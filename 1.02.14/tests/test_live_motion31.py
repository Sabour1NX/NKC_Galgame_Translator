# SPDX-License-Identifier: MIT
from threading import Event
from types import SimpleNamespace

from PIL import Image, ImageDraw

from nkc_galgame_translator.live_capture import LiveCapture, follow_source, major_scene_change
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.presentation import OverlayState
from test_pipeline import FakeEngine, Recorder, finals, wait_until
from test_scroll29 import SyntheticNative


def row(text, x, y):
    return dict(text=text, x=x, y=y, w=65, h=18, confidence=99,
                fg=(20, 40, 230), bg=(20, 40, 30))


def scene(rows):
    image = Image.new('RGB',(420,220),(20,40,30))
    draw = ImageDraw.Draw(image)
    for line in rows:
        draw.text((line['x']+3,line['y']+1),line['text'],fill=line['fg'])
    return image


def test_repeated_moving_candidate_requires_unique_pixel_match():
    prior = row('Same',40,60)
    with scene([prior]) as original, scene([row('Same',40,34),row('Same',40,106)]) as frame:
        assert follow_source(original,frame,[prior]) == []
        selection=((0,0,150,85),)
        moved, = follow_source(original,frame,[prior],selection)
        assert moved['y']==34 and moved['_pixel_motion']==(0,-26)


def test_cut_discards_old_translation_while_worker_is_still_running():
    initial=[row('Old menu',30,40)]
    with scene(initial) as old, Image.new('RGB',old.size,'pink') as new:
        native=SyntheticNative(old)
        def recognize(frame,language):
            return {'lines':initial if frame.getpixel((0,0))==old.getpixel((0,0)) else [],'ocr_ms':1}
        live=LiveCapture(SimpleNamespace(native=native,_capture_regions=None,recognize_image=recognize))
        hidden=Event()
        core=SimpleNamespace(capture_ocr=live.capture,reset=native.reset,hide_overlay=hidden.set)
        events,engine=Recorder(),FakeEngine()
        blocked=engine.block('Old menu')
        pipe=Pipeline(core,engine,events,interval=.01,settle=0,persist_results=True)
        pipe.start(lambda:(0,0,*old.size),'Replay','en','zh-Hans')
        try:
            wait_until(lambda:'Old menu' in engine.calls)
            old_generation=pipe.generation
            native.image=new
            assert hidden.wait(2)
            assert pipe.generation!=old_generation
            assert any(kind=='clear' and gen==pipe.generation for kind,gen,_ in events.snapshot())
            blocked.set()
            wait_until(lambda:any(kind=='late_translation' for kind,_,_ in events.snapshot()))
            assert all(not payload[-1] for kind,_,payload in events.snapshot() if kind=='late_translation')
        finally:
            blocked.set()
            pipe.stop()
            pipe.join(3)
            live.close()


def test_sensitivity_detects_partial_scene_change_in_the_active_selection():
    with Image.new('RGB',(320,200),(70,80,100)) as before, before.copy() as after:
        ImageDraw.Draw(after).rectangle((0,0,159,199), fill=(106,116,136))
        assert not major_scene_change(before,after,None,0)
        assert major_scene_change(before,after,None,70)
        assert major_scene_change(before,after,None,100)
        assert not major_scene_change(before,after,[(160,0,160,200)],100)


