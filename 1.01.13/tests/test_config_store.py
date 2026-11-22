# SPDX-License-Identifier: MIT
"""Real Windows DPAPI and interrupted credential commits, with synthetic keys."""
import json
from pathlib import Path
import sys

import httpx
import pytest

from nkc_galgame_translator import config_store as module
from nkc_galgame_translator.config_store import ConfigStore, ConfigStoreError


pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows DPAPI integration')
FIRST = 'synthetic-credential-first-not-a-real-api-key'
SECOND = 'synthetic-credential-second-not-a-real-api-key'


@pytest.fixture
def store(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail('Configuration storage must not construct an HTTP client')
    monkeypatch.setattr(httpx, 'Client', no_network)
    monkeypatch.setattr(httpx, 'AsyncClient', no_network)
    result = ConfigStore(tmp_path)
    result.example_path.parent.mkdir(parents=True)
    result.example_path.write_text(json.dumps({
        'api_key': 'YOUR_API_KEY', 'model': 'test-model', 'source_lang': 'ja',
        'target_lang': 'zh-Hans', 'offline_only': False,
    }), encoding='utf-8')
    return result


def persisted(store):
    return json.loads(store.config_path.read_text(encoding='utf-8'))


def write_legacy(store, value=FIRST, **fields):
    store.config_path.write_text(json.dumps({'api_key': value, **fields}), encoding='utf-8')


def assert_no_plaintext(store, secret):
    assert 'api_key' not in persisted(store)
    assert secret.encode() not in store.config_path.read_bytes()
    if store.credentials_path.exists():
        assert secret.encode() not in store.credentials_path.read_bytes()
    assert not list(store.config_path.parent.glob('.*.tmp'))


def test_actual_dpapi_roundtrip_preserves_all_settings(store):
    values = {'model': 'custom', 'game': '\u7d05\u9b54\u9928', 'source_lang': 'auto',
              'agreement_version': '2026-11-14', 'agreement_accepted_at': '2026-11-14T00:00:00Z',
              'api_setup_complete': True, 'offline_only': True}
    result = store.save(values, api_key=FIRST)
    assert result['api_key'] == FIRST
    assert store.credentials_path.read_bytes().startswith(module._MAGIC)
    assert_no_plaintext(store, FIRST)
    loaded = ConfigStore(store.root).load()
    assert loaded['api_key'] == FIRST
    assert all(loaded[key] == value for key, value in values.items())
    assert store.credential_error == ''


def test_empty_defaults_and_example_key_never_enable_network(store):
    store.example_path.write_text(json.dumps({'api_key': FIRST, 'model': 'example'}), encoding='utf-8')
    loaded = store.load()
    assert loaded['model'] == 'example' and loaded['api_key'] == ''
    assert loaded['active_api_slot'] == 0
    assert len(loaded['api_slots']) == 3
    assert not any(slot['has_api_key'] for slot in loaded['api_slots'])
    assert not store.config_path.exists()
    assert not store.credentials_path.exists()
    assert store.credential_error == ''


def test_legacy_migration_encrypts_then_removes_plaintext(store):
    write_legacy(store, FIRST, game='Remilia', agreement_version='1', offline_only=True)
    assert store.load()['api_key'] == ''
    assert '\u65e7\u5bc6\u94a5' in store.credential_error
    assert_no_plaintext(store, FIRST)
    assert persisted(store)['game'] == 'Remilia'
    assert persisted(store)['agreement_version'] == '1'
    assert ConfigStore(store.root).load()['api_key'] == ''
    assert FIRST in store._read_credentials()['keys'].values()
    assert store.save({}, api_key=FIRST)['api_key'] == FIRST


@pytest.mark.parametrize('placeholder', ['', 'YOUR_API_KEY', ' your_api_key ', None])
def test_blank_legacy_fields_are_removed_without_creating_credentials(store, placeholder):
    write_legacy(store, placeholder)
    assert store.load()['api_key'] == ''
    assert 'api_key' not in persisted(store)
    assert not store.credentials_path.exists()


def test_none_preserves_disk_key_and_ignores_runtime_key_and_pointer(store):
    initial = store.save({'game': 'first'}, api_key=FIRST)
    before = store.credentials_path.read_bytes()
    result = store.save({'api_key': SECOND, 'credential_id': '0' * 32, 'game': 'second'})
    assert result['api_key'] == FIRST
    assert result['credential_id'] == initial['credential_id']
    assert store.credentials_path.read_bytes() == before
    assert ConfigStore(store.root).load()['game'] == 'second'
    assert_no_plaintext(store, FIRST)
    assert_no_plaintext(store, SECOND)


def test_save_before_load_also_migrates_legacy_key(store):
    write_legacy(store, FIRST)
    assert store.save({'game': 'custom'})['api_key'] == ''
    assert_no_plaintext(store, FIRST)
    assert store.load()['api_key'] == ''
    assert FIRST in store._read_credentials()['keys'].values()


def test_placeholder_legacy_field_does_not_clear_existing_encrypted_key(store):
    store.save({}, api_key=FIRST)
    settings = persisted(store)
    settings['api_key'] = 'YOUR_API_KEY'
    store.config_path.write_text(json.dumps(settings), encoding='utf-8')
    assert store.load()['api_key'] == FIRST
    assert_no_plaintext(store, FIRST)
    assert FIRST in store._read_credentials()['keys'].values()


@pytest.mark.parametrize('empty', ['', '   ', 'YOUR_API_KEY'])
def test_explicit_empty_key_clears_credentials(store, empty):
    store.save({}, api_key=FIRST)
    assert store.save({'api_key': FIRST, 'game': 'kept'}, api_key=empty)['api_key'] == ''
    assert persisted(store)['credential_id'] == ''
    assert not store.credentials_path.exists()
    assert store.load()['api_key'] == ''
    assert store.load()['game'] == 'kept'


def test_failed_cleanup_cannot_resurrect_cleared_key(store, monkeypatch):
    store.save({}, api_key=FIRST)
    real_unlink = Path.unlink
    def fail_credentials_unlink(path, *args, **kwargs):
        if path == store.credentials_path:
            raise PermissionError('test cleanup failure')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_credentials_unlink)
    assert store.save({}, api_key='')['api_key'] == ''
    assert store.credentials_path.exists()
    assert ConfigStore(store.root).load()['api_key'] == ''


