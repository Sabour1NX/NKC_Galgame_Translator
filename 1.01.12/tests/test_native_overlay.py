# SPDX-License-Identifier: MIT
"""Real GDI/Win32 overlay regression tests, using synthetic text and no input/API."""
import ctypes
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows native compositor')

from nkc_galgame_translator.native import NativeCore


@pytest.fixture
def core():
    dll=Path(__file__).resolve().parents[1]/'native/bin/nkc_galgame_translator_core.dll'
    if not dll.exists():pytest.skip('Build the native DLL before the native test suite')
    with NativeCore(dll) as instance:
        yield instance


def region(identity=1,revision=1,text='\u6b22\u8fce',**changes):
    user=ctypes.windll.user32
    # Small synthetic overlays, never activate or send user input to any window.
    result={'x':user.GetSystemMetrics(76)+30,'y':user.GetSystemMetrics(77)+30,
            'w':220,'h':65,'font_size':28,'bg':[30,30,30],
            'text':text,'final':False,'_track_id':identity,'_revision':revision}
    result.update(changes)
    return result


def render(core,regions):
    previous=core.overlay_snapshot()['sequence']
    core.show_overlay(regions)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        state=core.overlay_snapshot()
        expected=[(r.get('_track_id',0),r.get('_revision',0),len(r['text'].encode('utf-16-le'))//2)
                  for r in regions]
        observed=[(r['track_id'],r['revision'],r['text_units']) for r in state['regions']]
        if state['sequence']>previous and observed==expected:
            return state['regions']
        time.sleep(.005)
    pytest.fail('The native overlay did not complete its render')


def test_stream_updates_reuse_one_offscreen_buffer_and_commit_complete_frames(core):
    item=region(501,w=360,h=100,text='\u521d',final=False)
    first=render(core,[item])[0]
    assert first['paint']['buffered'] and first['paint']['size']==[360,100]
    allocations=first['paint']['buffer_allocations']
    commits=first['paint']['commits']
    assert allocations>=1 and commits>=1
    for text in ('\u521d\u59cb','\u521d\u59cb\u6587\u5b57','\u521d\u59cb\u6587\u5b57\u6b63\u5728','\u521d\u59cb\u6587\u5b57\u6b63\u5728\u8fde\u7eed\u8f93\u51fa\u3002'):
        current=render(core,[{**item,'text':text}])[0]
        assert current['hwnd']==first['hwnd']
        assert current['paint']['buffered']
        assert current['paint']['buffer_allocations']==allocations
        assert current['paint']['commits']>commits
        assert current['fits']
        commits=current['paint']['commits']
    final=render(core,[{**item,'text':text,'final':True,'bg':[31,35,39]}])[0]
    assert final['paint']['buffered'] and final['paint']['commits']>commits
    assert final['paint']['buffer_allocations']==allocations


def test_offscreen_buffer_tracks_size_but_not_position_or_font_changes(core):
    item=region(502,w=350,h=90,text='Text and \u6587\u5b57',final=True)
    first=render(core,[item])[0]
    moved=render(core,[{**item,'x':item['x']+9}])[0]
    assert moved['paint']['buffer_allocations']==first['paint']['buffer_allocations']
    changed=render(core,[{**item,'w':380,'h':110,'font_size':24}])[0]
    assert changed['paint']['buffered'] and changed['paint']['size']==[380,110]
    assert changed['paint']['buffer_allocations']==first['paint']['buffer_allocations']+1
    smaller=render(core,[{**item,'w':300,'h':80}])[0]
    assert smaller['paint']['buffered'] and smaller['paint']['size']==[300,80]
    assert smaller['paint']['buffer_allocations']==changed['paint']['buffer_allocations']+1
    changed_font=render(core,[{**item,'w':300,'h':80,'font_size':22}])[0]
    assert changed_font['paint']['buffer_allocations']==smaller['paint']['buffer_allocations']


def test_repeated_resize_and_destroy_release_gdi_buffers(core):
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    user.GetGuiResources.argtypes=[ctypes.c_void_p,ctypes.c_uint]
    user.GetGuiResources.restype=ctypes.c_uint
    process=kernel.GetCurrentProcess()
    # Warm font caches before comparing the current process's GDI handles.
    render(core,[region(503,text='\u8986\u76d6\u6587\u5b57',final=True)]);render(core,[])
    baseline=user.GetGuiResources(process,0)
    assert baseline>0
    for index in range(24):
        objects=[region(510+part,text='\u8986\u76d6\u6587\u5b57',final=True,w=200+(index%5)*11,
                        h=60+(index%3)*5,y=40+part*100) for part in range(2)]
        shown=render(core,objects)
        assert all(item['paint']['buffered'] for item in shown)
        if index%4==3:render(core,[])
    render(core,[])
    assert user.GetGuiResources(process,0)<=baseline+2


def displayed_lines(text,snapshot):
    """Native diagnostics index UTF-16 units after CR removal, without text."""
    encoded=text.replace('\r','').encode('utf-16-le')
    return [encoded[line['start']*2:(line['start']+line['length'])*2].decode('utf-16-le')
            for line in snapshot['lines']]


@pytest.mark.parametrize('text',[
    '\u8230\u957f Alex \u53d1\u73b0\u4e86\u524d\u65b9\u6f02\u6d6e\u7684\u5c0f\u98de\u8239\uff0c\u7acb\u523b\u51c6\u5907\u6551\u63f4\u3002',
    '\u82f1\u8bed: \u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986\uff0c\u8bf7\u6536\u96c6\u94a5\u5319\u524d\u5f80\u51fa\u53e3\u3002',
])
def test_mixed_chinese_uses_available_width_after_an_earlier_space(core,text):
    core.set_overlay_font('SimSun');wait_font(core,'SimSun')
    result=render(core,[region(text=text,w=244,h=180,font_size=20,final=True)])[0]
    rows=displayed_lines(text,result)
    assert result['font_px']==20 and result['fits'],result
    assert len(rows)>=2
    # A space in a label/name must not strand a short prefix on its own line.
    assert result['lines'][0]['width']>=180,rows
    assert '\u53d1\u73b0\u4e86' in rows[0] or '\u6b22\u8fce\u6765\u5230' in rows[0],rows
    assert ''.join(rows).replace(' ','')==text.replace(' ','')


def test_latin_words_wrap_at_word_start_even_after_chinese(core):
    core.set_overlay_font('SimSun');wait_font(core,'SimSun')
    text='\u98de\u8239 PRINCESS BLUE \u5df2\u7ecf\u5230\u8fbe\u3002'
    result=render(core,[region(text=text,w=150,h=180,font_size=20,final=True)])[0]
    rows=displayed_lines(text,result)
    assert result['fits']
    assert any('PRINCESS' in row for row in rows),rows
    assert any('BLUE' in row for row in rows),rows
    assert ''.join(rows).replace(' ','')==text.replace(' ','')


@pytest.mark.parametrize('text,prefix',[
    ('\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986\uff0c\u8bf7\u7ee7\u7eed\u524d\u884c\u3002','\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986'),
    ('\u6b22\u8fce\u8fdb\u5165\u300c\u7ea2\u9b54\u9986\u300d\u7ee7\u7eed\u5192\u9669\u3002','\u6b22\u8fce\u8fdb\u5165\u300c'),
])
def test_cjk_closing_punctuation_stays_with_preceding_glyph_and_opening_with_next(core,text,prefix):
    core.set_overlay_font('SimSun');wait_font(core,'SimSun')
    measured=render(core,[region(text=prefix,w=600,h=80,font_size=20,final=True)])[0]
    width=measured['lines'][0]['width']+4
    result=render(core,[region(revision=2,text=text,w=width,h=200,font_size=20,final=True)])[0]
    rows=displayed_lines(text,result)
    assert result['font_px']==20 and result['fits'],result
    assert len(rows)>1
    assert all(not row.startswith(('\uff0c','\u3002','\u300d')) and not row.endswith('\u300c') for row in rows),rows
    assert ''.join(rows)==text


def test_tiny_rectangle_never_splits_utf16_surrogate_pair(core):
    text='\U0001f600\U0001f680'
    result=render(core,[region(text=text,w=5,h=120,font_size=20,final=True)])[0]
    # Even with less width than any glyph, each row is valid Unicode and the
    # compositor truthfully reports the overflow at the existing 8px floor.
    assert displayed_lines(text,result)==list(text)
    assert result['font_px']==8 and not result['fits']


def test_native_wrap_preserves_explicit_breaks_and_long_word_makes_progress(core):
    text='First\r\n\nSupercalifragilisticexpialidocious\n\u6700\u540e\u4e00\u884c'
    result=render(core,[region(text=text,w=150,h=240,font_size=20,final=True)])[0]
    rows=displayed_lines(text,result)
    assert result['fits']
    assert rows[0]=='First' and rows[-1]=='\u6700\u540e\u4e00\u884c'
    assert result['lines'][1]['y']-result['lines'][0]['y']==2*result['lines'][0]['height']
    assert ''.join(rows)==text.replace('\r','').replace('\n','')


def test_stream_font_never_enlarges_on_geometry_noise_position_or_final(core):
    text='\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986\uff0c\u8bf7\u6536\u96c6\u94a5\u5319\u5e76\u524d\u5f80\u51fa\u53e3\u3002'
    sizes=[]
    item=region()
    for count in (1,4,9,len(text)):
        item={**item,'text':text[:count]}
        result=render(core,[item])[0]
        sizes.append(result['font_px'])
    assert sizes==sorted(sizes,reverse=True),sizes
    assert sizes[-1]<sizes[0],sizes
    baseline=sizes[-1]
    for dx,width,height in ((1,222,66),(-1,220,65),(2,224,67),(0,220,65)):
        current=render(core,[{**item,'x':item['x']+dx,'w':width,'h':height,'final':True}])[0]
        assert current['font_px']==baseline,current
        assert current['fits']
        assert current['bounds']==[item['x']+dx,item['y'],width,height]
    for _ in range(3):
        assert render(core,[{**item,'final':True}])[0]['font_px']==baseline


def wait_font(core,family):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        state=core.overlay_snapshot()
        if state.get('font_family')==family:return state
        time.sleep(.005)
    pytest.fail('Font setting was not consumed by compositor')


def test_font_change_repaints_existing_regions_and_uses_selected_gdi_face(core):
    item=region(text='English letters wrap across lines in the selected face.',w=240,h=100)
    first=render(core,[item])[0]
    core.set_overlay_font('Consolas')
    changed=wait_font(core,'Consolas')
    assert changed['regions'][0]['track_id']==first['track_id']
    assert changed['regions'][0]['font_face']=='Consolas'
    assert changed['regions'][0]['fits']
    core.set_overlay_font('SimSun')
    chinese=render(core,[{**item,'text':'\u7b2c\u4e00\u884c\u4e2d\u6587\n\u7b2c\u4e8c\u884c\uff0c\u81ea\u52a8\u9002\u5e94\u5b57\u4f53\u3002','_revision':2}])[0]
    assert core.overlay_snapshot()['font_family']=='SimSun'
    assert chinese['font_face'] in ('SimSun','\u5b8b\u4f53')
    assert chinese['fits'] and len(chinese['lines'])>=2


def test_same_font_preserves_fit_and_new_font_resets_missing_history(core):
    core.set_overlay_font('Consolas');wait_font(core,'Consolas')
    item=region(text='A rather long line must shrink to fit this tiny rectangle.',w=100,h=40)
    small=render(core,[item])[0]
    assert small['font_px']<28
    sequence=core.overlay_snapshot()['sequence']
    core.set_overlay_font('Consolas')
    assert core.overlay_snapshot()['sequence']==sequence
    large={**item,'w':600,'h':150}
    assert render(core,[large])[0]['font_px']==small['font_px']
    render(core,[])
    core.set_overlay_font('Arial');wait_font(core,'Arial')
    reset=render(core,[large])[0]
    assert reset['font_px']==28 and reset['font_face']=='Arial'


@pytest.mark.parametrize('family',[None,1,'',' ','\u3000','\u2002','A'*32,'A\x00B','A\nB','A\x7fB','A\u200bB','\ud800','\U0001f600'*16])
def test_invalid_python_font_cannot_change_compositor(core,family):
    before=core.overlay_snapshot()
    with pytest.raises(ValueError):core.set_overlay_font(family)
    assert core.overlay_snapshot()==before


def test_direct_c_font_bounds_and_atomic_failure(core):
    before=core.overlay_snapshot()
    for family in (None,'',' ','\u2002','A'*32,'A\nB','A\x85B','\ud800','\udc00'):
        assert core._dll.gl_set_font(core._context,family)==0
        assert core.overlay_snapshot()==before
    assert core._dll.gl_set_font(None,'Arial')==0
    # 31 UTF-16 units, including one valid non-BMP pair, remains bounded and
    # allowed as a family request. GDI may substitute if it is not installed.
    family='A'*29+'\U0001f600'
    assert core._dll.gl_set_font(core._context,family)==1
    assert wait_font(core,family)['font_family']==family


def test_font_setter_requires_live_context(core):
    core.close()
    with pytest.raises(RuntimeError,match='closed'):core.set_overlay_font('Arial')


def test_abi2_without_font_export_rejected_before_context_creation(tmp_path,monkeypatch):
    path=tmp_path/'old-abi2.dll';path.touch()
    def abi_version():return 2
    monkeypatch.setattr(ctypes,'CDLL',lambda path,**kwargs:SimpleNamespace(gl_abi_version=abi_version))
    with pytest.raises(RuntimeError,match='\u539f\u751f\u6838\u5fc3\u7248\u672c\u4e0d\u5339\u914d'):NativeCore(path)


def test_reorder_and_disappearance_preserve_the_correct_object_window_and_font(core):
    long=region(11,text='\u4e00\u6bb5\u5f88\u957f\u7684\u8bd1\u6587\u9700\u8981\u964d\u4f4e\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u653e\u8fdb\u8f83\u5c0f\u7684\u6587\u5b57\u6846\u3002',w=130,h=55)
    short=region(22,text='\u5f00\u59cb',y=long['y']+90)
    first=render(core,[long,short]);by_id={r['track_id']:r for r in first}
    assert by_id[11]['font_px']<by_id[22]['font_px']
    second=render(core,[short,long])
    for actual in second:
        previous=by_id[actual['track_id']]
        assert actual['hwnd']==previous['hwnd']
        assert actual['font_px']==previous['font_px']
    remaining=render(core,[short])[0]
    assert remaining['hwnd']==by_id[22]['hwnd']
    assert remaining['font_px']==by_id[22]['font_px']
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.IsWindow.argtypes=[ctypes.c_void_p]
    assert not user.IsWindow(by_id[11]['hwnd'])


def test_new_revision_changed_text_and_new_target_reset_font_fit(core):
    original=region(42,text='\u4e00\u6bb5\u5f88\u957f\u7684\u8bd1\u6587\u9700\u8981\u964d\u4f4e\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u653e\u8fdb\u8f83\u5c0f\u7684\u6587\u5b57\u6846\u3002',w=130,h=55)
    small=render(core,[original])[0]
    assert small['font_px']<28
    # Prefix growth keeps the small size even if its available area increases.
    grown={**original,'w':400,'h':100}
    assert render(core,[grown])[0]['font_px']==small['font_px']
    revised=render(core,[{**grown,'_revision':2}])[0]
    assert revised['font_px']>small['font_px']
    render(core,[{**original,'_revision':2}])
    replaced=render(core,[{**original,'_revision':2,'text':'\u5f00\u59cb'}])[0]
    assert replaced['font_px']==28
    render(core,[original])
    core.set_target(0,0)  # Reset the same numeric IDs for a new capture session.
    reset=render(core,[grown])[0]
    assert reset['font_px']>small['font_px']


def test_partial_mask_final_full_cover_newlines_and_clickthrough(core):
    user=ctypes.WinDLL('user32',use_last_error=True)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    user.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    user.GetWindowLongW.argtypes=[ctypes.c_void_p,ctypes.c_int]
    user.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
    user.SendMessageW.restype=ctypes.c_ssize_t
    user.GetWindowDisplayAffinity.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint)]
    user.GetForegroundWindow.restype=ctypes.c_void_p
    gdi.CreateRectRgn.argtypes=[ctypes.c_int]*4;gdi.CreateRectRgn.restype=ctypes.c_void_p
    gdi.GetRgnBox.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    gdi.DeleteObject.argtypes=[ctypes.c_void_p]
    foreground=user.GetForegroundWindow()
    item=region(77,text='',w=250,h=180)
    empty=render(core,[item])[0]
    mask=gdi.CreateRectRgn(0,0,0,0)
    try:
        assert user.GetWindowRgn(empty['hwnd'],mask)==1  # NULLREGION: no source erased.
        item['text']='\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c\u6587\u5b57\u81ea\u52a8\u6362\u884c\nEnglish words wrap in this small rectangle.'
        partial=render(core,[item])[0]
        assert len(partial['lines'])>=3 and partial['fits']
        assert user.GetWindowRgn(partial['hwnd'],mask) in (2,3)
        box=(ctypes.c_long*4)();gdi.GetRgnBox(mask,box)
        assert tuple(box)!=(0,0,item['w'],item['h'])
        final=render(core,[{**item,'final':True}])[0]
        assert final['font_px']==partial['font_px'] and final['fits']
        assert user.GetWindowRgn(final['hwnd'],mask)==0  # No custom mask: entire rectangle.
        style=user.GetWindowLongW(final['hwnd'],-20)
        assert style&0x20 and style&0x08000000  # WS_EX_TRANSPARENT / WS_EX_NOACTIVATE
        assert user.SendMessageW(final['hwnd'],0x84,0,0)==-1  # WM_NCHITTEST / HTTRANSPARENT
        affinity=ctypes.c_uint()
        assert user.GetWindowDisplayAffinity(final['hwnd'],ctypes.byref(affinity)) and affinity.value==0x11
        assert user.GetForegroundWindow()==foreground
    finally:gdi.DeleteObject(mask)


