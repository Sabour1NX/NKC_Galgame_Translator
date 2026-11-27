# SPDX-License-Identifier: MIT
"""Thread-owned Win32 hotkeys; callbacks must enqueue UI events, never call Tk.

RegisterHotKey(NULL, ...) delivers WM_HOTKEY to its registering thread. A
PeekMessage call creates that thread's queue before PostThreadMessage is used.
https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-registerhotkey
https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-postthreadmessagew
"""
from __future__ import annotations

from .i18n import ui_source

from dataclasses import dataclass, field
import queue
import re
import threading

DEFAULT_HOTKEY = 'Ctrl+Alt+R'
DEFAULT_TOGGLE_HOTKEY = 'Ctrl+Alt+T'
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 1, 2, 4, 0x4000
WM_HOTKEY, WM_QUIT, WM_COMMAND = 0x0312, 0x0012, 0x8000 + 87


class HotkeyValidationError(ValueError):
    pass


def parse_hotkey(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or any(ord(c) < 32 for c in value):
        raise HotkeyValidationError(ui_source('Invalid shortcut. Enter a combination such as Ctrl+Alt+R.'))
    parts = [part.strip().upper() for part in value.split('+')]
    aliases = {'CTRL': 'Ctrl', 'CONTROL': 'Ctrl', 'ALT': 'Alt', 'SHIFT': 'Shift'}
    modifiers = [aliases.get(part) for part in parts[:-1]]
    if (len(parts) < 2 or any(value is None for value in modifiers) or
            len(set(modifiers)) != len(modifiers) or not {'Ctrl', 'Alt'} & set(modifiers)):
        raise HotkeyValidationError(ui_source('Include Ctrl or Alt; Shift is optional. Win and duplicate modifiers are not supported.'))
    key = parts[-1]
    if re.fullmatch('[A-Z0-9]', key):
        virtual_key = ord(key)
    elif re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])', key):
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        raise HotkeyValidationError(ui_source('Use A–Z, 0–9 or F1–F24 as the main key.'))
    if key == 'F12' or (set(modifiers) == {'Alt'} and key == 'F4'):
        raise HotkeyValidationError(ui_source('This combination is reserved by the system. Choose another.'))
    canonical = '+'.join([name for name in ('Ctrl', 'Alt', 'Shift') if name in modifiers] + [key])
    flags = sum({'Ctrl': MOD_CONTROL, 'Alt': MOD_ALT, 'Shift': MOD_SHIFT}[name] for name in modifiers)
    return canonical, flags | MOD_NOREPEAT, virtual_key


def normalize_hotkey(value):
    return parse_hotkey(value)[0]


@dataclass(frozen=True)
class HotkeyStatus:
    enabled: bool = False
    shortcut: str = DEFAULT_HOTKEY
    registered: bool = False
    error: str = ''
    error_code: str = ''

    @property
    def ok(self):
        return not self.error


class _Win32Hotkeys:
    def __init__(self):
        import ctypes as C
        from ctypes import wintypes as W
        self.C, self.W = C, W
        self.user = C.WinDLL('user32', use_last_error=True)
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.user.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
        self.user.PeekMessageW.restype = W.BOOL
        self.user.MsgWaitForMultipleObjectsEx.argtypes = [W.DWORD, C.POINTER(W.HANDLE), W.DWORD, W.DWORD, W.DWORD]
        self.user.MsgWaitForMultipleObjectsEx.restype = W.DWORD
        self.user.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
        self.user.PostThreadMessageW.restype = W.BOOL
        self.user.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
        self.user.RegisterHotKey.restype = W.BOOL
        self.user.UnregisterHotKey.argtypes = [W.HWND, C.c_int]
        self.user.UnregisterHotKey.restype = W.BOOL
        self.kernel.GetCurrentThreadId.restype = W.DWORD
        self.thread_id = 0

    def start(self):
        self.thread_id = self.kernel.GetCurrentThreadId()
        message = self.W.MSG()
        self.user.PeekMessageW(self.C.byref(message), None, 0, 0, 0)

    def post(self, message):
        return bool(self.user.PostThreadMessageW(self.thread_id, message, 0, 0))

    def receive(self):
        # The bounded OS wait is a shutdown fallback if posting WM_QUIT fails.
        # It does not poll keys and sleeps in the kernel when there is no input.
        waited = self.user.MsgWaitForMultipleObjectsEx(0, None, 250, 0x04FF, 0x0004)
        if waited == 258:
            return None
        if waited == 0xFFFFFFFF:
            raise OSError('Hotkey message wait failed')
        message = self.W.MSG()
        if not self.user.PeekMessageW(self.C.byref(message), None, 0, 0, 1):
            return None
        return int(message.message), int(message.wParam)

    def register(self, identity, modifiers, virtual_key):
        return bool(self.user.RegisterHotKey(None, identity, modifiers, virtual_key))

    def unregister(self, identity):
        return bool(self.user.UnregisterHotKey(None, identity))


@dataclass
class _Request:
    enabled: bool
    shortcut: str
    modifiers: int
    virtual_key: int
    done: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancelled: bool = False
    result: HotkeyStatus | None = None


