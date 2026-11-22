# SPDX-License-Identifier: MIT
"""Fixed-image OCR regressions; no desktop capture or game activation."""
from pathlib import Path
from unittest.mock import Mock

from PIL import Image, ImageDraw, ImageFont
import pytest

from nkc_galgame_translator.native import NativeCore
from nkc_galgame_translator.ocr import OcrCore, PortableOcr, looks_like_pixel_frame, place_image_result

ROOT=Path(__file__).resolve().parents[1]


def high_contrast_fixture():
    image=Image.new('RGB',(400,160),'black')
    ImageDraw.Draw(image).rectangle((30,30,330,65),fill='white')
    return image


def test_auto_pixel_hint_rejects_blank_and_smooth_multicolor_frames():
    assert looks_like_pixel_frame(high_contrast_fixture())
    assert not looks_like_pixel_frame(Image.new('RGB',(400,160),'black'))
    assert not looks_like_pixel_frame(Image.new('RGB',(400,160),'white'))
    image=Image.new('RGB',(128,128))
    image.putdata([(x*2,y*2,(x+y)%256) for y in range(128) for x in range(128)])
    assert not looks_like_pixel_frame(image)


def colored_hud_fixture():
    image=Image.new('RGB',(128,128),(25,30,210))
    draw=ImageDraw.Draw(image)
    draw.rectangle((12,8,115,107),fill='black')
    # Sparse white block glyphs, not a large white panel.
    for x in range(24,105,10):
        draw.rectangle((x,76,x+3,82),fill='white')
    return image


def test_auto_pixel_hint_recognizes_sparse_ink_inside_colored_classic_hud():
    image=colored_hud_fixture()
    assert looks_like_pixel_frame(image)
    # An otherwise identical frame with no readable bright ink stays native.
    image.paste('black',(12,8,116,108))
    assert not looks_like_pixel_frame(image)


def test_colored_hud_route_requires_concentrated_palette():
    image=colored_hud_fixture()
    # Keep the same dark/bright coverage but fill the decorative third with
    # 80 equally prevalent shades; it lacks the classic small-palette signal.
    for y in range(128):
        for x in range(128):
            if not (12<=x<=115 and 8<=y<=107):
                tone=(x+y*128)%80
                image.putpixel((x,y),(40+tone,50+tone,140+tone))
    assert not looks_like_pixel_frame(image)


def test_auto_colored_hud_routes_to_pixel_without_overriding_native_selection(monkeypatch):
    with OcrCore(mode='auto') as core:
        monkeypatch.setattr(core.portable,'available',lambda:True)
        local=Mock(return_value={'lines':[],'ocr_ms':1})
        native=Mock(return_value={'lines':[],'ocr_ms':1,'engine':'windows-ocr'})
        monkeypatch.setattr(core.portable,'recognize',local)
        monkeypatch.setattr(core.native,'recognize_bgra',native)
        image=colored_hud_fixture()
        result=core.recognize_image(image,'en')
        assert result['engine']=='portable-tesseract-pixel'
        assert local.call_args.args[1:]==('eng','pixel') and not native.called
        assert core.recognize_image(image,'en',mode='native')['engine']=='windows-ocr'
        assert native.call_count==1 and local.call_count==1


def test_fixed_image_native_ocr_does_not_capture_or_change_frame_hash(monkeypatch):
    with OcrCore(mode='native') as core:
        native=Mock(return_value={'lines':[],'ocr_ms':1,'engine':'windows-ocr'})
        monkeypatch.setattr(core.native,'recognize_bgra',native)
        monkeypatch.setattr(core.native,'capture_bgra',Mock(side_effect=AssertionError('unexpected capture')))
        monkeypatch.setattr(core.native,'capture_ocr',Mock(side_effect=AssertionError('unexpected recapture')))
        monkeypatch.setattr(core.native,'reset',Mock(side_effect=AssertionError('unexpected hash reset')))
        image=Image.new('RGB',(42,32),'white')
        assert core.recognize_image(image,'en')['engine']=='windows-ocr'
        args=native.call_args.args
        assert args[1:]==(42,32,'en') and len(args[0])==42*32*4


