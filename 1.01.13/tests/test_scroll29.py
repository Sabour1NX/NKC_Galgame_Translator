# SPDX-License-Identifier: MIT
"""Content scrolling, local language grouping and source-pixel freshness races."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading

import pytest
from PIL import Image,ImageDraw

from nkc_galgame_translator.languages import coherent_language_groups
from nkc_galgame_translator.tracking import ObjectTracker
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.ocr import OcrCore,changed_source_indices
from nkc_galgame_translator.frame_cache import FrameCache
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.vision_core import VisionCore
from test_tracking import line,by_text,overlay_objects
from test_pipeline import FakeCore,FakeEngine,Recorder,wait_until,make_pipeline,start,finals,objects,updates


@pytest.mark.parametrize('offset',[-760,-120,2,5,180,800])
def test_scroll_exact_text_outvotes_old_screen_position(offset):
    with ObjectTracker() as tracker:
        first=by_text(tracker.update([line('Alpha heading',y=900),line('Beta heading',y=1020)]))
        moved=by_text(tracker.update([line('Alpha heading',y=900+offset),line('Beta heading',y=1020+offset)]))
        for text in first:
            assert moved[text].track_id==first[text].track_id and moved[text].revision==first[text].revision
            assert moved[text].line['y']==first[text].line['y']+offset
            assert moved[text].line.get('_content_motion')


def test_scrolled_row_not_replaced_by_new_text_occupying_its_old_position():
    with ObjectTracker() as tracker:
        before=by_text(tracker.update([line('Old heading',y=20),line('Kept heading',y=100)]))
        after=by_text(tracker.update([line('Kept heading',y=20),line('Brand new',y=100)]))
        assert after['Kept heading'].track_id==before['Kept heading'].track_id
        assert after['Kept heading'].revision==1
        assert after['Brand new'].track_id!=before['Kept heading'].track_id


def test_repeated_rows_follow_column_motion_instead_of_nearest_old_slot():
    rows=[line('Header one',y=300),line('Header two',y=340),line('Same',y=380),line('Same',y=420)]
    with ObjectTracker() as tracker:
        first=tracker.update(rows)
        second=tracker.update([{**r,'y':r['y']-225} for r in rows])
        assert [t.track_id for t in second.tracks]==[t.track_id for t in first.tracks]
        assert not second.changed_ids
        third=tracker.update([{**r,'y':r['y']-260} for r in rows[1:]])
        assert [t.track_id for t in third.tracks]==[t.track_id for t in first.tracks[1:]]
        assert first.tracks[0].track_id in third.removed_ids


def test_two_scroll_panels_keep_independent_motion_and_duplicates():
    left=[line('Left one',x=0,y=300),line('Left two',x=0,y=340),line('Same',x=0,y=380)]
    right=[line('Right one',x=500,y=300),line('Right two',x=500,y=340),line('Same',x=500,y=380)]
    with ObjectTracker() as tracker:
        first=tracker.update(left+right)
        previous={(t.line['text'],t.line['x']):t.track_id for t in first.tracks}
        second=tracker.update([{**r,'y':r['y']-220} for r in left]+[{**r,'y':r['y']+190} for r in right])
        assert all(t.track_id==previous[(t.line['text'],t.line['x'])] for t in second.tracks)


def test_confirmed_scroll_bypasses_box_debounce_without_changing_font():
    with ObjectTracker() as tracker:
        overlay=OverlayState()
        rows=[line('First heading',y=40,font_size=24),line('Second heading',y=80,font_size=24)]
        first=tracker.update(rows);overlay.apply_objects(overlay_objects(first))
        for t in first.tracks:overlay.apply_translation(t.track_id,{'text':'\u8bd1\u6587','_revision':1,'final':False})
        for delta in [2,4,6,8,10]:
            current=tracker.update([{**r,'y':r['y']+delta,'w':r['w']+3,'font_size':25} for r in rows])
            overlay.apply_objects(overlay_objects(current))
            for track,source in zip(current.tracks,rows):
                assert overlay.rendered[track.track_id]['y']==source['y']+delta
                assert overlay.rendered[track.track_id]['font_size']==24
                overlay.apply_translation(track.track_id,{'text':'\u65b0\u6d41\u5f0f\u8bd1\u6587','_revision':1,'final':False,'y':999})
                assert overlay.rendered[track.track_id]['y']==source['y']+delta


def test_single_line_continuous_small_scroll_catches_up_after_motion_confirmation():
    with ObjectTracker() as tracker:
        overlay=OverlayState();first=tracker.update([line(y=20)]).tracks[0]
        overlay.apply_objects([{'track_id':first.track_id,'revision':1,'line':first.line}])
        overlay.apply_translation(first.track_id,{'text':'\u8bd1\u6587','_revision':1,'final':True})
        for y in [22,24,26,28]:
            current=tracker.update([line(y=y)]);overlay.apply_objects(overlay_objects(current))
            if y>=24:assert overlay.rendered[first.track_id]['y']==y


def test_scrolled_minor_text_change_cannot_keep_previous_words():
    with ObjectTracker() as tracker:
        first=tracker.update([line('Welcome to the mansion',y=20)]).tracks[0]
        second=tracker.update([line('Welcome to the manslon',y=34)]).tracks[0]
        assert second.track_id==first.track_id and second.revision==2


def test_occluded_scroll_object_rejects_late_display_and_recovers_current_box():
    with ObjectTracker(max_missing=2) as tracker:
        overlay=OverlayState();first=tracker.update([line('Welcome aboard',y=300)]).tracks[0]
        overlay.apply_objects([{'track_id':first.track_id,'revision':1,'line':first.line}])
        overlay.apply_translation(first.track_id,{'text':'\u6b22\u8fce','_revision':1,'final':False})
        overlay.apply_objects(overlay_objects(tracker.update([])))
        assert not overlay.apply_translation(first.track_id,{'text':'\u6b22\u8fce\u767b\u8239','_revision':1,'final':True})
        assert not overlay.rendered
        current=tracker.update([line('Welcome aboard',y=30)]);overlay.apply_objects(overlay_objects(current))
        assert current.tracks[0].track_id==first.track_id
        overlay.apply_translation(first.track_id,{'text':'\u6b22\u8fce\u767b\u8239','_revision':1,'final':True,'y':300})
        assert overlay.rendered[first.track_id]['y']==30


def test_independent_english_button_does_not_label_japanese_paragraph(make_pipeline):
    rows=[line('\u4eca\u65e5\u306f\u5143\u6c17\u3067\u3059\u304b\u3002',y=20,w=430,h=80,font_size=18),
          line('Cancel',x=500,y=230,w=70,h=20,font_size=16)]
    p,core,engine,events,region=make_pipeline(rows,source_label_mixed_only=True)
    start(p,region);wait_until(lambda:len(finals(events))==2)
    assert all('\uff1a' not in event[2][1]['text'] for event in finals(events))
    assert {scope[1] for scope in engine.scopes}=={'en','ja'}


@pytest.mark.parametrize('change',[{'x':500},{'y':200},{'font_size':40},{'bg':[255,255,255]},{'_selection_id':2}])
def test_only_coherent_block_contributes_languages(change):
    a=line('\u30b2\u30fc\u30e0\u3092\u958b\u59cb',source_lang='ja',y=20,font_size=20)
    b=line('Start game',source_lang='en',y=48,font_size=20)
    assert coherent_language_groups([a,b],'zh-Hans')==[frozenset({'ja','en'})]*2
    groups=coherent_language_groups([a,{**b,**change}],'zh-Hans')
    assert groups==[frozenset({'ja'}),frozenset({'en'})]


def scene(rows,background=(0,0,0)):
    image=Image.new('RGB',(320,220),background);draw=ImageDraw.Draw(image)
    for row in rows:
        x,y=row['x'],row['y']
        for index in range(10):
            draw.rectangle((x+index*9,y,x+index*9+3,y+12),fill='white')
            draw.rectangle((x+index*9,y+index%3*4,x+index*9+7,y+index%3*4+2),fill='white')
    return image


def pixel_line(y=20):return line('Welcome aboard',x=10,y=y,w=100,h=16,bg=[0,0,0],fg=[255,255,255])


def test_source_glyph_check_ignores_animation_elsewhere_and_subtle_pixel_noise():
    rows=[pixel_line()]
    with scene(rows) as before:
        after=before.copy();ImageDraw.Draw(after).rectangle((160,100,310,210),fill='red')
        assert changed_source_indices(before,after,rows)==set()
        after.putpixel((10,20),(244,244,244))
        assert changed_source_indices(before,after,rows)==set()
        after.close()


@pytest.mark.parametrize('dy',[2,10,80,-12])
def test_source_glyph_check_detects_content_motion(dy):
    rows=[pixel_line(40)]
    with scene(rows) as before,scene([pixel_line(40+dy)]) as after:
        assert changed_source_indices(before,after,rows)=={0}


class SyntheticNative:
    def __init__(self,image):self.image=image;self.previous=None;self.resets=0
    def reset(self):self.previous=None;self.resets+=1
    def capture_bgra(self,*_):
        pixels=self.image.tobytes('raw','BGRX');changed=pixels!=self.previous;self.previous=pixels
        return {'changed':changed,'capture_ms':0,'bgra':pixels if changed else None}


def source_core(image,recognizer):
    core=object.__new__(OcrCore);core._lock=threading.RLock();core.native=SyntheticNative(image)
    core._source_callback=None;core._source_reference=None;core._capture_language=None
    core._capture_regions=None
    core.recognize_image=recognizer
    return core


def test_vision_cuda_fast_path_also_checks_pixels_after_local_recognition():
    rows=[pixel_line(40)];notifications=[]
    with scene(rows) as before,scene([pixel_line(90)]) as after:
        def local_ocr(*_,**__):
            core.native.image=after
            return {'lines':[{**rows[0],'confidence':99}],'engine':'rapidocr-cuda','ocr_ms':1}
        core=source_core(before,local_ocr);core.set_source_change_callback(notifications.append)
        wrapper=VisionCore(core,None,recognizer=SimpleNamespace())
        try:
            result=wrapper.capture_ocr(0,0,320,220,'en')
            assert result['source_stale'] and result['lines']==[] and notifications
            assert wrapper._frame is None and not wrapper._published
        finally:
            wrapper._pool.shutdown(wait=True,cancel_futures=True)
            if core._source_reference is not None:core._source_reference[0].close()


def test_slow_ocr_result_is_discarded_when_text_scrolled_during_recognition():
    rows=[pixel_line(40)];entered=threading.Event();release=threading.Event();notifications=[]
    def recognize(*_):entered.set();assert release.wait(2);return {'lines':rows,'ocr_ms':100}
    with scene(rows) as before,scene([pixel_line(100)]) as after:
        core=source_core(before,recognize);core.set_source_change_callback(notifications.append)
        with ThreadPoolExecutor(max_workers=1) as pool:
            job=pool.submit(core.capture_ocr,50,60,320,220,'en');assert entered.wait(1)
            core.native.image=after;release.set();result=job.result(2)
        assert result['changed'] and result['source_stale'] and result['lines']==[]
        assert notifications[-1][0]['y']==100  # Source y40 + capture-origin y60.
        core.recognize_image=lambda *_:{'lines':[pixel_line(100)],'ocr_ms':0}
        current=core.capture_ocr(50,60,320,220,'en')
        assert not current['source_stale'] and current['lines'][0]['y']==160
        core._source_reference[0].close()


def test_source_change_notification_precedes_slow_recognition_and_window_motion_is_not_scroll():
    rows=[pixel_line(40)];notifications=[]
    with scene(rows) as before,scene([pixel_line(90)]) as after:
        core=source_core(before,lambda *_:{'lines':rows,'ocr_ms':0});core.set_source_change_callback(notifications.append)
        core.capture_ocr(50,60,320,220,'en')
        core.native.reset();core.capture_ocr(-100,300,320,220,'en')
        assert notifications==[]
        core.native.image=after
        def recognize(*_):
            assert notifications and notifications[-1][0]['y']==340
            return {'lines':[pixel_line(90)],'ocr_ms':0}
        core.recognize_image=recognize
        result=core.capture_ocr(-100,300,320,220,'en')
        assert result['lines'][0]['y']==390
        core._source_reference[0].close()


def test_stale_source_hides_only_affected_stream_and_reappears_at_fresh_position(make_pipeline):
    p,core,engine,events,region=make_pipeline([line('Welcome aboard',y=20),line('Settings',y=160)])
    gate=engine.block('Welcome aboard');start(p,region)
    wait_until(lambda:len(engine.calls)==2)
    p._source_regions_changed([{'x':20,'y':20,'w':200,'h':24}])
    assert [o['line']['text'] for o in objects(events)]==['Settings']
    before=len(updates(events));gate.set();wait_until(lambda:engine.active==0)
    assert not any(event[2][2]=='Welcome aboard' for event in updates(events)[before:])
    core.set_scene([line('Welcome aboard',y=70),line('Settings',y=160)])
    wait_until(lambda:any(event[2][2]=='Welcome aboard' and event[2][1]['y']==70 and event[2][3] for event in updates(events)))
    assert engine.calls.count('Welcome aboard')==1
