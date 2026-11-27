# SPDX-License-Identifier: MIT
"""Adversarial file/IPC/ABI cases; no remote fetch or game interaction."""
import ctypes
import importlib.util
import io
import json
from pathlib import Path
import struct
import threading

import pytest
from PIL import Image

from nkc_galgame_translator.dictionary_import import parse_dictionary, DictionaryImportError
from nkc_galgame_translator.input_paths import local_file_path
from nkc_galgame_translator.native import NativeCore, _Region
from nkc_galgame_translator.ocr import PortableOcr, validate_response

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('independent_ocr_helper',ROOT/'tools/ocr_helper.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


@pytest.mark.parametrize('path', [r'\\server\private\x.csv',r'\\?\C:\x.csv',r'\\.\pipe\x.csv',
    r'C:\temp\x.csv:payload.csv',r'C:\temp\CON.csv',r'C:\temp\LPT1.csv','https://host/x.csv','x\x00.csv'])
def test_remote_device_and_ads_rejected_before_filesystem_access(monkeypatch,path):
    def unexpected(*a,**kw):raise AssertionError('Must reject before path access')
    monkeypatch.setattr(Path,'lstat',unexpected)
    monkeypatch.setattr(Path,'stat',unexpected)
    with pytest.raises(DictionaryImportError):parse_dictionary(path,'en','zh-Hans')


def test_symlink_or_reparse_input_rejected(tmp_path,monkeypatch):
    item=tmp_path/'x.csv';item.write_text('source,target\nStart,\u5f00\u59cb',encoding='utf-8')
    old=Path.lstat
    def info(path):
        value=old(path)
        if path==item:
            from types import SimpleNamespace
            return SimpleNamespace(st_mode=value.st_mode,st_file_attributes=0x400)
        return value
    monkeypatch.setattr(Path,'lstat',info)
    with pytest.raises(ValueError):local_file_path(item)


def test_json_depth_bounded_before_decoder_and_literals_remain_plain_data(tmp_path,monkeypatch):
    item=tmp_path/'x.json';item.write_text('['*17+'0'+']'*17)
    def unexpected(*a,**kw):raise AssertionError('Must reject before allocating decoder tree')
    with monkeypatch.context() as patch:
        patch.setattr(json,'loads',unexpected)
        with pytest.raises(DictionaryImportError):parse_dictionary(item,'en','zh-Hans')
    entries={'__import__("os").system("bad")':'DROP TABLE glossary; -- [{{{' }
    item.write_text(json.dumps(entries),encoding='utf-8')
    assert parse_dictionary(item,'en','zh-Hans')==[{'source':k,'target':v} for k,v in entries.items()]


@pytest.mark.parametrize('bounds',[(-2**40,0,20,20),(0,0,-1,20),(0,0,4097,20),(0,0,True,20),(0,0,2.5,20),(2**31-1,0,1,20)])
def test_capture_bounds_rejected_before_ctypes_or_buffer_allocation(bounds):
    core=NativeCore.__new__(NativeCore)
    with pytest.raises(ValueError):core.capture_bgra(*bounds)
    with pytest.raises(ValueError):core.capture_ocr(*bounds)


@pytest.mark.parametrize('change',[{'x':2**32},{'w':-1},{'h':8193},{'_track_id':-1},{'_revision':2**64},
    {'text':'a\x00b'},{'text':'\ud800'},{'text':'x'*64001},{'text':'😀'*32001},{'font_size':513}])
def test_overlay_rejects_wrapping_and_unbounded_text_before_native_call(change):
    core=NativeCore.__new__(NativeCore)
    region={'x':0,'y':0,'w':100,'h':30,'text':'\u5f00\u59cb',**change}
    with pytest.raises(ValueError):core.show_overlay([region])


def test_dll_uses_absolute_local_path_and_restricted_dependency_search(monkeypatch):
    original=ctypes.CDLL;calls=[]
    def load(path,*args,**kwargs):
        calls.append((path,kwargs));return original(path,*args,**kwargs)
    monkeypatch.setattr(ctypes,'CDLL',load)
    with NativeCore() as core:assert core.languages()
    assert Path(calls[0][0]).is_absolute()
    assert calls[0][1]['winmode']==0x900


def test_raw_c_abi_bounds_text_without_mutating_overlay():
    with NativeCore() as core:
        before=core.overlay_snapshot()['sequence']
        regions=(_Region*1)(_Region(0,0,100,30,0,0,12,1,'X'*64001,99,1))
        assert core._dll.gl_overlay(core._context,regions,1)==0
        assert b'exceeds limit' in core._dll.gl_error()
        assert core.overlay_snapshot()['sequence']==before


def valid_response():return {'lines':[{'text':'Start','x':1,'y':1,'w':9,'h':9,'confidence':90}], 'ocr_ms':2.5}


@pytest.mark.parametrize('change',[{'text':'\ud800'},{'text':'a\x00b'},{'text':'a'*16001},{'x':-1},
    {'w':1000},{'w':0},{'h':2.5},{'confidence':float('nan')},{'confidence':101}])
def test_invalid_helper_line_cannot_reach_drawing(change):
    value=valid_response();value['lines'][0].update(change)
    with pytest.raises(RuntimeError):validate_response(value,100,100)


@pytest.mark.parametrize('value',[None,[],{'error':'private sentinel path'}, {'lines':[], 'ocr_ms':float('inf')},
    {'lines':[],'ocr_ms':True}, {'lines':[{}]*513,'ocr_ms':1}])
def test_response_envelope_errors_are_bounded_and_sanitized(value):
    with pytest.raises(RuntimeError) as error:validate_response(value,100,100)
    assert 'sentinel' not in str(error.value)


def test_response_preserves_valid_newlines():
    value=valid_response();value['lines'][0]['text']='First\nSecond'
    assert validate_response(value,100,100)==value


def bmp(tmp_path):
    path=tmp_path/'frame.bmp';Image.new('RGB',(32,16),'white').save(path)
    return path


@pytest.mark.parametrize('kind',['png','jp2-header','oversize','compression','truncated','extra-data','offset','outside'])
def test_helper_rejects_other_formats_and_bmp_bombs(tmp_path,kind):
    path=bmp(tmp_path)
    if kind=='png':Image.new('RGB',(32,16)).save(path,format='PNG')
    elif kind=='jp2-header':path.write_bytes(b'\x00\x00\x00\x0cjP  \r\n\x87\n'+b'x'*80)
    elif kind=='outside':
        with pytest.raises(ValueError):helper.load_image(str(path),tmp_path/'other')
        return
    else:
        data=bytearray(path.read_bytes())
        if kind=='oversize':struct.pack_into('<i',data,18,100000)
        if kind=='compression':struct.pack_into('<I',data,30,1)
        if kind=='truncated':data=data[:-3]
        if kind=='extra-data':data+=b'trailing'
        if kind=='offset':struct.pack_into('<I',data,10,2**32-1)
        path.write_bytes(data)
    with pytest.raises(ValueError):helper.load_image(str(path),tmp_path)


def test_helper_loads_bounded_rgb_frame(tmp_path):
    with helper.load_image(str(bmp(tmp_path)),tmp_path) as image:
        assert image.mode=='RGB' and image.size==(32,16)


def test_rgb_transfer_uses_raw_pixels_without_leptonica_format_detection():
    class Engine:
        def SetImage(self,*args):raise AssertionError('Generic image decoder must not run')
        def SetImageFile(self,*args):raise AssertionError('File decoder must not run')
        def SetImageBytes(self,*args):self.args=args
    engine=Engine();image=Image.new('RGB',(3,2),(1,2,3))
    retained=helper.set_rgb_image(engine,image)
    assert engine.args==(bytes([1,2,3])*6,3,2,3,9)
    assert engine.args[0] is retained


def test_oversized_image_rejected_without_spawning(tmp_path):
    ocr=PortableOcr(tmp_path)
    with pytest.raises(ValueError):ocr.recognize(Image.new('RGB',(4097,1)))
    assert ocr._process is None


def test_helper_reader_limits_lines_and_ignores_python_environment(tmp_path,monkeypatch):
    ocr=PortableOcr(tmp_path);monkeypatch.setattr(ocr,'available',lambda:True)
    monkeypatch.setenv('PYTHONPATH','untrusted-path')
    monkeypatch.setenv('PYTHONHOME','untrusted-home')
    class Output(io.StringIO):
        sizes=[]
        def readline(self,size=-1):self.sizes.append(size);return super().readline(size)
    class Process:
        stdout=Output('x'*1048578+'\n');stdin=io.StringIO()
        def poll(self):return 0
    calls=[]
    def spawn(command,**kwargs):calls.append((command,kwargs));return Process()
    monkeypatch.setattr('nkc_galgame_translator.ocr.subprocess.Popen',spawn)
    try:
        ocr._start()
        result=ocr._responses.get(timeout=3)
        assert 'error' in result
        assert Process.stdout.sizes==[1048577]
        assert '-I' in calls[0][0] and '--input-root' in calls[0][0]
        assert 'PYTHONPATH' not in calls[0][1]['env'] and 'PYTHONHOME' not in calls[0][1]['env']
    finally:ocr.close()
