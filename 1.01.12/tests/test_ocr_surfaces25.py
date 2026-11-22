# SPDX-License-Identifier: MIT
"""Measured, generic small-text surfaces: no game vocabulary or coordinates."""
import importlib.util
from copy import deepcopy
from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageFont
from nkc_galgame_translator.ocr import PortableOcr, OcrCore, place_image_result, validate_response
from nkc_galgame_translator.ocr_regions import refine_ink

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('surface25',ROOT/'tools/ocr_helper.py')
HELPER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(HELPER)


def panel(offset=(0,0),scale=1,colors=('#fff7ff','#2837ac')):
    image=Image.new('RGB',(800*scale,400*scale),'#183b50')
    draw=ImageDraw.Draw(image);ox,oy=offset
    box=((100+ox)*scale,(80+oy)*scale,(700+ox)*scale,(320+oy)*scale)
    draw.rectangle(box,fill=colors[0],outline='#756397',width=2*scale)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14*scale)
    for i,text in enumerate(['Welcome to the station.','The current mission is complete.','Please return to the main menu.']):
        draw.text(((135+ox)*scale,(115+oy+i*40)*scale),text,fill=colors[1],font=font)
    return image


@pytest.mark.parametrize('offset,scale',[((0,0),1),((13,-12),1),((-30,16),2)])
def test_detected_surface_follows_measured_panel_not_fixed_game_bounds(offset,scale):
    with panel(offset,scale) as image:
        boxes=HELPER.find_text_surfaces(image)
        assert boxes
        ox,oy=offset
        assert any(l<=(135+ox)*scale<r and t<=(115+oy)*scale<b for l,t,r,b in boxes)
        assert all(0<=l<r<=image.width and 0<=t<b<=image.height for l,t,r,b in boxes)


@pytest.mark.parametrize('colors',[('#fff7ff','#2837ac'),('#072241','#ffe852'),('#008200','#ff0000')])
def test_small_color_text_recognized_without_whole_frame_inversion(colors):
    core=PortableOcr(ROOT)
    if not core.available():pytest.skip('Optional portable OCR unavailable')
    try:
        with panel(colors=colors) as image:
            before=image.tobytes();result=core.recognize(image,'eng','standard')
            text=' '.join(row['text'] for row in result['lines'])
            assert 'Welcome to the station.' in text
            assert 'current mission is complete.' in text
            assert 'return to the main menu' in text
            assert image.tobytes()==before
    finally:core.close()


def test_projection_ignores_tall_border_and_keeps_actual_row_positions():
    with Image.new('RGB',(360,160),'white') as image:
        d=ImageDraw.Draw(image);d.rectangle((0,0,359,159),outline='black',width=2)
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
        for y,text in [(20,'Mission complete.'),(75,'Return to the station.')]:
            d.text((24,y),text,font=font,fill='black')
        rows=HELPER.surface_rows(image)
        assert len(rows)==2
        assert 20<=rows[0][1]<40 and 75<=rows[1][1]<95


def detection(text,confidence=90,**changes):
    return dict(text=text,confidence=confidence,x=10,y=10,w=180,h=15,**changes)


def test_surface_merge_never_overwrites_strong_text_or_crosses_two_rows():
    primary=[detection('Strong original',95)]
    original=deepcopy(primary)
    assert HELPER.merge_surface_detections(primary,[detection('Another reading',80)])==primary
    candidate=detection('Too tall',99);candidate['h']=50
    assert HELPER.merge_surface_detections(primary,[candidate])==primary
    assert primary==original


def test_surface_merge_accepts_complete_row_only_when_stronger():
    primary=[detection('weaker',60)]
    result=HELPER.merge_surface_detections(primary,[detection('clear reading',89)])
    assert [r['text'] for r in result]==['clear reading']
    assert HELPER.merge_surface_detections([], [detection('uncertain',44)])==[]


def test_no_surfaces_on_blank_or_dense_continuous_art():
    with Image.new('RGB',(200,150),'white') as image:
        assert not HELPER.find_text_surfaces(image)
        image.putdata([(x%256,y%256,(x*3+y*2)%256) for y in range(150) for x in range(200)])
        assert not HELPER.find_text_surfaces(image)