def test_capture_once_offset_once_and_skip_unchanged(monkeypatch):
    with OcrCore() as core:
        capture=Mock(side_effect=[{'changed':True,'capture_ms':1,'bgra':bytes(40*30*4)},
                                  {'changed':False,'capture_ms':.1,'bgra':None}])
        recognize=Mock(return_value={'lines':[{'text':'opaque','x':2,'y':3,'w':12,'h':13}],
                                    'ocr_ms':2,'engine':'fake'})
        monkeypatch.setattr(core.native,'capture_bgra',capture)
        monkeypatch.setattr(core,'recognize_image',recognize)
        first=core.capture_ocr(100,200,40,30,'en')
        second=core.capture_ocr(100,200,40,30,'en')
        assert (first['lines'][0]['x'],first['lines'][0]['y'])==(102,203)
        assert first['changed'] and first['capture_ms']==1
        assert second['changed'] is False and second['ocr_ms']==0
        assert capture.call_count==2 and recognize.call_count==1


def test_language_change_invalidates_raw_frame_cache(monkeypatch):
    with OcrCore() as core:
        reset=Mock()
        monkeypatch.setattr(core.native,'reset',reset)
        monkeypatch.setattr(core.native,'capture_bgra',lambda *_:{'changed':False,'capture_ms':0,'bgra':None})
        core.capture_ocr(0,0,40,30,'en')
        core.capture_ocr(0,0,40,30,'en')
        core.capture_ocr(0,0,40,30,'ja')
        assert reset.call_count==2


def test_place_result_does_not_mutate_game_text_or_source_bounds():
    original={'lines':[{'text':'{source} / \u8bbe\u7f6e','x':3,'y':5,'w':10,'h':12}],'ocr_ms':1}
    placed=place_image_result(original,100,-200)
    assert placed['lines'][0]['text']=='{source} / \u8bbe\u7f6e'
    assert (placed['lines'][0]['x'],placed['lines'][0]['y'])==(103,-195)
    assert original['lines'][0]['x']==3


def test_native_mode_advertises_only_installed_windows_languages(monkeypatch):
    with OcrCore(mode='native') as core:
        core._native_languages=['en-US']
        monkeypatch.setattr(core.portable,'available',lambda:True)
        assert core.languages()==['en-US']


@pytest.mark.parametrize('mode',['bad',None,1,True,[],{}])
def test_invalid_mode_fails_before_native_initialization(mode):
    with pytest.raises(ValueError):OcrCore(mode=mode)


@pytest.mark.parametrize('size,data', [((0,20),b''),((4097,1),b''),((3,4),bytes(47)),((3,4),'x'*48)])
def test_fixed_native_image_rejects_invalid_buffers(size,data):
    with NativeCore() as core:
        with pytest.raises(ValueError):core.recognize_bgra(data,*size,'en')


def test_real_native_fixed_image_english_and_bounds():
    font=Path('C:/Windows/Fonts/arial.ttf')
    if not font.exists():pytest.skip('test font missing')
    image=Image.new('RGB',(800,160),'white')
    ImageDraw.Draw(image).text((20,35),'Mission complete. Welcome aboard.',font=ImageFont.truetype(str(font),34),fill='black')
    with OcrCore(mode='native') as core:
        result=core.recognize_image(image,'en')
    assert 'Mission complete' in ' '.join(line['text'] for line in result['lines'])
    assert all(0<=line['x']<line['x']+line['w']<=800 and 0<=line['y']<line['y']+line['h']<=160 for line in result['lines'])


def test_real_private_spacerogue_pixel_recovers_fifteen_lines_and_bottom_paragraph():
    fixture=ROOT/'reports/ocr-private/spacerogue-game.png'
    if not fixture.exists() or not PortableOcr(ROOT).available():
        pytest.skip('private supplied screenshot or optional OCR models absent')
    with Image.open(fixture) as image, OcrCore(mode='pixel') as core:
        result=core.recognize_image(image,'en')
    texts=[line['text'] for line in result['lines']]
    assert len(texts)==15
    for expected in ('trading mission','in the backwater','Small Craft','EVA duty','Make it quick','schedule.'):
        assert any(expected in text for text in texts),expected
    assert len([line for line in result['lines'] if line['y']>550])==5
    assert all(line['confidence']>=55 for line in result['lines'])


def test_real_private_colored_status_uses_pixel_bounds_and_readable_label():
    fixture=ROOT/'reports/ocr-private/status.png'
    if not fixture.exists() or not PortableOcr(ROOT).available():
        pytest.skip('private supplied screenshot or optional OCR models absent')
    with Image.open(fixture) as image, OcrCore(mode='auto') as core:
        result=core.recognize_image(image,'en')
    assert result['engine']=='portable-tesseract-pixel'
    status=next(line for line in result['lines'] if line['text']=='STATUS')
    assert tuple(status[name] for name in ('x','y','w','h'))==(703,162,152,32)
    assert any(line['text']=='SCAN' for line in result['lines'])
