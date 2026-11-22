# SPDX-License-Identifier: MIT
from threading import Event
from types import SimpleNamespace

from PIL import Image, ImageDraw

from nkc_galgame_translator.live_capture import LiveCapture, decorative_lettering
from nkc_galgame_translator.pipeline import _quality_lines
from test_scroll29 import SyntheticNative


def test_multicolor_title_retains_source_but_plain_dialogue_is_eligible():
    row=dict(x=0,y=0,w=300,h=60,text='\u30bf\u30a4\u30c8\u30eb',bg=[240]*3,fg=[60]*3)
    with Image.new('RGB',(300,60),'white') as image:
        draw=ImageDraw.Draw(image)
        for x in range(10,280,20):
            draw.rectangle((x,8,x+9,50),fill='teal' if x<150 else 'purple')
        assert decorative_lettering(image,row)
        protected=_quality_lines([{**row,'_decorative_lettering':True}],'ja',(0,0),True)
        assert protected[0]['_preserve_source']
        draw.rectangle((0,0,300,60),fill='white')
        draw.text((10,12),'Continue',fill='black')
        assert not decorative_lettering(image,row)


def test_busy_ocr_takes_latest_available_frame_on_completion():
    release=Event()
    samples=[]
    with Image.new('RGB',(128,80),'white') as image:
        native=SyntheticNative(image)
        def read(source,language):
            samples.append(source.getpixel((3,4)))
            assert release.wait(3)
            return dict(lines=[],ocr_ms=0)
        live=LiveCapture(SimpleNamespace(native=native,_capture_regions=(),recognize_image=read))
        live.ocr_interval=0
        try:
            live.capture(0,0,*image.size,'ja')
            for color in ('red','blue'):
                image.putpixel((3,4),{'red':(255,0,0),'blue':(0,0,255)}[color])
                live.capture(0,0,*image.size,'ja')
            release.set()
            live._ocr[-1].result(timeout=3)
            live.capture(0,0,*image.size,'ja')
            live._ocr[-1].result(timeout=3)
            assert samples==[(255,255,255),(0,0,255)]
        finally:
            release.set()
            live.close()