def test_duplicate_identity_rejected_and_untracked_replacement_does_not_inherit_fit(core):
    item=region(9)
    with pytest.raises(RuntimeError,match='Duplicate'):
        core.show_overlay([item,{**item,'y':item['y']+100}])
    long=region(0,text='\u4e00\u6bb5\u5f88\u957f\u7684\u8bd1\u6587\u9700\u8981\u964d\u4f4e\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u653e\u8fdb\u8f83\u5c0f\u7684\u6587\u5b57\u6846\u3002',w=130,h=55)
    assert render(core,[long])[0]['font_px']<28
    assert render(core,[{**long,'w':400,'h':100}])[0]['font_px']==28
    assert render(core,[{**long,'text':'\u5f00\u59cb'}])[0]['font_px']==28


def test_missing_object_restores_its_font_without_retaining_windows_and_hide_resets(core):
    user=ctypes.WinDLL('user32',use_last_error=True);user.IsWindow.argtypes=[ctypes.c_void_p]
    item=region(55,text='\u4e00\u6bb5\u5f88\u957f\u7684\u8bd1\u6587\u9700\u8981\u964d\u4f4e\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u653e\u8fdb\u8f83\u5c0f\u7684\u6587\u5b57\u6846\u3002',w=130,h=55)
    first=render(core,[item])[0]
    assert first['font_px']<28
    assert render(core,[])==[]
    assert not user.IsWindow(first['hwnd'])
    enlarged={**item,'w':400,'h':100}
    restored=render(core,[enlarged])[0]
    assert restored['font_px']==first['font_px']
    render(core,[])
    changed=render(core,[{**enlarged,'_revision':2}])[0]
    assert changed['font_px']==28
    render(core,[item]);render(core,[])
    core.hide_overlay()
    assert render(core,[enlarged])[0]['font_px']==28


