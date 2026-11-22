# SPDX-License-Identifier: MIT
"""Real GDI: separate OCR objects in one paragraph share a fitting font."""
import pytest
from test_native_overlay import core, render
from test_native_fixed_layout import fixed


def prose(identity, y, text, *, height=30, width=495, cap=0, x=30, **extra):
    return fixed(text, _track_id=identity, x=x, y=y, w=width+5, h=height+5,
        _source_rows=[dict(x=0,y=0,w=width+5,h=height+5,
            ink_bounds=[2,2,width,height],font_size=cap)], **extra)


def test_low_glyph_and_punctuation_prefix_cannot_inflate_em(core):
    core.set_overlay_font('SimSun')
    results=[render(core,[prose(i+1,50,text)])[0]
        for i,text in enumerate(('\u4e00','……','\u5c06\u4f1a\u6709\u6109\u5feb\u7684','\u56fd'))]
    # The fitting ceiling derives from a stable font alphabet, not the current
    # token's black-pixel height. Actual glyph ink may naturally differ.
    assert len({item['font_px'] for item in results})==1
    assert all(item['fits'] and item['font_px']<45 for item in results)


def test_fragmented_paragraph_uniform_em_keeps_full_width_spacing(core):
    regions=[prose(1,50,'\u4ed6\u5df2\u7ecf\u5bf9\u60a8\u7684\u8d27\u8231\u8fdb\u884c\u4e86\u4f8b\u884c\u68c0\u67e5\uff0c',height=27),
             prose(2,84,'\u53d1\u73b0\u4e00\u5207\u6b63\u5e38\u3002\u4ed6\u5e0c\u671b\u60a8',height=31),
             prose(3,119,'\u5c06\u4f1a\u6709\u6109\u5feb\u7684',height=30),
             prose(4,154,'\u8bbf\u95ee\u3002',height=27)]
    result=render(core,regions)
    assert len({item['font_px'] for item in result})==1
    assert all(item['font_peers']==4 and item['fits'] for item in result)
    assert [item['bounds'] for item in result]==[[r['x'],r['y'],r['w'],r['h']] for r in regions]
    assert all(item['lines'][0]['width']==495 for item in result)
    # An overlong translated row makes every peer shrink together.
    regions[1].update(text='\u8fd9\u6bb5\u8bd1\u6587\u6bd4\u539f\u6765\u957f\uff0c\u9700\u8981\u7f29\u5c0f\u5b57\u53f7\u624d\u80fd\u5b8c\u6574\u5730\u653e\u8fdb\u539f\u6765\u7684\u7269\u7406\u884c\u5bbd\u3002',_revision=2)
    smaller=render(core,regions)
    assert len({item['font_px'] for item in smaller})==1
    assert smaller[0]['font_px']<result[0]['font_px']
    assert all(item['fits'] for item in smaller)


@pytest.mark.parametrize('change',['title','gap','column','color','cap','family','pixel'])
def test_distinct_source_style_never_joins_body_font_group(core,change):
    first=prose(1,50,'\u7b2c\u4e00\u6bb5\u6b63\u6587\u5185\u5bb9\u5f88\u957f\u5f88\u957f\uff0c\u9700\u8981\u66f4\u5c0f\u7684\u5b57\u53f7\u624d\u53ef\u4ee5\u5b8c\u6574\u663e\u793a\u3002')
    second=prose(2,85,'\u53e6\u4e00\u6bb5\u5185\u5bb9')
    if change=='title':
        second=prose(2,85,'\u53e6\u4e00\u6bb5\u5185\u5bb9',height=48)
    elif change=='gap':second['y']=160
    elif change=='column':second['x']=560
    elif change=='color':second['fg']=[100,255,100]
    elif change=='cap':second['_source_rows'][0]['font_size']=14
    if change in ('family','pixel'):
        from types import SimpleNamespace
        second['_source_font_style']='other'
        core._font_selector=SimpleNamespace(choose=lambda style,text:
            ('SimSun' if style=='other' and change=='family' else 'Microsoft YaHei UI',
             style=='other' and change=='pixel'))
    result=render(core,[first,second])
    assert all(item['font_peers']==1 for item in result)
    assert result[0]['font_px']!=result[1]['font_px']


def test_standalone_prompt_keeps_native_fit_when_neighbor_appears(core):
    prompt=prose(1,50,'\u8981\u8df3\u8fc7\u5f00\u573a\u5417\uff1f',_standalone_subtitle=True)
    neighbor=prose(2,85,'\u8fd9\u6bb5\u5019\u9009\u6587\u5b57\u6bd4\u4e0a\u4e00\u884c\u66f4\u957f\uff0c\u4f1a\u5355\u72ec\u7f29\u5c0f\u5b57\u53f7\u4ee5\u9002\u5e94\u539f\u6587\u7684\u884c\u5bbd\u3002')
    first,=render(core,[prompt])
    with_neighbor=render(core,[prompt,neighbor])
    last,=render(core,[prompt])
    for current in (with_neighbor[0],last):
        assert current['font_px']==first['font_px'] and current['font_peers']==1
        assert current['lines']==first['lines'] and current['bounds']==first['bounds']
    assert with_neighbor[1]['font_px']<first['font_px']


def test_stream_font_sync_never_grows_or_changes_revision_and_identity(core):
    rows=[prose(1,50,'\u7b2c\u4e00\u884c',final=False),prose(2,85,'\u7b2c\u4e8c\u884c',final=False)]
    sizes=[];handles=None
    for text in ('\u7b2c\u4e8c\u884c','\u7b2c\u4e8c\u884c\u6bd4\u8f83\u957f','\u7b2c\u4e8c\u884c\u6bd4\u8f83\u957f\uff0c\u9700\u8981\u9010\u6e10\u7f29\u5c0f\u5b57\u53f7\u5e76\u4fdd\u6301\u6574\u6bb5\u7684\u4e00\u81f4\u6027'):
        rows[1]['text']=text
        snapshot=render(core,rows)
        assert snapshot[0]['font_px']==snapshot[1]['font_px']
        sizes.append(snapshot[0]['font_px'])
        if handles is None:handles=[item['hwnd'] for item in snapshot]
        assert [item['hwnd'] for item in snapshot]==handles
    assert sizes==sorted(sizes,reverse=True)
