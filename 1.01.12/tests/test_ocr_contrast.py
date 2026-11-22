# SPDX-License-Identifier: MIT
"""Mixed-polarity and RGB-contrast regressions. No screen capture or API."""
import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pytest

from nkc_galgame_translator.ocr import OcrCore, PortableOcr, looks_like_pixel_frame, validate_response

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('contrast_helper',ROOT/'tools/ocr_helper.py')
HELPER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(HELPER)
PALETTES=[('white','black'),('black','white'),('#28a62a','black'),
          ('#173b92','#fff43a'),('#c82965','white'),('#ff0000','#008200')]


def mixed_frame(background,foreground):
    image=Image.new('RGB',(660,250),'#121212')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
    draw=ImageDraw.Draw(image)
    draw.text((28,18),'Cargo Manifest',font=font,fill='white')
    draw.rectangle((24,82,630,129),fill=background)
    draw.text((32,85),'Selected Cargo',font=font,fill=foreground)
    draw.text((563,85),'18',font=font,fill=foreground)
    draw.text((28,174),'Return to Ship',font=font,fill='#ffde46')
    return image


@pytest.mark.parametrize('background,foreground',PALETTES)
def test_rgb_rows_preserve_normal_text_columns_and_source(background,foreground):
    with mixed_frame(background,foreground) as image,OcrCore(mode='pixel') as core:
        original=image.tobytes()
        result=core.recognize_image(image,'en')
        lines=result['lines']
        assert image.tobytes()==original
        for expected in ('Cargo Manifest','Selected Cargo','18','Return to Ship'):
            assert any(line['text']==expected for line in lines),lines
        label=next(line for line in lines if line['text']=='Selected Cargo')
        price=next(line for line in lines if line['text']=='18')
        assert label['x']+label['w']<400 and price['x']>530
        assert 82<=label['_source_ink'][1]<130
        assert len({(l['x'],l['y'],l['w'],l['h']) for l in lines})==len(lines)


@pytest.mark.parametrize('background,foreground',[('#ff0000','#008200'),('#253997','#ffd42a'),('#ffff00','#1347a2')])
def test_flat_color_text_auto_route(background,foreground):
    with Image.new('RGB',(640,180),background) as image,OcrCore(mode='auto') as core:
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',34)
        ImageDraw.Draw(image).text((30,45),'Welcome aboard',font=font,fill=foreground)
        assert looks_like_pixel_frame(image)
        result=core.recognize_image(image,'en')
        assert result['engine']=='portable-tesseract-pixel'
        assert any(l['text']=='Welcome aboard' for l in result['lines'])


def test_color_distance_keeps_equal_luminance_ink():
    with Image.new('RGB',(2,1),(255,0,0)) as image:
        image.putpixel((1,0),(0,130,0))
        with image.convert('L') as gray:assert abs(gray.getpixel((0,0))-gray.getpixel((1,0)))<=1
        with HELPER.color_contrast(image,(255,0,0)) as mapped:
            assert mapped.getpixel((0,0))==(255,255,255)
            assert mapped.getpixel((1,0))==(0,0,0)


def test_several_contrast_types_in_one_frame():
    with Image.new('RGB',(660,500),'#101010') as image,OcrCore(mode='pixel') as core:
        draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
        rows=[('Ordinary Text','#101010','white'),('White Selection','white','black'),
              ('Blue Selection','#173b92','#fff43a'),('Green Selection','#28a62a','black'),
              ('Color Contrast','#ff0000','#008200')]
        for i,(text,bg,fg) in enumerate(rows):
            y=20+i*90
            draw.rectangle((24,y,630,y+48),fill=bg)
            draw.text((32,y+3),text,font=font,fill=fg)
        result=core.recognize_image(image,'en')
        for i,(text,_,_) in enumerate(rows):
            matches=[l for l in result['lines'] if l['text']==text]
            assert len(matches)==1,result['lines']
            assert 20+i*90<=matches[0]['_source_ink'][1]<=68+i*90


@pytest.mark.parametrize('kind',['blank','rule','oversized','textured'])
def test_no_supplement_for_unproven_background(kind):
    with Image.new('RGB',(640,240),'black') as image:
        draw=ImageDraw.Draw(image)
        if kind=='blank':draw.rectangle((20,70,620,110),fill='white')
        if kind=='rule':draw.rectangle((20,70,620,73),fill='red')
        if kind=='oversized':draw.rectangle((20,10,620,220),fill='white')
        if kind=='textured':
            for y in range(240):
                for x in range(640):image.putpixel((x,y),((x*7)%256,(y*11)%256,(x+y)%256))
        assert HELPER.find_contrast_rows(image)==[]