def test_missing_font_history_expires_and_has_a_fixed_capacity(core):
    item=region(88,text='\u4e00\u6bb5\u5f88\u957f\u7684\u8bd1\u6587\u9700\u8981\u964d\u4f4e\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u653e\u8fdb\u8f83\u5c0f\u7684\u6587\u5b57\u6846\u3002',w=130,h=55)
    small=render(core,[item])[0]
    assert small['font_px']<28
    render(core,[])
    time.sleep(3.1)
    assert render(core,[{**item,'w':400,'h':100}])[0]['font_px']==28
    # All are at the same small synthetic location; no input/focus changes.
    render(core,[{**item,'_track_id':identity} for identity in range(100,165)])
    render(core,[])
    oldest=render(core,[{**item,'_track_id':100,'w':400,'h':100}])[0]
    newest=render(core,[{**item,'_track_id':164,'w':400,'h':100}])[0]
    assert oldest['font_px']==28 and newest['font_px']==small['font_px']


@pytest.mark.parametrize('version',[None,1])
def test_incompatible_native_abi_rejected_before_context_creation(tmp_path,monkeypatch,version):
    old=tmp_path/'old-core.dll';old.touch()
    def abi_version():return version
    library=SimpleNamespace(**({'gl_abi_version':abi_version} if version is not None else {}))
    monkeypatch.setattr(ctypes,'CDLL',lambda path,**kwargs:library)
    with pytest.raises(RuntimeError,match='\u539f\u751f\u6838\u5fc3\u7248\u672c\u4e0d\u5339\u914d'):
        NativeCore(old)