@pytest.mark.parametrize('damage', ['header', 'truncated', 'bitflip'])
def test_corrupt_credentials_fail_closed_and_never_expose_secret(store, damage):
    store.save({}, api_key=FIRST)
    encrypted = store.credentials_path.read_bytes()
    if damage == 'header':
        encrypted = FIRST.encode()
    elif damage == 'truncated':
        encrypted = encrypted[:len(module._MAGIC) + 15]
    else:
        raw = bytearray(encrypted)
        raw[-8] ^= 0xA5
        encrypted = bytes(raw)
    store.credentials_path.write_bytes(encrypted)
    assert store.load()['api_key'] == ''
    assert store.credential_error
    assert FIRST not in store.credential_error
    assert store.credentials_path.read_bytes() == encrypted


def test_missing_referenced_cipher_is_reported_as_missing_key(store):
    store.save({}, api_key=FIRST)
    store.credentials_path.unlink()
    assert store.load()['api_key'] == ''
    assert store.credential_error


def test_new_explicit_key_recovers_from_corrupt_cipher(store):
    store.credentials_path.write_bytes(FIRST.encode())
    assert store.load()['api_key'] == ''
    assert store.credential_error
    assert store.save({'offline_only': False}, api_key=SECOND)['api_key'] == SECOND
    assert store.load()['api_key'] == SECOND
    assert store.credential_error == ''
    assert_no_plaintext(store, SECOND)


def test_settings_save_preserves_unreadable_cipher_for_recovery(store):
    store.save({}, api_key=FIRST)
    encrypted = store.credentials_path.read_bytes()[:20]
    store.credentials_path.write_bytes(encrypted)
    assert store.save({'offline_only': True})['api_key'] == ''
    assert store.credential_error
    assert store.credentials_path.read_bytes() == encrypted
    assert store.load()['offline_only'] is True


def test_failed_cipher_write_leaves_prior_config_and_key_usable(store, monkeypatch):
    store.save({'game': 'original'}, api_key=FIRST)
    prior_json = store.config_path.read_bytes()
    prior_cipher = store.credentials_path.read_bytes()
    real_write = module._atomic_write
    def fail_cipher(path, data):
        if path == store.credentials_path:
            raise PermissionError(SECOND)
        real_write(path, data)
    monkeypatch.setattr(module, '_atomic_write', fail_cipher)
    with pytest.raises(ConfigStoreError) as caught:
        store.save({'game': 'changed'}, api_key=SECOND)
    assert SECOND not in str(caught.value)
    assert store.config_path.read_bytes() == prior_json
    assert store.credentials_path.read_bytes() == prior_cipher
    assert ConfigStore(store.root).load()['api_key'] == FIRST


