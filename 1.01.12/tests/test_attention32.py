# SPDX-License-Identifier: MIT
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

from PIL import Image, ImageDraw

from nkc_galgame_translator.flash_hold import FlashHold
from nkc_galgame_translator.live_capture import LiveCapture
from nkc_galgame_translator.pointer_attention import attention_crop
from nkc_galgame_translator.pipeline import Pipeline
from test_pipeline import FakeEngine, Recorder, finals, wait_until
from test_scroll29 import SyntheticNative


def test_phase_hold_requires_fade_evidence_and_expires(monkeypatch):
    from nkc_galgame_translator import flash_hold
    timestamp=[1.0]
    monkeypatch.setattr(flash_hold,'monotonic',lambda:timestamp[0])
    row=dict(text='Message',x=10,y=20,w=70,h=16,bg=(215,230,250))
    with Image.new('RGB',(200,80),row['bg']) as background, background.copy() as bright:
        ImageDraw.Draw(bright).text((12,20),row['text'],fill=(38,46,220))
        hold=FlashHold()
        with Image.blend(background,bright,.2) as dim:
            saved,=hold.recover(bright,dim,[row])
            assert saved['_flash_hold']
            restored,=hold.recover(dim,bright,[saved])
            assert '_flash_hold' not in restored
            saved,=hold.recover(bright,dim,[row])
            timestamp[0]+=.110
            assert hold.expire([saved])==[saved]
            timestamp[0]+=.020
            assert hold.expire([saved])==[]
        ImageDraw.Draw(background).text((12,20),'Changed',fill=(38,46,220))
        assert hold.recover(bright,background,[row])==[]


def test_cursor_crop_is_independent_of_main_ocr_and_wins_dispatch():
    with Image.new('RGB',(640,400),'white') as frame:
        main_entered,main_release=Event(),Event()
        attention_entered=Event()
        source=SimpleNamespace(native=SyntheticNative(frame),_capture_regions=None)
        pointer=(320,200)
        _,left,top,_,_=attention_crop(pointer,((0,0,640,400),))
        focus=dict(text='Pointed dialogue',x=300,y=190,w=100,h=22,fg=(0,0,0),bg=(255,255,255))
        normal=dict(focus,text='Normal scan result',x=80,y=60)
        def regular(*args):
            main_entered.set()
            assert main_release.wait(3)
            return {'lines':[normal,focus],'ocr_ms':25}
        def attention(*args):
            attention_entered.set()
            return {'lines':[{**focus,'x':focus['x']-left,'y':focus['y']-top}]}
        source.recognize_image=regular
        source.recognize_attention=attention
        live=LiveCapture(source)
        live.pointer_provider=lambda:pointer
        core=SimpleNamespace(capture_ocr=live.capture,reset=source.native.reset,hide_overlay=lambda:None)
        engine,events=FakeEngine(),Recorder()
        pipe=Pipeline(core,engine,events,interval=.015,settle=.4,merge_lines=False,cursor_attention=True)
        pipe.start(lambda:(0,0,640,400),'fixture','en','zh-Hans')
        try:
            assert main_entered.wait(1) and attention_entered.wait(1)
            wait_until(lambda:len(finals(events))==1,timeout=.38)
            assert engine.calls==['Pointed dialogue']
            main_release.set()
            wait_until(lambda:len(finals(events))==2)
            assert engine.calls==['Pointed dialogue','Normal scan result']
        finally:
            main_release.set()
            pipe.stop()
            pipe.join(3)
            live.close()