def test_selected_row_changes_cannot_reuse_stale_color_or_text():
    with mixed_frame('white','black') as first,mixed_frame('#173b92','#fff43a') as second,OcrCore(mode='pixel') as core:
        a=core.recognize_image(first,'en');b=core.recognize_image(second,'en');again=core.recognize_image(first,'en')
        assert not b['frame_cache_hit'] and again['frame_cache_hit']
        assert a['lines']==again['lines']
        label_a=next(l for l in a['lines'] if l['text']=='Selected Cargo')
        label_b=next(l for l in b['lines'] if l['text']=='Selected Cargo')
        assert label_a['bg']!=label_b['bg']


def test_real_cargo_inverse_row_and_status_color_are_recovered():
    for filename,expected in [('cargo.png',('souvenirs','18')),('status.png',('CHART','ALERT'))]:
        fixture=ROOT/'reports/ocr-private'/filename
        if not fixture.exists() or not PortableOcr(ROOT).available():pytest.skip('Private replay fixture absent')
        with Image.open(fixture) as image,OcrCore(mode='pixel') as core:
            before=image.tobytes();lines=core.recognize_image(image,'en')['lines']
            assert image.tobytes()==before
        for text in expected:assert any(l['text']==text for l in lines),lines
        if filename=='cargo.png':
            assert len(lines)==14
            assert all(l['x']+l['w']<400 or l['x']>440 for l in lines)
            selected=[l for l in lines if l['text'] in expected]
            assert all(l['bg']==[255,255,255] and l['fg']==[0,0,0] for l in selected)


def test_candidate_count_and_area_are_bounded():
    with Image.new('RGB',(640,1000),'black') as image:
        draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
        for y in range(10,960,60):
            draw.rectangle((20,y,600,y+40),fill='#4682b4');draw.text((30,y+3),'SELECT A SHIP',font=font,fill='white')
        boxes=HELPER.find_contrast_rows(image)
        assert 1<=len(boxes)<=8
        assert sum((r-l)*(b-t) for l,t,r,b in boxes)<=image.width*image.height//2


def test_contrast_cache_rebases_only_current_geometry_and_checks_rgb(monkeypatch):
    calls=[]
    def reader(engine,tess,image,language,regions):
        calls.append((language,regions))
        l,t,r,b=regions[0]
        return [dict(text='Cargo',x=l+2,y=t+3,w=40,h=20,confidence=90)]
    monkeypatch.setattr(HELPER,'_read_contrast_rows',reader)
    cache=HELPER.ContrastCache()
    with Image.new('RGB',(300,200),'white') as image:
        a=HELPER.read_contrast_rows(None,None,image,'eng',[(10,10,110,50)],cache)
        b=HELPER.read_contrast_rows(None,None,image,'eng',[(100,90,200,130)],cache)
        assert len(calls)==1 and b[0]['x']==102 and b[0]['y']==93
        b[0]['text']='mutated'
        assert HELPER.read_contrast_rows(None,None,image,'eng',[(10,10,110,50)],cache)==a
        image.putpixel((20,20),(0,0,0))
        HELPER.read_contrast_rows(None,None,image,'eng',[(10,10,110,50)],cache)
        HELPER.read_contrast_rows(None,None,image,'jpn',[(10,10,110,50)],cache)
        assert len(calls)==3


def test_contrast_cache_evicts_and_verifies_bytes_even_on_hash_collision():
    cache=HELPER.ContrastCache(max_bytes=1048600,max_entries=2)
    cache.put('key',b'first',[])
    assert cache.get('key',b'first')==[]
    assert cache.get('key',b'other') is None
    cache.put('second',b'next',[])
    assert cache.get('key',b'first') is None
    assert cache.bytes<=cache.max_bytes
    cache.put('too-large',bytes(100),[])
    assert cache.get('too-large',bytes(100)) is None


@pytest.mark.parametrize('size,mode',[((4097,1),'RGB'),((1,4097),'RGB'),((10,10),'L')])
def test_reject_unbounded_or_wrong_format(size,mode):
    with Image.new(mode,size) as image:
        with pytest.raises(ValueError):HELPER.find_contrast_rows(image)
