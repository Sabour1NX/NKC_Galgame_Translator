# SPDX-License-Identifier: MIT
"""Language enumeration stays MTA-safe after Tk initializes the UI as STA."""
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from nkc_galgame_translator.native import NativeCore


def mock_core(languages, destroy=lambda _:None):
    core=NativeCore.__new__(NativeCore)
    core._dll=SimpleNamespace(gl_languages=languages, gl_destroy=destroy)
    core._context=1
    core._lifecycle=threading.Condition(threading.RLock())
    core._active_operations=0
    core._closing=False
    return core


def test_languages_reuses_one_distinct_worker_and_returns_after_decode():
    caller=threading.get_ident();operations=[]
    core=mock_core(lambda:operations.append(threading.get_ident()) or b'["en-US"]')
    assert core.languages()==['en-US']
    assert core.languages()==['en-US']
    assert operations[0]!=caller
    assert operations[1]==operations[0]
    assert core._active_operations==0
    assert len([t for t in threading.enumerate() if t.name.startswith('ocr-language-mta')])==1
    core.close()


def test_close_waits_for_language_enumeration_decode():
    started,release,destroyed=threading.Event(),threading.Event(),threading.Event()
    def enumerate_languages():
        started.set()
        assert release.wait(3)
        return b'["en-US"]'
    core=mock_core(enumerate_languages,lambda _:destroyed.set())
    results=[]
    caller=threading.Thread(target=lambda:results.append(core.languages()))
    caller.start();assert started.wait(2)
    closer=threading.Thread(target=core.close);closer.start()
    assert not destroyed.wait(.05)
    release.set();caller.join(3);closer.join(3)
    assert results==[['en-US']] and destroyed.is_set()
    assert not caller.is_alive() and not closer.is_alive()
    assert core._active_operations==0 and core._context is None


def test_enumeration_error_propagates_and_releases_lifecycle_pin():
    core=mock_core(lambda:b'{"error":"expected enumeration failure"}')
    with pytest.raises(RuntimeError,match='expected enumeration failure'):core.languages()
    assert core._active_operations==0
    core.close()
    with pytest.raises(RuntimeError,match='closed'):core.languages()


def test_real_hidden_tk_then_ocr_core_languages():
    root=Path(__file__).resolve().parents[1]
    code=r'''
import ctypes
import tkinter as tk
from nkc_galgame_translator.ocr import OcrCore
window=tk.Tk();window.withdraw()
core=None
ole=ctypes.WinDLL('ole32')
ole.CoInitializeEx.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
ole.CoInitializeEx.restype=ctypes.c_long
# Some Tk code paths initialize STA only after clipboard/shell use. Make that
# real COM state explicit without interacting with the user's clipboard.
initialized=ole.CoInitializeEx(None,2)
assert initialized in (0,1)
try:
    apartment=ctypes.c_int();qualifier=ctypes.c_int()
    ole.CoGetApartmentType.argtypes=[ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int)]
    ole.CoGetApartmentType.restype=ctypes.c_long
    assert ole.CoGetApartmentType(ctypes.byref(apartment),ctypes.byref(qualifier))==0
    assert apartment.value in (0,3),apartment.value
    # Repeated create/query/close reproduced an access violation on query 2
    # with short-lived MTA workers. The shared worker must survive core.close.
    for iteration in range(100):
        core=OcrCore()
        assert isinstance(core.languages(),list) and core.languages()
        assert isinstance(core.native.languages(),list)
        core.close();core=None
finally:
    if core:core.close()
    window.destroy()
    ole.CoUninitialize()
'''
    result=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=root,
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,result.stderr