class GlobalHotkey:
    """One active registration, atomically replaced only when a new one succeeds.

    update returns the effective registration, including the retained old one on
    failure. close is idempotent and returns whether the worker has stopped.
    The optional backend factory is solely for deterministic WinAPI-free tests.
    """
    def __init__(self, callback, *, _backend_factory=None):
        if not callable(callback):
            raise TypeError('Hotkey callback must be callable')
        self._callback = callback
        self._factory = _backend_factory or _Win32Hotkeys
        self._status = HotkeyStatus()
        self._commands = queue.Queue()
        self._operations = threading.RLock()
        self._ready, self._closing = threading.Event(), threading.Event()
        self._backend = None
        self._active_id = None
        self._registered_ids = set()
        self._thread = threading.Thread(target=self._run, name='global-retranslate-hotkey', daemon=True)
        try:self._thread.start()
        except RuntimeError:
            self._status = HotkeyStatus(False, DEFAULT_HOTKEY, False,
                ui_source('Global shortcuts are unavailable. Change the combination and save again.'), 'unavailable')
            self._ready.set()
        self._ready.wait(1.0)

    @property
    def status(self):
        return self._status

    def _failure(self, message, code):
        current = self._status
        return HotkeyStatus(current.enabled, current.shortcut, current.registered, message, code)

    def update(self, enabled, shortcut=DEFAULT_HOTKEY):
        try:
            if type(enabled) is not bool:
                raise HotkeyValidationError(ui_source('The shortcut switch must be on or off.'))
            canonical, modifiers, virtual_key = parse_hotkey(shortcut)
        except HotkeyValidationError as error:
            return self._failure(str(error), 'invalid')
        with self._operations:
            if self._closing.is_set():
                return self._failure(ui_source('The shortcut service is closed.'), 'closed')
            if not self._ready.is_set() or self._backend is None or not self._thread.is_alive():
                return self._failure(ui_source('Global shortcuts are unavailable. Change the combination and save again.'), 'unavailable')
            request = _Request(enabled, canonical, modifiers, virtual_key)
            self._commands.put(request)
            try:posted = self._backend.post(WM_COMMAND)
            except Exception:posted = False
            if not posted:
                with request.lock:
                    request.cancelled = True
                return self._failure(ui_source('Cannot update the shortcut. The previous one is unchanged.'), 'post_failed')
            if not request.done.wait(1.0):
                with request.lock:
                    if request.result is None:
                        request.cancelled = True
                        return self._failure(ui_source('The shortcut service timed out. The previous one is unchanged.'), 'timeout')
            return request.result or self._failure(ui_source('Global shortcuts are unavailable. Change the combination and save again.'), 'unavailable')

    def _apply(self, request):
        with request.lock:
            if request.cancelled or self._closing.is_set():
                request.done.set()
                return
            previous = self._status
            if request.enabled and previous.registered and request.shortcut == previous.shortcut:
                self._status = HotkeyStatus(True, request.shortcut, True)
            elif not request.enabled:
                if self._active_id is not None and not self._backend.unregister(self._active_id):
                    request.result = self._failure(ui_source('Cannot unregister the shortcut. Try again later.'), 'unregister_failed')
                else:
                    self._registered_ids.discard(self._active_id)
                    self._active_id = None
                    self._status = HotkeyStatus(False, request.shortcut, False)
            else:
                identity = 0x4E11 if self._active_id == 0x4E10 else 0x4E10
                if not self._backend.register(identity, request.modifiers, request.virtual_key):
                    request.result = self._failure(ui_source('The shortcut is occupied or cannot be registered. The previous one remains active; choose another combination.'), 'registration_failed')
                else:
                    self._registered_ids.add(identity)
                    if self._active_id is not None and not self._backend.unregister(self._active_id):
                        if self._backend.unregister(identity):
                            self._registered_ids.discard(identity)
                        request.result = self._failure(ui_source('Cannot replace the shortcut. The previous one remains active.'), 'unregister_failed')
                    else:
                        self._registered_ids.discard(self._active_id)
                        self._active_id = identity
                        self._status = HotkeyStatus(True, request.shortcut, True)
            request.result = request.result or self._status
            request.done.set()

    def _run(self):
        try:
            backend = self._factory()
            backend.start()
            self._backend = backend
            self._ready.set()
            while not self._closing.is_set():
                incoming = backend.receive()
                if incoming is None:
                    continue
                message, identity = incoming
                if message == WM_QUIT:
                    break
                if message == WM_COMMAND:
                    while True:
                        try:request = self._commands.get_nowait()
                        except queue.Empty:break
                        self._apply(request)
                elif message == WM_HOTKEY and identity == self._active_id and not self._closing.is_set():
                    try:self._callback()
                    except Exception:pass  # UI event sink failure must not leak a registration.
        except Exception:
            self._status = HotkeyStatus(False, self._status.shortcut, False,
                ui_source('Global shortcuts are unavailable. Change the combination and save again.'), 'unavailable')
        finally:
            if self._backend is not None:
                for identity in self._registered_ids:
                    try:self._backend.unregister(identity)
                    except Exception:pass
            self._registered_ids.clear()
            self._active_id = None
            self._status = HotkeyStatus(False, self._status.shortcut, False)
            self._ready.set()
            while True:
                try:request = self._commands.get_nowait()
                except queue.Empty:break
                request.result = self._failure(ui_source('The shortcut service is closed.'), 'closed')
                request.done.set()

    def close(self):
        with self._operations:
            self._closing.set()
            if self._backend is not None and self._thread.is_alive():
                try:self._backend.post(WM_QUIT)
                except Exception:pass  # The bounded message wait still observes _closing.
        if threading.current_thread() is not self._thread and self._thread.ident is not None:
            self._thread.join(1.0)
        return not self._thread.is_alive()
