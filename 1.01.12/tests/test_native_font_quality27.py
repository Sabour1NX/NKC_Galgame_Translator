# SPDX-License-Identifier: MIT
"""Actual GDI regression for short OCR continuations and streaming fit."""
import ctypes
from test_native_overlay import core, render
from test_native_fixed_layout import fixed


def paragraph(text=None, **changes):
    # Measured row sizes from a 960/1280 scaled warning panel. Text is synthetic.
    widths=[555,699,490,797,28,490,639,759,456]
    ys=[0,32,64,96,130,160,192,224,256]
    rows=[dict(x=0,y=y,w=w+5,h=23 if i==4 else 25,
               ink_bounds=[2,y+2,w,18 if i==4 else 20],font_size=0)
          for i,(w,y) in enumerate(zip(widths,ys))]
    item=fixed(text or '\n'.join(['\u6b63\u6587\u7b2c\u4e00\u884c\u5185\u5bb9','\u6b63\u6587\u7b2c\u4e8c\u884c\u5185\u5bb9','\u7b2c\u4e09\u884c\u8bf4\u660e',
                  '\u8fd9\u91cc\u6709\u5145\u8db3\u7684\u7a7a\u95f4\u663e\u793a\u4e0a\u4e00\u884c\u5c1a\u672a\u5bb9\u7eb3\u7684\u7ed3\u5c3e','\u5427\uff01',
                  '\u8fd9\u662f\u540e\u7eed\u6b63\u6587','\u53e6\u4e00\u884c\u5185\u5bb9\u8bf4\u660e','\u63a5\u4e0b\u6765\u7ee7\u7eed\u8bf4\u660e','\u6700\u540e\u4e00\u884c\u5185\u5bb9']),
               w=802,h=281,_source_rows=rows)
    item.update(changes)
    return item


def point_is_covered(snapshot,x,y):
    gdi=ctypes.windll.gdi32;user=ctypes.windll.user32
    gdi.CreateRectRgn.restype=ctypes.c_void_p
    gdi.PtInRegion.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    gdi.DeleteObject.argtypes=[ctypes.c_void_p]
    user.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
    mask=gdi.CreateRectRgn(0,0,0,0)
    try:
        user.GetWindowRgn(snapshot['hwnd'],mask)
        return bool(gdi.PtInRegion(mask,x,y))
    finally:gdi.DeleteObject(mask)


def test_short_continuation_uses_previous_spare_width_without_shrinking_body(core):
    item=paragraph();result=render(core,[item])[0]
    assert result['fits'] and result['font_px']>=19
    assert len(result['lines'])==9 and all(row['drawable'] for row in result['lines'])
    assert result['lines'][4]['length']==1
    assert result['lines'][3]['length']==len(item['text'].splitlines()[3])+1
    assert sum(row['length'] for row in result['lines'])==len(item['text'].replace('\n',''))
    assert all(row['width']==source['ink_bounds'][2]
               for row,source in zip(result['lines'],item['_source_rows']) if row['length']>1)
    assert result['bounds']==[item['x'],item['y'],item['w'],item['h']]


def test_unreliable_tiny_row_preserves_original_and_does_not_reduce_body(core):
    item=paragraph();item['_source_rows'][4].update(h=7,ink_bounds=[2,132,5,3])
    result=render(core,[item])[0]
    assert result['fits'] and result['font_px']>=19
    assert not result['lines'][4]['drawable']
    assert not point_is_covered(result,3,133)
    assert point_is_covered(result,3,162)


def test_real_long_body_line_still_shrinks_entire_paragraph(core):
    item=paragraph();regular=render(core,[item])[0]
    text=item['text'].splitlines();text[1]='\u8fd9\u662f\u4e00\u6761\u5f88\u957f\u5f88\u957f\u7684\u6b63\u6587\uff0c\u9700\u8981\u6574\u6bb5\u5171\u540c\u7f29\u5c0f\u4ee5\u4fdd\u6301\u539f\u6765\u7684\u7a7a\u95f4\u3002'*2
    smaller=render(core,[{**item,'text':'\n'.join(text),'_revision':2}])[0]
    assert smaller['fits'] and smaller['font_px']<regular['font_px']
    assert len(smaller['lines'])==len(regular['lines'])


