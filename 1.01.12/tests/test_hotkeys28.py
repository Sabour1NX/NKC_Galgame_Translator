# SPDX-License-Identifier: MIT
"""Deterministic hotkey ownership/replacement tests; no actual key registration/input."""
import queue
import threading
import time

import pytest

from nkc_galgame_translator.hotkeys import (DEFAULT_HOTKEY, MOD_NOREPEAT, WM_COMMAND, WM_HOTKEY,
    GlobalHotkey, HotkeyValidationError, normalize_hotkey, parse_hotkey)
from nkc_galgame_translator.tuning import validate_tuning


class FakeWinApi:
    def __init__(self):
        self.messages=queue.Queue();self.registrations={};self.calls=[]
        self.fail_register=False;self.fail_unregister=set();self.fail_post=False
        self.owner=None;self.created=False
    def start(self):self.owner=threading.get_ident();self.created=True
    def post(self,message):
        assert self.created, 'Queue must exist before PostThreadMessage'
        if self.fail_post:return False
        self.messages.put((message,0));return True
    def receive(self):
        try:return self.messages.get(timeout=.03)
        except queue.Empty:return None
    def register(self,identity,modifiers,key):
        assert threading.get_ident()==self.owner
        self.calls.append(('register',identity,modifiers,key))
        if self.fail_register:return False
        self.registrations[identity]=(modifiers,key);return True
    def unregister(self,identity):
        assert threading.get_ident()==self.owner
        self.calls.append(('unregister',identity))
        if identity in self.fail_unregister:return False
        self.registrations.pop(identity,None);return True


@pytest.fixture
def service():
    backend=FakeWinApi();events=[]
    instance=GlobalHotkey(lambda:events.append(threading.get_ident()),_backend_factory=lambda:backend)
    yield instance,backend,events
    backend.fail_unregister.clear();backend.fail_post=False
    assert instance.close()
    assert not backend.registrations


@pytest.mark.parametrize('value,wanted',[
    ('Ctrl+Alt+R','Ctrl+Alt+R'),('alt + control + r','Ctrl+Alt+R'),
    ('shift+Ctrl+9','Ctrl+Shift+9'),('Alt+F24','Alt+F24'),('Ctrl+F1','Ctrl+F1')])
def test_canonical_combinations_and_repeat_suppression(value,wanted):
    assert normalize_hotkey(value)==wanted
    assert parse_hotkey(value)[1]&MOD_NOREPEAT


@pytest.mark.parametrize('value',[
    '',None,True,'R','Shift+R','Win+R','Ctrl+Ctrl+R','Ctrl++R','Ctrl+Alt',
    'Ctrl+A+B','Ctrl+Delete','Ctrl+F0','Alt+F25','Ctrl+F12','Alt+F4',
    'Ctrl+R\n','Ctrl+\uff32','Ctrl+R\x00','a'*65])
def test_invalid_or_reserved_combinations_are_rejected(value):
    with pytest.raises(HotkeyValidationError):normalize_hotkey(value)


def test_settings_validate_and_preserve_canonical_value():
    values=validate_tuning({'retranslate_hotkey_enabled':False,'retranslate_hotkey':'ALT + CTRL + r'})
    assert values['retranslate_hotkey_enabled'] is False
    assert values['retranslate_hotkey']=='Ctrl+Alt+R'
    assert validate_tuning({})['retranslate_hotkey']==DEFAULT_HOTKEY
    with pytest.raises(ValueError):validate_tuning({'retranslate_hotkey':'Win+R'})
    with pytest.raises(ValueError):validate_tuning({'retranslate_hotkey_enabled':1})


def test_hotkey_settings_survive_local_config_roundtrip(tmp_path):
    from nkc_galgame_translator.config_store import ConfigStore
    store=ConfigStore(tmp_path)
    values=validate_tuning({'retranslate_hotkey_enabled':False,'retranslate_hotkey':'shift+ctrl+8'})
    store.save({**store.load(),**values})
    reopened=ConfigStore(tmp_path).load()
    assert reopened['retranslate_hotkey_enabled'] is False
    assert reopened['retranslate_hotkey']=='Ctrl+Shift+8'
    assert not reopened.get('api_key')


