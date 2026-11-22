# SPDX-License-Identifier: MIT
"""Atomic configuration and Windows CurrentUser DPAPI credential storage.

The JSON settings file contains three slot credential IDs, never API keys.
Credentials use a small encrypted journal: write old+new records, commit the
JSON pointers, then compact. A failed JSON commit cannot discard prior keys.
DPAPI protects stored bytes, not secrets while the application is using them.
"""
from __future__ import annotations

from .i18n import ui_source

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import uuid
from .api_providers import local_endpoint, provider_for
from .security import SecurityValidationError, validate_api_url, validate_model, normalize_api_key


class ConfigStoreError(RuntimeError):
    """A sanitized error suitable for displaying without exposing credentials."""


_MAGIC = b'NKC-DPAPI\x01'
_ENTROPY = b'Nishokuchou.GameRealtimeTranslator.credentials.v1'
_MAX_FILE_BYTES = 1024 * 1024
_UI_FORBIDDEN = 0x1  # Deliberately never OR in CRYPTPROTECT_LOCAL_MACHINE.


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate configuration field')
        result[name] = value
    return result


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != 'win32':
        raise ConfigStoreError(ui_source('Key encryption requires a Windows user account.'))
    if not data or len(data) > _MAX_FILE_BYTES:
        raise ConfigStoreError(ui_source('Invalid credential file. Enter the API key again.'))
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p if decrypt else ctypes.c_wchar_p,
                         ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data, len(data))
    entropy_buffer = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy = _Blob(len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    try:
        description = None if decrypt else 'NKC_Galgame_Translator API credentials'
        if not function(ctypes.byref(source), description, ctypes.byref(entropy), None, None,
                        _UI_FORBIDDEN, ctypes.byref(output)):
            message = (ui_source('The saved key could not be decrypted. Enter it again under this Windows account.') if decrypt
                       else ui_source('Could not encrypt the API key. The previous configuration was not removed.'))
            raise ConfigStoreError(message)
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if output.pbData:
            ctypes.memset(output.pbData, 0, output.cbData)
            kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def _normalize_key(value) -> str:
    try:
        return normalize_api_key(value)
    except SecurityValidationError as error:
        raise ConfigStoreError(str(error)) from None


def _atomic_write(path: Path, content: bytes) -> None:
    """Write beside the destination and replace only a complete flushed file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != content:
            raise OSError('Incomplete configuration write')
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class ConfigStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.config_path = self.root / 'config' / 'local.json'
        self.example_path = self.root / 'config' / 'example.json'
        self.credentials_path = self.root / 'config' / 'credentials.bin'
        self.credential_error = ''
        self._lock = threading.RLock()

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                raise ValueError('Too large')
            with path.open('rb') as handle:
                raw = handle.read(_MAX_FILE_BYTES + 1)
            if len(raw) > _MAX_FILE_BYTES:
                raise ValueError('Too large')
            result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object,
                                parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
            if not isinstance(result, dict):
                raise ValueError('Expected object')
            pending, count = [(result, 0)], 0
            while pending:
                value, depth = pending.pop()
                count += 1
                if depth > 32 or count > 10000:
                    raise ValueError('Configuration complexity limit')
                if isinstance(value, (list, dict)):
                    pending.extend((child, depth+1) for child in (value.values() if isinstance(value, dict) else value))
            return result
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise ConfigStoreError(ui_source('Could not read the configuration. Check config/local.json and the example configuration.')) from None

    def _settings(self) -> tuple[dict, dict]:
        example = self._read_json(self.example_path)
        local = self._read_json(self.config_path)
        # A real key is only migrated from the private local file, never from a
        # public example. Defaults still supply ordinary settings such as URL.
        example.pop('api_key', None)
        for field in ('api_slots', 'active_api_slot', 'credential_id'):
            example.pop(field, None)
        settings = {**example, **local}
        if 'vision_ocr_mode' not in local and type(local.get('vision_ocr')) is bool:
            settings['vision_ocr_mode'] = 'force' if local['vision_ocr'] else 'off'
        elif settings.get('vision_ocr_mode')=='auto':
            settings['vision_ocr_mode']='hardware'
        # Migrate wider legacy prompt budgets in memory; archives remain complete.
        for field,maximum in (('context_max_chars',16384),('context_history_records',2)):
            if type(settings.get(field)) is int:
                settings[field]=min(settings[field],maximum)
        return settings, local

    @staticmethod
    def _empty_credentials() -> dict:
        return {'format': 'nkc-api-credentials', 'version': 1, 'active_id': '', 'keys': {}, 'endpoints': {}}

    def _read_credentials(self) -> dict:
        if not self.credentials_path.exists():
            return self._empty_credentials()
        try:
            if self.credentials_path.stat().st_size > _MAX_FILE_BYTES:
                raise ValueError('Too large')
            with self.credentials_path.open('rb') as handle:
                raw = handle.read(_MAX_FILE_BYTES + 1)
            if not raw.startswith(_MAGIC) or len(raw) > _MAX_FILE_BYTES:
                raise ValueError('Bad envelope')
            payload = json.loads(_dpapi(raw[len(_MAGIC):], decrypt=True).decode('utf-8'))
            if (not isinstance(payload, dict) or payload.get('format') != 'nkc-api-credentials'
                    or payload.get('version') != 1 or not isinstance(payload.get('keys'), dict)
                    or not isinstance(payload.get('active_id'), str)):
                raise ValueError('Bad payload')
            for identity, key in payload['keys'].items():
                if (not isinstance(identity, str) or len(identity) != 32 or
                        any(char not in '0123456789abcdef' for char in identity) or
                        not isinstance(key, str) or not key or _normalize_key(key) != key):
                    raise ValueError('Bad credential')
            payload.setdefault('endpoints', {})
            if not isinstance(payload['endpoints'], dict):
                raise ValueError('Bad endpoint bindings')
            for identity, endpoint in payload['endpoints'].items():
                if identity not in payload['keys'] or validate_api_url(endpoint) != endpoint:
                    raise ValueError('Bad endpoint binding')
            if payload['active_id'] and payload['active_id'] not in payload['keys']:
                raise ValueError('Bad active pointer')
            return payload
        except (OSError, ValueError, UnicodeError, RecursionError, ConfigStoreError):
            raise ConfigStoreError(ui_source('Could not read the saved API key. Enter it again.')) from None

    def _write_credentials(self, payload: dict) -> None:
        content = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        encrypted = _MAGIC + _dpapi(content, decrypt=False)
        # Verify the encrypted payload before replacing any existing file.
        if _dpapi(encrypted[len(_MAGIC):], decrypt=True) != content:
            raise ConfigStoreError(ui_source('Key encryption verification failed. The previous configuration was not removed.'))
        _atomic_write(self.credentials_path, encrypted)
        # Migration must also read back what was actually persisted before the
        # legacy plaintext configuration is removed.
        if self._read_credentials() != payload:
            raise ConfigStoreError(ui_source('Saved-key verification failed. The previous configuration was not removed.'))

    @staticmethod
    def _selected_key(settings: dict, payload: dict) -> str:
        # An explicit empty ID means cleared, even if orphaned encrypted data
        # remains after interrupted cleanup.
        identity = settings.get('credential_id', payload['active_id'])
        if not identity:
            return ''
        if not isinstance(identity, str) or identity not in payload['keys']:
            raise ConfigStoreError(ui_source('No saved API key was found. Enter it again.'))
        return payload['keys'][identity]

    @staticmethod
    def _slot_index(index) -> int:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 3:
            raise ConfigStoreError(ui_source('API slot must be 1, 2, or 3.'))
        return index

    @classmethod
    def _slots(cls, settings: dict, payload: dict) -> tuple[list[dict], int]:
        """Read persisted pointers only. Runtime metadata is never authoritative."""
        default = {'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
                   'credential_id': ''}
        if 'api_slots' not in settings:
            slots = [dict(default) for _ in range(3)]
            slots[0].update(base_url=settings.get('base_url') or default['base_url'],
                            model=settings.get('model') or default['model'],
                            credential_id=settings.get('credential_id', payload['active_id']))
            active = 0
        else:
            raw = settings['api_slots']
            if not isinstance(raw, list) or len(raw) != 3:
                raise ConfigStoreError(ui_source('Invalid API slot configuration. Check the local settings.'))
            slots = []
            for slot in raw:
                if not isinstance(slot, dict) or not isinstance(slot.get('credential_id'), str):
                    raise ConfigStoreError(ui_source('Invalid API slot configuration. Check the local settings.'))
                record = {name: slot.get(name) for name in default}
                if slot.get('local_provider') in ('local', 'ollama'):
                    record['local_provider'] = slot['local_provider']
                slots.append(record)
            active = cls._slot_index(settings.get('active_api_slot', 0))
        for slot in slots:
            try:
                slot['base_url'] = validate_api_url(slot['base_url'])
                slot['model'] = validate_model(slot['model'])
            except SecurityValidationError:
                # Recover the form and offline onboarding, but never attach an
                # existing secret to the public fallback endpoint. Ciphertext
                # is not removed by reading or ordinary preference saves.
                slot.update(default)
                slot['_metadata_error'] = True
            cls._set_local_provider(slot)
        return slots, active

    @staticmethod
    def _set_local_provider(slot):
        provider = provider_for(slot['base_url'], slot.get('local_provider'))
        if provider in ('local', 'ollama'):
            slot['local_provider'] = provider
        else:
            slot.pop('local_provider', None)

    def _runtime(self, settings: dict, payload: dict, error='') -> dict:
        slots, active = self._slots(settings, payload)
        selected = slots[active]
        if selected.get('_metadata_error'):
            error = ui_source('The API address or model is invalid. This slot is disabled and shows defaults. Verify the provider and enter the key again.')
        identity = selected['credential_id']
        key = payload['keys'].get(identity, '')
        if key:
            try:
                endpoint = validate_api_url(selected['base_url'])
                validate_model(selected['model'])
                if payload.get('endpoints', {}).get(identity) != endpoint:
                    raise SecurityValidationError('Binding mismatch')
            except SecurityValidationError:
                key = ''
                error = ui_source('The key is bound to a different API address or has no address binding. Verify the provider and enter this slot’s key again.')
        if identity and not key and not error:
            error = ui_source('No saved key was found for the current slot. Enter it again.')
        self.credential_error = error
        # Only the active key leaves this class. Other slots expose status, not
        # pointers or secret values; neither the form nor logs need those keys.
        return {**settings, 'active_api_slot': active,
                'api_slots': [{'base_url': slot['base_url'], 'model': slot['model'],
                               **({'local_provider': slot['local_provider']} if 'local_provider' in slot else {}),
                               'has_api_key': bool(payload['keys'].get(slot['credential_id']) and payload.get('endpoints', {}).get(slot['credential_id']) == slot['base_url'])}
                              for slot in slots],
                'base_url': selected['base_url'], 'model': selected['model'],
                'credential_id': identity, 'api_key': key}

    def load(self) -> dict:
        with self._lock:
            self.credential_error = ''
            settings, local = self._settings()
            legacy_present = 'api_key' in local
            legacy = local.get('api_key') or ''
            settings.pop('api_key', None)
            try:
                legacy = _normalize_key(legacy)
                if legacy_present or (local and 'api_slots' not in local):
                    # Upgrade both plaintext and 0.01.08 encrypted single-key
                    # files. Pointer-only migration does not rewrite ciphertext.
                    return self._save_locked(settings, legacy if legacy else None, settings, bind_key=False)
                payload = self._read_credentials()
                return self._runtime(settings, payload)
            except ConfigStoreError as error:
                # Do not leak a partially decrypted key after a failed migration.
                return self._runtime(settings, self._empty_credentials(), str(error))

    def _save_locked(self, config: dict, api_key: str | None, current: dict,
                     *, slot_update=None, bind_key=True) -> dict:
        try:
            settings = dict(config)
            for field in ('api_key', 'credential_id', 'api_slots', 'active_api_slot'):
                settings.pop(field, None)
            payload_error = ''
            try:
                payload = self._read_credentials()
            except ConfigStoreError as error:
                payload_error = str(error)
                payload = self._empty_credentials()
            slots, active = self._slots(current, payload)
            target = active
            old_ids = {slot['credential_id'] for slot in slots if slot['credential_id']}
            previous_active_id = slots[active]['credential_id']
            allow_key_reuse = False
            previous_endpoints = [slot['base_url'] for slot in slots]
            if slot_update is None:
                # Ordinary settings saves update the current slot only. Ignore
                # caller-supplied active IDs and slot arrays, including stale UI.
                for field in ('base_url', 'model'):
                    if field in config:
                        slots[target][field] = config[field]
            else:
                target, base_url, model, activate, offline_only, allow_key_reuse, local_provider = slot_update
                target = self._slot_index(target)
                if not isinstance(base_url, str) or not isinstance(model, str):
                    raise ConfigStoreError(ui_source('API address and model must be text.'))
                slots[target].update(base_url=base_url, model=model)
                if local_provider in ('local', 'ollama'):
                    slots[target]['local_provider'] = local_provider
                if activate:
                    active = target
                    settings['offline_only'] = bool(offline_only)
                settings['api_setup_complete'] = True
            slots[target]['base_url'] = validate_api_url(slots[target]['base_url'])
            slots[target]['model'] = validate_model(slots[target]['model'])
            self._set_local_provider(slots[target])
            old_target_id = slots[target]['credential_id']
            if api_key is None and old_target_id:
                bound = payload.get('endpoints', {}).get(old_target_id)
                if bound != slots[target]['base_url'] and (slot_update is not None or slots[target]['base_url'] != previous_endpoints[target]):
                    if not allow_key_reuse or local_endpoint(bound) or local_endpoint(slots[target]['base_url']):
                        raise ConfigStoreError(ui_source('The API address changed or the old key is unbound. Verify the provider and enter the key again.'))
                    api_key = payload['keys'].get(old_target_id, '')
                    if not api_key:
                        raise ConfigStoreError(ui_source('The previous key cannot be read. Enter it again.'))
            if api_key is not None:
                key = _normalize_key(api_key)
                if key and payload_error and any(slot['credential_id'] for i, slot in enumerate(slots) if i != target):
                    raise ConfigStoreError(ui_source('Another slot’s encrypted key is unreadable and cannot be overwritten. Restore the credential file and try again.'))
                identity = uuid.uuid4().hex if key else ''
                slots[target]['credential_id'] = identity
            else:
                key = payload['keys'].get(old_target_id, '')
                identity = old_target_id
            for slot in slots:
                slot.pop('_metadata_error', None)
            settings.update(api_slots=slots, active_api_slot=active,
                            base_url=slots[active]['base_url'], model=slots[active]['model'],
                            credential_id=slots[active]['credential_id'])
            serialized = (json.dumps(settings, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
            if len(serialized) > _MAX_FILE_BYTES:
                raise ConfigStoreError(ui_source('Configuration exceeds the 1 MiB limit. Nothing was saved.'))
            if api_key is not None and key:
                # Journal every previously referenced slot until JSON commits.
                # A failed active-slot switch must leave all three old keys usable.
                old_keys = {identity: value for identity, value in payload['keys'].items() if identity in old_ids}
                payload = {'format': 'nkc-api-credentials', 'version': 1,
                           'active_id': previous_active_id if previous_active_id in old_keys else '',
                           'keys': {**old_keys, identity: key},
                           'endpoints': {**{i:v for i,v in payload.get('endpoints', {}).items() if i in old_keys},
                                         **({identity: slots[target]['base_url']} if bind_key else {})}}
                self._write_credentials(payload)
            _atomic_write(self.config_path, serialized)
        except SecurityValidationError as error:
            raise ConfigStoreError(str(error)) from None
        except ConfigStoreError:
            raise
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            raise ConfigStoreError(ui_source('Could not save settings. Existing settings and keys were not deliberately removed.')) from None

        if api_key is not None:
            # Compaction is optional after JSON commits. Keep only selected
            # pointers across ALL slots; clearing one never clears the others.
            selected_ids = {slot['credential_id'] for slot in slots if slot['credential_id']}
            if not payload_error or key:
                keys = {identity: value for identity, value in payload['keys'].items() if identity in selected_ids}
                payload = {'format': 'nkc-api-credentials', 'version': 1,
                           'active_id': slots[active]['credential_id'] if slots[active]['credential_id'] in keys else '',
                           'keys': keys,
                           'endpoints': {i:v for i,v in payload.get('endpoints', {}).items() if i in keys}}
                payload_error = ''
                try:
                    if keys:
                        self._write_credentials(payload)
                    else:
                        self.credentials_path.unlink(missing_ok=True)
                except (OSError, ConfigStoreError):
                    pass
            elif not selected_ids:
                # Explicitly clearing the final bad reference may remove a
                # corrupt file. Clearing just one slot leaves others recoverable.
                try:
                    self.credentials_path.unlink(missing_ok=True)
                except OSError:
                    pass
                payload_error = ''
        return self._runtime(settings, payload, payload_error)

    def save(self, config: dict, api_key: str | None = None) -> dict:
        with self._lock:
            if not isinstance(config, dict):
                raise ConfigStoreError(ui_source('Invalid settings format.'))
            merged, local = self._settings()
            bind_key = True
            if 'api_key' in local and api_key is None:
                legacy = _normalize_key(local.get('api_key') or '')
                if legacy:
                    api_key = legacy
                    bind_key = False
            return self._save_locked(config, api_key, merged, bind_key=bind_key)

    def save_api_slot(self, index: int, base_url: str, model: str,
                      api_key: str | None = None, *, activate=True,
                      offline_only=False, allow_key_reuse=False, local_provider=None) -> dict:
        """Persist one slot and optionally activate it, without a network call.

        ``None`` retains that slot's key; an empty string clears only that slot.
        With ``activate=False``, the current slot and online/offline mode remain.
        """
        with self._lock:
            index = self._slot_index(index)
            settings, local = self._settings()
            # Migrate a legacy key before editing another slot, never attach the
            # old single key to whichever empty slot the user selected first.
            if 'api_key' in local:
                self.load()
                settings, local = self._settings()
                if 'api_key' in local:
                    raise ConfigStoreError(ui_source('The old API key has not finished encrypted migration. Restore the configuration first.'))
            return self._save_locked(settings, api_key, settings,
                                     slot_update=(index, base_url, model, bool(activate), bool(offline_only), bool(allow_key_reuse), local_provider))