def test_low_confidence_anchors_do_not_become_renderable_rows(monkeypatch):
    weak=detection('uncertain text',12)
    with Image.new('RGB',(240,100),'white') as image,OcrCore() as core:
        core._native_languages=['en-US']
        monkeypatch.setattr(core.portable,'available',lambda:True)
        monkeypatch.setattr(core.portable,'recognize',lambda *_:{'lines':[], 'vision_anchors':[weak]})
        result=core.recognize_image(image,'ja')
        assert result['lines']==[]
        assert len(result['vision_anchors'])==1 and result['vision_anchors'][0]['_vision_only'] is True
        placed=place_image_result(result,120,-50)
        anchor=placed['vision_anchors'][0]
        assert anchor['x']==result['vision_anchors'][0]['x']+120
        assert anchor['y']==result['vision_anchors'][0]['y']-50
        assert anchor['_source_ink'][0]==weak['x']+120
        assert anchor['_source_ink'][1]==weak['y']-50


@pytest.mark.parametrize('mutation',[lambda row:row.update(x=-1),lambda row:row.update(w=4097),
    lambda row:row.update(confidence=float('nan')),lambda row:row.update(text='bad\x00')])
def test_untrusted_anchor_geometry_is_validated_like_normal_ocr(mutation):
    row=detection('uncertain',12);mutation(row)
    with pytest.raises(RuntimeError):validate_response({'lines':[],'vision_anchors':[row],'ocr_ms':1},240,100)


def test_anchor_limit_and_opt_in_array():
    with pytest.raises(RuntimeError):validate_response({'lines':[],'vision_anchors':[detection('x')]*129,'ocr_ms':1},240,100)
    with pytest.raises(RuntimeError):validate_response({'lines':[],'vision_anchors':{},'ocr_ms':1},240,100)
    assert validate_response({'lines':[],'ocr_ms':1},240,100)['lines']==[]


def test_real_japanese_pixel_panel_retains_all_body_row_anchors():
    path=ROOT/'reports/ocr-private/needy-caution-full.png'
    if not path.exists() or not PortableOcr(ROOT).available():pytest.skip('Private game screenshot unavailable')
    with Image.open(path) as image,OcrCore() as core:
        result=core.recognize_image(image,'ja')
    anchors=result['vision_anchors']
    for y in (381,413,445,477,510,541,573,605,637):
        matching=[r for r in anchors if r['y']<=y<r['y']+r['h']]
        assert len(matching)==1,(y,matching)
        assert matching[0]['_vision_only'] is True
    assert not any(r['y']>700 and r['w']>300 for r in anchors)


def test_large_ocr_vertical_padding_does_not_enlarge_button_font():
    with Image.new('RGB',(240,100),'#f7e1fa') as image:
        draw=ImageDraw.Draw(image)
        for x in range(24,81,10):draw.rectangle((x,31,x+5,44),fill='#4d22cd')
        source=dict(text='Any label',x=18,y=23,w=74,h=35,
                    _source_ink=[20,25,70,30],fg=[20,20,20],bg=[247,225,250])
        found=refine_ink(image,source)
        assert found['_source_ink'][3]==16
        assert found['fg']==[77,34,205]
        assert tuple(found[k] for k in ('x','y','w','h'))==(18,23,74,35)


def test_real_controls_use_the_same_measured_ink_height():
    path=ROOT/'reports/ocr-private/needy-caution-full.png'
    if not path.exists():pytest.skip('Private game screenshot unavailable')
    with Image.open(path) as image:
        controls=[dict(text='opaque',x=808,y=755,w=69,h=35,_source_ink=[810,757,64,30]),
                  dict(text='opaque',x=1061,y=759,w=25,h=21,_source_ink=[1063,761,20,16])]
        found=[refine_ink(image,row) for row in controls]
        assert [row['_source_ink'][3] for row in found]==[16,16]

def test_warm_warning_line_survives_when_whole_frame_ocr_has_no_result(monkeypatch):
    font=ImageFont.truetype('C:/Windows/Fonts/YuGothM.ttc',20)
    with Image.new('RGB',(280,110),(253,248,253)) as image,OcrCore() as core:
        if not core.portable.available():
            pytest.skip('Optional portable OCR unavailable')
        draw=ImageDraw.Draw(image)
        draw.text((22,25),'\u3051\u3044\u3053\u304f',font=font,fill=(231,83,83))
        draw.text((22,62),'\u9752\u3044\u6587\u5b57',font=font,fill=(77,34,205))
        monkeypatch.setattr(core,'_recognize_image_uncached',
                            lambda *args:dict(lines=[],ocr_ms=0,engine='synthetic'))
        rows=core.recognize_image(image,'ja')['lines']
        assert [row['text'].replace(' ','') for row in rows]==['\u3051\u3044\u3053\u304f']
        assert rows[0]['fg']==(231,83,83)
        assert 24<=rows[0]['y']<48