def test_stream_overflow_defers_prefix_at_stable_font_then_final_fits_once(core):
    text='\u6d41\u5f0f\u6587\u5b57\u4fdd\u6301\u7a33\u5b9a\uff0c\u7ed3\u675f\u540e\u6574\u6bb5\u9002\u914d\u539f\u4f4d\u3002'
    sizes=[];seen=[]
    for end in (2,8,16,len(text)):
        result=render(core,[fixed(text[:end],final=False)])[0]
        sizes.append(result['font_px']);seen.append(result['lines'][0]['length'])
        assert result['lines'][0]['width']<=245 and result['fits']
    assert len(set(sizes))==1 and seen==sorted(seen)
    assert seen[-1]<len(text)
    final=render(core,[fixed(text,final=True)])[0]
    assert final['fits'] and final['font_px']<sizes[0]
    assert final['lines'][0]['length']==len(text) and final['lines'][0]['width']==245


def test_two_short_label_rows_are_not_assumed_to_be_prose_outliers(core):
    item=fixed('\u7532\u4e59\n\u4e19\u4e01',w=60,h=65,_source_rows=[
        dict(x=0,y=0,w=60,h=25,ink_bounds=[2,2,55,20],font_size=0),
        dict(x=0,y=35,w=20,h=25,ink_bounds=[2,37,15,20],font_size=0)])
    result=render(core,[item])[0]
    assert not result['fits'] or result['font_px']<=8


def test_separate_tiny_object_does_not_drag_down_two_body_neighbors(core):
    from test_native_font_consistency25 import prose
    objects=[prose(1,50,'\u7b2c\u4e00\u884c\u6b63\u6587',height=20,width=495),
             prose(2,75,'\u5427\uff01',height=20,width=28),
             prose(3,100,'\u7b2c\u4e09\u884c\u6b63\u6587',height=20,width=495)]
    first=render(core,objects)
    assert first[0]['fits'] and first[2]['fits'] and not first[1]['fits']
    assert len({v['font_px'] for v in first})==1 and first[0]['font_px']>=19
    assert all(v['font_peers']==3 for v in first)
    assert not point_is_covered(first[1],5,5)
    second=render(core,objects)
    assert [v['font_px'] for v in second]==[v['font_px'] for v in first]


def test_medium_width_object_remains_a_real_constraint_for_all_peers(core):
    from test_native_font_consistency25 import prose
    objects=[prose(1,50,'\u7b2c\u4e00\u884c\u6b63\u6587',height=20,width=495),
             prose(2,75,'\u4e2d\u95f4\u8fd9\u884c\u9700\u8981\u5171\u540c\u7f29\u5c0f',height=20,width=100),
             prose(3,100,'\u7b2c\u4e09\u884c\u6b63\u6587',height=20,width=495)]
    result=render(core,objects)
    assert all(v['fits'] for v in result)
    assert len({v['font_px'] for v in result})==1 and result[0]['font_px']<19


def test_small_ink_noise_keeps_fit_but_corrected_large_geometry_can_recover(core):
    item=fixed('\u8fd9\u4e00\u884c\u6587\u5b57\u8f83\u957f\uff0c\u9700\u8981\u62df\u5408\u5230\u5f53\u524d\u884c\u5bbd\u3002')
    first=render(core,[item])[0]
    noisy={**item,'_source_rows':[dict(x=0,y=0,w=250,h=35,ink_bounds=[2,2,246,31],font_size=0)]}
    same=render(core,[noisy])[0]
    assert same['font_px']==first['font_px']
    corrected={**item,'w':500,'_source_rows':[dict(x=0,y=0,w=500,h=35,ink_bounds=[2,2,495,30],font_size=0)]}
    recovered=render(core,[corrected])[0]
    assert recovered['fits'] and recovered['font_px']>first['font_px']