def test_json_commit_failure_retains_old_record_in_encrypted_journal(store, monkeypatch):
    store.save({'game': 'original'}, api_key=FIRST)
    original = store.config_path.read_bytes()
    real_write = module._atomic_write
    def fail_json(path, data):
        if path == store.config_path:
            raise PermissionError(SECOND)
        real_write(path, data)
    monkeypatch.setattr(module, '_atomic_write', fail_json)
    with pytest.raises(ConfigStoreError) as caught:
        store.save({'game': 'changed'}, api_key=SECOND)
    assert SECOND not in str(caught.value)
    assert store.config_path.read_bytes() == original
    loaded = ConfigStore(store.root).load()
    assert loaded['api_key'] == FIRST
    assert loaded['game'] == 'original'
    assert_no_plaintext(store, FIRST)
    assert_no_plaintext(store, SECOND)


def test_migration_json_failure_preserves_plaintext_until_retry_verified(store, monkeypatch):
    write_legacy(store, FIRST, game='unchanged')
    original = store.config_path.read_bytes()
    real_write = module._atomic_write
    def fail_json(path, data):
        if path == store.config_path:
            raise PermissionError(FIRST)
        real_write(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(module, '_atomic_write', fail_json)
        assert store.load()['api_key'] == ''
        assert store.credential_error
        assert FIRST not in store.credential_error
        assert store.config_path.read_bytes() == original
    assert store.load()['api_key'] == ''
    assert_no_plaintext(store, FIRST)


def test_migration_readback_failure_does_not_clear_original_plaintext(store, monkeypatch):
    write_legacy(store, FIRST)
    original = store.config_path.read_bytes()
    real_read = store._read_credentials
    def refuse_persisted_cipher():
        if store.credentials_path.exists():
            raise ConfigStoreError('\u6a21\u62df\u8bfb\u56de\u5931\u8d25\u3002')
        return real_read()
    monkeypatch.setattr(store, '_read_credentials', refuse_persisted_cipher)
    assert store.load()['api_key'] == ''
    assert store.credential_error
    assert store.config_path.read_bytes() == original


def test_optional_compaction_failure_does_not_invalidate_success(store, monkeypatch):
    store.save({}, api_key=FIRST)
    real_write = store._write_credentials
    calls = 0
    def fail_compaction(payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError('test compaction failure')
        return real_write(payload)
    monkeypatch.setattr(store, '_write_credentials', fail_compaction)
    assert store.save({}, api_key=SECOND)['api_key'] == SECOND
    assert ConfigStore(store.root).load()['api_key'] == SECOND


def test_atomic_replace_failure_preserves_original_and_removes_temp(store, monkeypatch):
    destination = store.root / 'replace-test.txt'
    destination.write_bytes(b'original')
    def fail_replace(*args):
        raise PermissionError('test replace failure')
    monkeypatch.setattr(module.os, 'replace', fail_replace)
    with pytest.raises(PermissionError):
        module._atomic_write(destination, b'replacement')
    assert destination.read_bytes() == b'original'
    assert not list(store.root.glob('.replace-test.txt.*.tmp'))


def test_corrupt_json_refuses_load_and_save_without_overwriting(store):
    damaged = ('{"api_key": "' + FIRST).encode()
    store.config_path.write_bytes(damaged)
    for operation in (store.load, lambda: store.save({}, api_key=SECOND)):
        with pytest.raises(ConfigStoreError) as caught:
            operation()
        assert FIRST not in str(caught.value)
        assert SECOND not in str(caught.value)
        assert store.config_path.read_bytes() == damaged
    assert not store.credentials_path.exists()


@pytest.mark.parametrize('invalid', [123, 'synthetic\x00bad', '\ud800', 'x' * 8193])
def test_invalid_explicit_key_is_rejected_without_changing_files(store, invalid):
    store.save({}, api_key=FIRST)
    original_json = store.config_path.read_bytes()
    original_cipher = store.credentials_path.read_bytes()
    with pytest.raises(ConfigStoreError):
        store.save({}, api_key=invalid)
    assert store.config_path.read_bytes() == original_json
    assert store.credentials_path.read_bytes() == original_cipher
    assert store.load()['api_key'] == FIRST


def test_unserializable_settings_do_not_replace_existing_key(store):
    store.save({}, api_key=FIRST)
    cipher = store.credentials_path.read_bytes()
    with pytest.raises(ConfigStoreError):
        store.save({'not_json': object()}, api_key=SECOND)
    assert store.credentials_path.read_bytes() == cipher
    assert store.load()['api_key'] == FIRST


def test_renaming_project_folder_does_not_change_dpapi_domain(store):
    store.save({'game': 'portable-name'}, api_key=FIRST)
    renamed = store.root.with_name(store.root.name + '_renamed')
    store.root.rename(renamed)
    loaded = ConfigStore(renamed).load()
    assert loaded['api_key'] == FIRST
    assert loaded['game'] == 'portable-name'


THIRD = 'synthetic-credential-third-not-a-real-api-key'


@pytest.mark.parametrize('operation', ['save', 'slot', 'legacy'])
def test_partial_settings_preserve_example_connection_defaults(store, operation):
    store.example_path.write_text(json.dumps({'base_url': 'https://configured.example.test/v1',
        'model': 'configured-model'}), encoding='utf-8')
    if operation == 'save':
        loaded = store.save({'offline_only': True}, FIRST)
    elif operation == 'slot':
        loaded = store.save_api_slot(1, 'https://second.example.test', 'second', SECOND,
                                     activate=False)
    else:
        write_legacy(store, FIRST, offline_only=True)
        loaded = store.load()
    assert loaded['base_url'] == 'https://configured.example.test/v1'
    assert loaded['model'] == 'configured-model'
    assert loaded['api_slots'][0]['base_url'] == loaded['base_url']
    assert loaded['api_slots'][0]['model'] == loaded['model']
    restarted = ConfigStore(store.root).load()
    assert restarted['base_url'] == loaded['base_url']
    assert restarted['model'] == loaded['model']


def test_three_slots_independent_after_restart_and_activation(store):
    for index, key in enumerate((FIRST, SECOND, THIRD)):
        result = store.save_api_slot(index, f'https://api{index}.example.test', f'model{index}', key)
        assert result['active_api_slot'] == index
        assert result['api_key'] == key
        assert result['api_setup_complete'] is True
    restarted = ConfigStore(store.root)
    assert all(slot['has_api_key'] for slot in restarted.load()['api_slots'])
    for index, key in enumerate((FIRST, SECOND, THIRD)):
        result = restarted.save_api_slot(index, f'https://api{index}.example.test', f'model{index}')
        assert result['api_key'] == key
        assert result['base_url'] == f'https://api{index}.example.test'
        assert result['model'] == f'model{index}'
        assert len(result['api_slots']) == 3
        for slot in result['api_slots']:
            assert set(slot) == {'base_url', 'model', 'has_api_key'}
    for key in (FIRST, SECOND, THIRD):
        assert_no_plaintext(store, key)


def test_clearing_one_slot_does_not_clear_other_keys(store):
    for index, key in enumerate((FIRST, SECOND, THIRD)):
        store.save_api_slot(index, f'https://api{index}.example.test', f'model{index}', key)
    cleared = store.save_api_slot(1, 'https://api1.example.test', 'model1', '')
    assert cleared['api_key'] == ''
    assert [slot['has_api_key'] for slot in cleared['api_slots']] == [True, False, True]
    assert store.credentials_path.exists()
    assert store.save_api_slot(0, 'https://api0.example.test', 'model0')['api_key'] == FIRST
    assert store.save_api_slot(2, 'https://api2.example.test', 'model2')['api_key'] == THIRD
    store.save_api_slot(0, 'https://api0.example.test', 'model0', '')
    store.save_api_slot(2, 'https://api2.example.test', 'model2', '')
    assert not store.credentials_path.exists()
    assert not any(slot['has_api_key'] for slot in store.load()['api_slots'])


def test_save_inactive_slot_does_not_change_active_or_mode(store):
    store.save_api_slot(0, 'https://first.example.test', 'first', FIRST, offline_only=True)
    result = store.save_api_slot(2, 'https://third.example.test', 'third', THIRD,
                                 activate=False, offline_only=False)
    assert result['api_key'] == FIRST and result['model'] == 'first'
    assert result['active_api_slot'] == 0 and result['offline_only'] is True
    assert result['api_slots'][2]['has_api_key'] is True
    assert store.save_api_slot(2, 'https://third.example.test', 'third')['api_key'] == THIRD


def test_ordinary_save_cannot_change_slot_or_resurrect_another_pointer(store):
    store.save_api_slot(0, 'https://first.example.test', 'first', FIRST)
    store.save_api_slot(2, 'https://third.example.test', 'third', THIRD)
    result = store.save({'active_api_slot': 0, 'api_slots': [{'api_key': SECOND}],
                         'credential_id': persisted(store)['api_slots'][0]['credential_id'],
                         'api_key': SECOND, 'game': 'ordinary-save'})
    assert result['active_api_slot'] == 2 and result['api_key'] == THIRD
    assert result['game'] == 'ordinary-save'
    assert store.save_api_slot(0, 'https://first.example.test', 'first')['api_key'] == FIRST
    assert_no_plaintext(store, SECOND)


def test_single_encrypted_config_migrates_to_first_slot_without_reencryption(store):
    store.save({'base_url': 'https://old.example.test', 'model': 'old-model'}, FIRST)
    original_cipher = store.credentials_path.read_bytes()
    settings = persisted(store)
    del settings['api_slots']; del settings['active_api_slot']
    store.config_path.write_text(json.dumps(settings), encoding='utf-8')
    loaded = ConfigStore(store.root).load()
    assert loaded['api_key'] == FIRST
    assert loaded['active_api_slot'] == 0
    assert loaded['api_slots'][0] == {'base_url': 'https://old.example.test',
                                    'model': 'old-model', 'has_api_key': True}
    assert [s['has_api_key'] for s in loaded['api_slots']] == [True, False, False]
    assert store.credentials_path.read_bytes() == original_cipher
    assert len(persisted(store)['api_slots']) == 3


def test_editing_slot_two_first_migrates_legacy_key_to_slot_one(store):
    write_legacy(store, FIRST, base_url='https://old.example.test', model='old')
    result = store.save_api_slot(1, 'https://second.example.test', 'second', SECOND)
    assert result['api_key'] == SECOND and result['active_api_slot'] == 1
    with pytest.raises(ConfigStoreError):
        store.save_api_slot(0, 'https://old.example.test', 'old')
    assert store.save_api_slot(0, 'https://old.example.test', 'old', FIRST)['api_key'] == FIRST
    for key in (FIRST, SECOND): assert_no_plaintext(store, key)


def test_failed_json_slot_commit_preserves_every_original_slot_and_activation(store, monkeypatch):
    for index, key in enumerate((FIRST, SECOND, THIRD)):
        store.save_api_slot(index, f'https://api{index}.example.test', f'model{index}', key)
    before = store.config_path.read_bytes()
    real_write = module._atomic_write
    def fail_json(path, data):
        if path == store.config_path: raise PermissionError(SECOND)
        return real_write(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(module, '_atomic_write', fail_json)
        with pytest.raises(ConfigStoreError) as error:
            store.save_api_slot(0, 'https://changed.example.test', 'changed', SECOND)
        assert SECOND not in str(error.value)
    assert store.config_path.read_bytes() == before
    assert store.load()['active_api_slot'] == 2
    for index, key in enumerate((FIRST, SECOND, THIRD)):
        assert store.save_api_slot(index, f'https://api{index}.example.test', f'model{index}')['api_key'] == key


def test_corrupt_multislot_cipher_refuses_overwriting_other_keys(store):
    store.save_api_slot(0, 'https://first.example.test', 'first', FIRST)
    store.save_api_slot(1, 'https://second.example.test', 'second', SECOND)
    broken = store.credentials_path.read_bytes()[:25]
    store.credentials_path.write_bytes(broken)
    before = store.config_path.read_bytes()
    with pytest.raises(ConfigStoreError):
        store.save_api_slot(0, 'https://new.example.test', 'new', THIRD)
    assert store.config_path.read_bytes() == before
    assert store.credentials_path.read_bytes() == broken
    result = store.save_api_slot(0, 'https://first.example.test', 'first', '', offline_only=True)
    assert result['api_key'] == ''
    assert store.credentials_path.read_bytes() == broken
    assert persisted(store)['api_slots'][1]['credential_id']
    store.save_api_slot(1, 'https://second.example.test', 'second', '', offline_only=True)
    assert not store.credentials_path.exists()


@pytest.mark.parametrize('invalid', [-1, 3, True, False, '1', None, 1.5])
def test_invalid_slot_does_not_change_files(store, invalid):
    store.save({}, FIRST)
    before = store.config_path.read_bytes(), store.credentials_path.read_bytes()
    with pytest.raises(ConfigStoreError):
        store.save_api_slot(invalid, 'https://example.test', 'model', SECOND)
    assert (store.config_path.read_bytes(), store.credentials_path.read_bytes()) == before


def test_example_slot_pointers_cannot_activate_stored_secret(store):
    store.save({}, FIRST)
    settings = persisted(store)
    store.config_path.unlink()
    store.example_path.write_text(json.dumps({'api_slots': settings['api_slots'],
        'active_api_slot': 0, 'credential_id': settings['credential_id'], 'api_key': FIRST}), encoding='utf-8')
    # The encrypted payload contains an old committed active record. The legacy
    # recovery fallback applies without local JSON, but example pointers have no
    # authority over selection; its metadata never enters the runtime slots.
    loaded = store.load()
    assert loaded['api_slots'][0]['base_url'] == 'https://api.deepseek.com'
    assert len(loaded['api_slots']) == 3
