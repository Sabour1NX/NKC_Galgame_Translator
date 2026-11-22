# SPDX-License-Identifier: MIT
from types import SimpleNamespace
import time

from PIL import Image, ImageDraw, ImageFont

from nkc_galgame_translator.live_capture import LiveCapture, follow_source
from test_scroll29 import SyntheticNative


def frame(background, text):
    image=Image.new('RGB',(360,110),background)
    ImageDraw.Draw(image).text((18,31),text,fill='white',
        font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',25))
    return image


def source_line():
    return dict(x=17,y=31,w=270,h=38,text='Office begins tomorrow.',
        fg=[255]*3,bg=[52,84,108],_source_ink=[18,35,270,30])


def test_moving_background_keeps_original_source_but_changed_glyphs_do_not():
    row=source_line()
    with frame((52,84,108),row['text']) as before, frame((105,136,165),row['text']) as after, frame(
            (105,136,165),'Office begins next week.') as new_text:
        refresh=[]
        assert follow_source(before,after,[row],refresh=refresh)==[row] and refresh
        assert follow_source(after,new_text,[row])==[]


def test_large_background_change_with_same_dialogue_repaints_without_a_scene_cut():
    row=source_line()
    with frame((52,84,108),row['text']) as before,frame((110,150,170),row['text']) as after:
        native=SyntheticNative(before)
        core=SimpleNamespace(native=native,_capture_regions=(),
            recognize_image=lambda *_:dict(lines=[row],ocr_ms=0))
        live=LiveCapture(core)
        try:
            for i in range(100):
                if live.capture(0,0,*before.size,'en')['changed']:break
                time.sleep(.01)
            assert live.lines and live.lines[0]['text']==row['text']
            native.image=after
            result=live.capture(0,0,*before.size,'en')
            assert result['background_refresh']
            assert not result.get('scene_cut') and not result['changed']
            assert live.lines and live.lines[0]['text']==row['text']
        finally:live.close()



def test_final_translation_is_not_requested_again_during_background_animation():
    from nkc_galgame_translator.pipeline import Pipeline
    from test_pipeline import FakeEngine, Recorder, finals, wait_until
    row=source_line()
    changed={**row,'text':'Office begins next week.'}
    with frame((52,84,108),row['text']) as before,frame((105,136,165),row['text']) as after,frame(
            (105,136,165),changed['text']) as new_text:
        native=SyntheticNative(before)
        core=SimpleNamespace(native=native,_capture_regions=(),
            recognize_image=lambda source,*_:dict(lines=[row if native.image is not new_text else changed],ocr_ms=0),
            hide_overlay=lambda:None)
        live=LiveCapture(core)
        core.capture_ocr=live.capture
        core.set_ready_callback=lambda callback:setattr(live,'ready_callback',callback)
        def reset():
            live.reset();native.reset()
        core.reset=reset
        engine=FakeEngine();events=Recorder()
        pipe=Pipeline(core,engine,events,interval=.02,settle=0,persist_results=True)
        try:
            pipe.start(lambda:(0,0,*before.size),'sample','en','zh-Hans')
            wait_until(lambda:len(finals(events))==1)
            initial=pipe.generation
            native.image=after
            wait_until(lambda:any(kind=='background' for kind,_,_ in events.snapshot()))
            assert pipe.generation==initial
            assert engine.calls==[row['text']]
            native.image=new_text
            wait_until(lambda:engine.calls==[row['text'],changed['text']])
        finally:
            pipe.stop()
            assert pipe.join(3)
            live.close()