def test_pale_menu_clears_vanished_warning_without_waiting_for_ocr():
    rows=[row('Warning',30,40),row('Continue',30,90)]
    with Image.new('RGB',(420,220),(255,239,249)) as warning:
        draw=ImageDraw.Draw(warning)
        for item in rows:
            item['bg']=(255,239,249)
            draw.text((item['x'],item['y']),item['text'],fill=item['fg'])
        menu=warning.copy()
        ImageDraw.Draw(menu).rectangle((29,39,100,64),fill=(250,223,240))
        native=SyntheticNative(warning)
        blocked = Event()
        def recognize(frame,language):
            if frame.getpixel((29,39))==(255,239,249):
                return {'lines':rows,'ocr_ms':1}
            blocked.wait(3)
            return {'lines':rows[1:],'ocr_ms':1}
        live=LiveCapture(SimpleNamespace(native=native,_capture_regions=None,recognize_image=recognize))
        events,engine=Recorder(),FakeEngine()
        core=SimpleNamespace(capture_ocr=live.capture,reset=native.reset,hide_overlay=lambda:None)
        pipe=Pipeline(core,engine,events,interval=.01,settle=0,persist_results=True,merge_lines=False)
        overlay=OverlayState(hold_until_next=True,hold_seconds=10)
        seen=0
        def update():
            nonlocal seen
            batch=events.snapshot()
            for kind,gen,payload in batch[seen:]:
                if kind=='source_changed':overlay.discard_changed_sources(payload)
                if kind=='objects':overlay.apply_objects(payload)
                if kind=='translation':overlay.apply_translation(payload[0],payload[1])
            seen=len(batch)
            overlay.expire_held()
            return len(overlay.rendered)
        pipe.start(lambda:(0,0,*warning.size),'Replay','en','zh-Hans')
        try:
            wait_until(lambda:update()==2)
            generation=pipe.generation
            identity=next(key for key,entry in overlay.objects.items() if entry['line']['text']=='Warning')
            old_result=dict(overlay.rendered[identity])
            native.image=menu
            wait_until(lambda:update()==1,timeout=1.5)
            assert any(kind=='source_changed' for kind,_,_ in events.snapshot())
            assert identity not in overlay.rendered and generation==pipe.generation
            assert not overlay.apply_late(identity,old_result)
            assert next(iter(overlay.objects.values()))['line']['text']=='Continue'
        finally:
            blocked.set()
            pipe.stop()
            pipe.join(3)
            live.close()
            menu.close()


def test_verified_scroll_moves_only_changed_box_during_blocked_recognition():
    initial = [row('Header',180,28),row('Scroll',40,88)]
    moved = [initial[0],row('Scroll',40,84)]
    replaced = [initial[0],row('Scroll',40,80),row('New text',40,130)]
    with scene(initial) as first, scene(moved) as second, scene(replaced) as third:
        native = SyntheticNative(first)
        worker_entered, worker_release = Event(), Event()
        calls = []

        def recognize(image, language):
            calls.append(language)
            if len(calls) == 1:
                return {'lines':initial,'ocr_ms':3}
            worker_entered.set()
            assert worker_release.wait(3)
            return {'lines':replaced if image.tobytes()==third.tobytes() else moved,'ocr_ms':300}

        live = LiveCapture(SimpleNamespace(native=native,_capture_regions=None,recognize_image=recognize))
        core = SimpleNamespace(capture_ocr=live.capture,reset=native.reset,hide_overlay=lambda:None)
        events, engine=Recorder(),FakeEngine()
        pipe=Pipeline(core,engine,events,interval=.03,settle=0,merge_lines=False)
        pipe.start(lambda:(0,0,420,220),'fixture','en','zh-Hans')

        def last():
            batches = [payload for event,_,payload in events.snapshot() if event=='objects']
            return {item['line']['text']:item for item in batches[-1]} if batches else {}

        try:
            wait_until(lambda:len(finals(events))==2)
            first_ids={key:(value['track_id'],value['revision']) for key,value in last().items()}
            native.image=second
            assert worker_entered.wait(1)
            native.image=third
            wait_until(lambda:last().get('Scroll',{}).get('line',{}).get('y')==80)
            assert 'New text' not in last() and len(engine.scopes)==2
            assert last()['Scroll']['line']['_content_motion']==(0,-4)
            assert last()['Header']['line']['y']==28
            assert {key:(value['track_id'],value['revision']) for key,value in last().items()}==first_ids
            worker_release.set()
            wait_until(lambda:len(finals(events))==3)
            assert sorted(engine.calls)==['Header','New text','Scroll']
        finally:
            worker_release.set()
            pipe.stop()
            pipe.join(3)
            live.close()
