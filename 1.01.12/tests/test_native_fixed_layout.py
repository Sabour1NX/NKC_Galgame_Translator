# SPDX-License-Identifier: MIT
"""Actual GDI fixed-row fitting without API calls or game input."""
import ctypes
import pytest

from test_native_overlay import core, region, render
from nkc_galgame_translator.native import _Region, _SourceRow


def fixed(text='\u8d27\u7269', **changes):
    result=region(text=text,w=250,h=35,font_size=0,final=True,_fixed_layout=True,
        _source_rows=[dict(x=0,y=0,w=250,h=35,ink_bounds=[2,2,245,30],font_size=0)])
    result.update(changes)
    return result


def test_fixed_one_row_uses_original_rectangle_and_ink_height_then_spaces(core):
    item=fixed()
    result=render(core,[item])[0]
    assert result['fits'] and result['fixed_layout'] and result['source_rows']==1
    assert result['bounds']==[item['x'],item['y'],250,35]
    line=result['lines'][0]
    assert line['x']==2 and line['ink_y']==2 and line['width']==245
    assert 27<=line['ink_height']<=30
    assert line['clip']==[0,0,250,35]


def test_overlong_translation_shrinks_without_adding_rows(core):
    short=render(core,[fixed()])[0]
    long=render(core,[fixed(text='\u8fd9\u662f\u4e00\u6bb5\u66f4\u957f\u7684\u8d27\u7269\u540d\u79f0\uff0c\u9700\u8981\u7f29\u5c0f\u5b57\u53f7\u624d\u80fd\u653e\u8fdb\u539f\u6765\u7684\u4e00\u884c\u3002',_revision=2)])[0]
    assert long['fits'] and len(long['lines'])==1
    assert long['font_px']<short['font_px']
    assert long['lines'][0]['width']==245


def test_multirow_exact_source_positions_and_explicit_breaks(core):
    rows=[dict(x=2,y=3,w=246,h=34,ink_bounds=[4,5,240,29],font_size=0),
          dict(x=20,y=55,w=200,h=34,ink_bounds=[22,57,194,29],font_size=0)]
    item=fixed('\u7b2c\u4e00\u884c\u6587\u5b57\n\u7b2c\u4e8c\u884c\u6587\u5b57',h=92,_source_rows=rows)
    result=render(core,[item])[0]
    assert result['fits'] and result['source_rows']==2 and len(result['lines'])==2
    assert [(v['x'],v['ink_y'],v['width'],v['length']) for v in result['lines']]==[
        (4,5,240,5),(22,57,194,5)]
    # Final coverage is the union of source rows, not the paragraph's blank gap.
    gdi=ctypes.windll.gdi32;user=ctypes.windll.user32
    gdi.CreateRectRgn.restype=ctypes.c_void_p
    gdi.PtInRegion.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    gdi.DeleteObject.argtypes=[ctypes.c_void_p]
    user.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    mask=gdi.CreateRectRgn(0,0,0,0)
    try:
        assert user.GetWindowRgn(result['hwnd'],mask)>0
        assert gdi.PtInRegion(mask,10,10)
        assert not gdi.PtInRegion(mask,10,45)
        assert gdi.PtInRegion(mask,30,60)
    finally:gdi.DeleteObject(mask)


def test_final_without_newlines_distributes_into_same_source_slots(core):
    rows=[dict(x=0,y=i*40,w=250,h=35,ink_bounds=[2,i*40+2,245,30],font_size=0) for i in range(3)]
    result=render(core,[fixed('\u6b22\u8fce\u6765\u5230\u7a7a\u95f4\u7ad9\uff0c\u8bf7\u68c0\u67e5\u8bbe\u5907\uff0c\u51c6\u5907\u7ee7\u7eed\u4e0b\u4e00\u9879\u4efb\u52a1\u3002',h=115,_source_rows=rows)])[0]
    assert result['fits'] and len(result['lines'])==3
    assert [v['ink_y'] for v in result['lines']]==[2,42,82]
    assert all(v['length'] and v['width']==245 for v in result['lines'])


def test_stream_no_stretch_and_font_never_enlarges_for_same_revision(core):
    text='\u8fd9\u662f\u4e00\u6bb5\u5fc5\u987b\u4fdd\u6301\u539f\u4f4d\u5e76\u5728\u5fc5\u8981\u65f6\u7f29\u5c0f\u5b57\u53f7\u7684\u7ffb\u8bd1\u6587\u5b57\u3002'
    sizes=[]
    for length in (2,6,12,len(text)):
        result=render(core,[fixed(text[:length],final=False)])[0]
        sizes.append(result['font_px'])
        if length==2:assert result['lines'][0]['width']<245
    done=render(core,[fixed(text)])[0]
    sizes.append(done['font_px'])
    assert sizes==sorted(sizes,reverse=True)
    assert done['fits'] and done['lines'][0]['width']==245


@pytest.mark.parametrize('text',['😀😀😀😀','e\u0301e\u0301e\u0301e\u0301','👩\u200d🚀👩\u200d🚀'])
def test_clusters_remain_intact_across_source_rows(core,text):
    rows=[dict(x=0,y=i*40,w=250,h=35,font_size=0) for i in range(2)]
    result=render(core,[fixed(text,h=75,_source_rows=rows)])[0]
    assert result['fits']
    # Each repeated grapheme has the same unit length; no boundary splits it.
    units=len(text.encode('utf-16-le'))//2
    cluster=2 if text.startswith('😀') or text.startswith('e') else 5
    assert sum(v['length'] for v in result['lines'])==units
    assert all(v['length']%cluster==0 for v in result['lines'])


def test_unfit_minimum_font_keeps_original_pixels(core):
    result=render(core,[fixed('\u5f88\u957f\u7684\u6587\u5b57'*100,w=12,h=10,
        _source_rows=[dict(x=0,y=0,w=12,h=10,font_size=0)])])[0]
    assert not result['fits']
    gdi=ctypes.windll.gdi32;user=ctypes.windll.user32
    gdi.CreateRectRgn.restype=ctypes.c_void_p
    gdi.DeleteObject.argtypes=[ctypes.c_void_p]
    user.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    mask=gdi.CreateRectRgn(0,0,0,0)
    try:assert user.GetWindowRgn(result['hwnd'],mask)==1  # NULLREGION
    finally:gdi.DeleteObject(mask)


@pytest.mark.parametrize('text',['','\u4e2d','\u5f88\u957f\u7684\u6587\u5b57'*100])
def test_japanese_source_with_no_sample_stays_visible(core,text):
    item=fixed(text,w=80,h=20,final=False,_cover_source=True,
               _source_rows=[dict(x=2,y=1,w=76,h=18,font_size=0)])
    result=render(core,[item])[0]
    assert not ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(result['hwnd']))


def test_bad_native_row_offsets_fail_without_submitting_partial_snapshot(core):
    before=render(core,[fixed()])[0]
    raw=(_Region*1)(_Region(30,30,250,35,0,0xffffff,0,1,'\u72b6\u6001',1,1))
    rows=(_SourceRow*1)(_SourceRow(0,0,250,35,2,2,245,30,0))
    offsets=(ctypes.c_int32*2)(0,2)
    with core._operation() as context:
        assert core._dll.gl_overlay_fixed(context,raw,1,rows,1,offsets)==0
    assert core.overlay_snapshot()['regions'][0]['hwnd']==before['hwnd']


def test_explicit_font_cap_is_respected(core):
    item=fixed(_source_rows=[dict(x=0,y=0,w=250,h=35,font_size=14)])
    assert render(core,[item])[0]['font_px']<=14
