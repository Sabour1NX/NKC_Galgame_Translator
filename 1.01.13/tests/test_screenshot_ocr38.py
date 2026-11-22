# SPDX-License-Identifier: MIT
"""DeepSeek screenshot mode, window-only upload and bounded OCR geometry."""
import time
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from nkc_galgame_translator.config_store import ConfigStore
from nkc_galgame_translator.live_capture import LiveCapture
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.tuning import validate_tuning
from nkc_galgame_translator.vision import DeepSeekScreenshotRecognizer, parse_layout
from nkc_galgame_translator.vision_core import VisionCore
from test_scroll29 import SyntheticNative


def test_vision_mode_migrates_legacy_opt_in(tmp_path):
    config = tmp_path/'config'
    config.mkdir()
    (config/'example.json').write_text('{"vision_ocr_mode":"off"}')
    (config/'local.json').write_text('{"vision_ocr":true}')
    assert ConfigStore(tmp_path).load()['vision_ocr_mode'] == 'force'
    (config/'local.json').write_text('{"vision_ocr":true,"vision_ocr_mode":"force"}')
    assert ConfigStore(tmp_path).load()['vision_ocr_mode'] == 'force'
    assert validate_tuning({})['vision_ocr_mode'] == 'off'
    with pytest.raises(ValueError):
        validate_tuning({'vision_ocr_mode':'other'})


def test_layout_parser_supports_provider_coordinates_and_ignores_images():
    text = '<\uff5cref\uff5c>text<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[100,200,751,331]]<\uff5c/box\uff5c> Actual line. '
    text += '<\uff5cref\uff5c>image<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[0,0,1000,1000]]<\uff5c/box\uff5c> omission'
    assert parse_layout(text, (200,100)) == [{'text':'Actual line.','x':20,'y':20,'w':131,'h':14}]
    with pytest.raises(ValueError):
        parse_layout(text.replace('751','1751'), (200,100))


def test_recognizer_uses_official_spatial_ocr_protocol(tmp_path):
    messages = []
    def handle(request):
        messages.append(request)
        return httpx.Response(200, json={'page_count':1, 'pages':[
            {'index':0,'finish_reason':'stop',
             'text':'<\uff5cref\uff5c>text<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[100,200,900,450]]<\uff5c/box\uff5c> New words'}
        ]})
    engine = TranslationEngine({'base_url':'https://api.deepseek.com/v1','model':'deepseek-flash',
                               'api_key':'synthetic-screenshot-key-012345'},tmp_path/'test.db')
    engine._client = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        with Image.new('RGB',(100,50)) as image:
            rows = DeepSeekScreenshotRecognizer(engine).recognize_frame(image,cancelled=lambda:False)
        assert rows[0]['text'] == 'New words'
        assert str(messages[0].url) == 'https://api.deepseek.com/v1/tools/ocr'
        assert b'rich_layout_recognition' in messages[0].content
        assert b'image/png' in messages[0].content
        assert engine.get_stats()['session_requests'] == 1
    finally:
        engine.close()


@pytest.mark.parametrize('mode,window_pixels,local_text,expected',[
    ('off',True,'Good text',False),('off',True,None,False),
    ('force',True,None,True),('force',True,'Good text',True),('force',False,None,False),
])
def test_live_cloud_request_routing_and_selection_mask(mode,window_pixels,local_text,expected):
    class Native(SyntheticNative):
        def capture_bgra(self,*args):
            return {**super().capture_bgra(*args),'window_pixels':window_pixels}
    calls = []
    def recognize_frame(image, *, cancelled):
        assert image.getpixel((1,1)) == (255,255,255)
        assert image.getpixel((120,25)) == (0,0,0)  # Outside both selections.
        calls.append(1)
        return [dict(text='Recovered message',x=10,y=43,w=90,h=12)]
    local = [dict(text=local_text,x=10,y=12,w=80,h=14,confidence=99)] if local_text else []
    with Image.new('RGB',(200,100),'white') as image:
        core = SimpleNamespace(native=Native(image), _capture_regions=((0,0,110,100),(150,20,45,75)),
                               recognize_image=lambda *args: {'lines':local,'ocr_ms':1})
        recognizer = SimpleNamespace(recognize_frame=recognize_frame)
        wrapper = VisionCore(core,None,frame_mode=mode,recognizer=recognizer)
        live = LiveCapture(core)
        live.frame_review = wrapper._plan_frame_review if mode!='off' else None
        try:
            end = time.monotonic()+.45
            while time.monotonic()<end:
                live.capture(0,0,200,100,'en')
                time.sleep(.01)
            assert bool(calls) == expected
            assert any(row['text']=='Recovered message' for row in live.lines) == expected
            assert len(calls)<=1
            if local_text:
                assert any(row['text']==local_text for row in live.lines)
        finally:
            live.close()
            wrapper._pool.shutdown(wait=True)