def test_register_callback_thread_and_mod_norepeat(service):
    hotkey,api,events=service
    status=hotkey.update(True)
    assert status.ok and status.registered
    identity=next(iter(api.registrations))
    assert api.registrations[identity][0]&MOD_NOREPEAT
    api.messages.put((WM_HOTKEY,identity))
    until=time.monotonic()+1
    while not events and time.monotonic()<until:time.sleep(.005)
    assert events==[api.owner] and api.owner!=threading.get_ident()


def test_conflict_and_invalid_input_keep_old_registration(service):
    hotkey,api,events=service
    assert hotkey.update(True).ok
    original=dict(api.registrations)
    api.fail_register=True
    conflict=hotkey.update(True,'Ctrl+Alt+T')
    assert conflict.error_code=='registration_failed' and conflict.shortcut==DEFAULT_HOTKEY
    assert conflict.registered and api.registrations==original
    invalid=hotkey.update(True,'Win+R')
    assert invalid.error_code=='invalid' and api.registrations==original


def test_register_new_before_releasing_old_and_drop_stale_events(service):
    hotkey,api,events=service
    hotkey.update(True);old=next(iter(api.registrations));api.calls.clear()
    assert hotkey.update(True,'Ctrl+Alt+T').ok
    assert [call[0] for call in api.calls]==['register','unregister']
    assert len(api.registrations)==1 and old not in api.registrations
    new=next(iter(api.registrations))
    api.messages.put((WM_HOTKEY,old));api.messages.put((WM_HOTKEY,new))
    until=time.monotonic()+1
    while not events and time.monotonic()<until:time.sleep(.005)
    assert len(events)==1


def test_same_registration_is_idempotent_and_disable_removes_it(service):
    hotkey,api,events=service
    hotkey.update(True);before=list(api.calls)
    assert hotkey.update(True,'alt+ctrl+r').ok and api.calls==before
    status=hotkey.update(False)
    assert status.ok and not status.registered and not api.registrations


def test_failed_unregister_rolls_back_candidate(service):
    hotkey,api,events=service
    hotkey.update(True);old=next(iter(api.registrations));api.fail_unregister.add(old)
    status=hotkey.update(True,'Ctrl+Alt+T')
    assert status.error_code=='unregister_failed'
    assert status.shortcut==DEFAULT_HOTKEY and list(api.registrations)==[old]


def test_failed_post_cancels_request_and_close_has_idle_fallback(service):
    hotkey,api,events=service
    hotkey.update(True);before=dict(api.registrations)
    api.fail_post=True
    assert hotkey.update(True,'Ctrl+Alt+T').error_code=='post_failed'
    api.fail_post=False;api.post(WM_COMMAND)
    assert hotkey.update(True).ok and api.registrations==before
    api.fail_post=True
    assert hotkey.close() and not api.registrations
    assert hotkey.close()
    assert hotkey.update(True).error_code=='closed'


def test_post_exception_does_not_leave_an_armed_change_in_queue(service):
    hotkey,api,_=service
    hotkey.update(True);before=dict(api.registrations);original=api.post
    def failure(message):raise OSError('post failed')
    api.post=failure
    assert hotkey.update(True,'Ctrl+Alt+T').error_code=='post_failed'
    api.post=original
    assert hotkey.update(True).ok and api.registrations==before


def test_missing_winapi_is_nonfatal_and_has_no_callback():
    def missing():raise OSError('unavailable')
    service=GlobalHotkey(lambda:pytest.fail('callback must not run'),_backend_factory=missing)
    assert service.update(True).error_code=='unavailable'
    assert service.close()


def test_thread_creation_failure_does_not_break_application_startup(monkeypatch):
    def failure(self):raise RuntimeError('No thread resource')
    monkeypatch.setattr(threading.Thread,'start',failure)
    service=GlobalHotkey(lambda:None,_backend_factory=FakeWinApi)
    assert service.update(True).error_code=='unavailable'
    assert service.close()


def test_close_survives_post_exception_and_unregisters_on_owner_thread(service):
    hotkey,api,_=service
    hotkey.update(True)
    def failed(message):raise OSError('Queue unavailable')
    api.post=failed
    assert hotkey.close()
    assert not api.registrations


def test_callback_exception_does_not_kill_worker():
    api=FakeWinApi();called=threading.Event()
    def callback():called.set();raise ValueError('UI event sink rejected')
    service=GlobalHotkey(callback,_backend_factory=lambda:api)
    try:
        service.update(True);api.messages.put((WM_HOTKEY,next(iter(api.registrations))))
        assert called.wait(1)
        assert service.update(False).ok
    finally:assert service.close()
