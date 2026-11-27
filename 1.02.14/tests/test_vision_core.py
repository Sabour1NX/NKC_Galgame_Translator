# SPDX-License-Identifier: MIT
"""Real worker scheduling with fake pixels/recognizer; no API, native DLL or GUI."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image

import nkc_galgame_translator.vision_core as module
from nkc_galgame_translator.translation import TranslationError
from nkc_galgame_translator.layout import merge_dialogue_lines


class Clock:
    def __init__(self):self.now=100.
    def advance(self,seconds):self.now+=seconds


class FakeNative:
    def __init__(self):
        self.scene=1;self.alpha=0;self.background=0;self.previous=None;self.captures=0
    def reset(self):self.previous=None
    def capture_bgra(self,x,y,w,h):
        self.captures+=1
        identity=(self.scene,self.background,x,y,w,h)
        changed=identity!=self.previous;self.previous=identity
        pixels=None
        if changed:
            pixels=bytearray(bytes((0,0,self.scene,self.alpha))*(w*h))
            pixels[-4:]=bytes((0,self.background,0,self.alpha))
        return {'changed':changed,'capture_ms':.1,
                'bgra':bytes(pixels) if pixels is not None else None}


class FakeCore:
    def __init__(self):
        self.native=FakeNative();self._lock=threading.RLock()
        self._native_languages=['en-US'];self.local_calls=[];self.closed=0;self.blank=False
        self.jitter_text=False;self.anchor_x=2
    def reset(self):self.native.reset()
    def recognize_image(self,image,language,mode):
        scene=image.getpixel((0,0))[0];self.local_calls.append((scene,language,mode))
        return {'engine':'local','ocr_ms':.2,'lines':[] if self.blank else [
            {'text':f'local {scene}'+(f' OCR guess {len(self.local_calls)}' if self.jitter_text else ''),
             'x':self.anchor_x,'y':3,'w':6,'h':4,'confidence':42,
             'bg':[0,0,0],'fg':[255,255,255]}]}
    def close(self):self.closed+=1


class Recognizer:
    def __init__(self):
        self.calls=[];self.lock=threading.Lock();self.active=0;self.peak=0
        self.block=True;self.error=None;self.mutate=False
    def recognize(self,image,anchors,language,*,cancelled):
        scene=image.getpixel((0,0))[0]
        call={'scene':scene,'language':language,'cancelled':cancelled,'gate':threading.Event(),
              'anchor_texts':[line['text'] for line in anchors]}
        with self.lock:
            self.calls.append(call);self.active+=1;self.peak=max(self.peak,self.active)
        try:
            if self.block:assert call['gate'].wait(3),'fake recognizer was not released'
            if self.mutate:
                anchors[0]['x']=99999;anchors[0]['bg'][0]=99
            if self.error:raise self.error
            return [{**line,'text':f'refined {scene} {language}'} for line in anchors]
        finally:
            with self.lock:self.active-=1
    def release_all(self):
        with self.lock:
            for call in self.calls:call['gate'].set()


def wait_until(predicate,timeout=2):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:time.sleep(.002)
    assert predicate(),'worker did not reach expected state'


@pytest.fixture
def rig(monkeypatch):
    clock=Clock()
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock.now,perf_counter=time.perf_counter))
    core=FakeCore();recognizer=Recognizer()
    wrapper=module.VisionCore(core,None,recognizer=recognizer)
    yield wrapper,core,recognizer,clock
    recognizer.release_all();wrapper.close()
    wrapper._pool.shutdown(wait=True,cancel_futures=True)


def capture(wrapper,language='en',x=100,y=200):
    return wrapper.capture_ocr(x,y,16,12,language)


def launch(rig):
    wrapper,_,recognizer,clock=rig
    first=capture(wrapper)
    assert first['changed'] and first['lines']==[]
    clock.advance(.5);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==1)
    return recognizer.calls[0]


def finish(wrapper,call):
    call['gate'].set()
    wait_until(lambda:wrapper._future.done())
    return capture(wrapper,call['language'])


def test_stable_wait_and_three_second_default_request_spacing(rig):
    wrapper,core,recognizer,clock=rig
    capture(wrapper);clock.advance(.44);capture(wrapper)
    assert not recognizer.calls and wrapper._future is None
    clock.advance(.02);capture(wrapper);wait_until(lambda:len(recognizer.calls)==1)
    first=recognizer.calls[0]
    result=finish(wrapper,first)
    assert result['lines'][0]['text']=='refined 1 en'
    core.native.scene=2;capture(wrapper)
    clock.advance(2.99);capture(wrapper)
    assert len(recognizer.calls)==1
    clock.advance(.02);capture(wrapper);wait_until(lambda:len(recognizer.calls)==2)
    assert recognizer.calls[1]['scene']==2


def test_old_frame_never_published_and_many_changes_do_not_queue_jobs(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig)
    original_future=wrapper._future
    for scene in range(2,42):
        core.native.scene=scene
        observed=capture(wrapper)
        assert observed['changed'] and not observed['lines']
        clock.advance(3.1);capture(wrapper)
        assert wrapper._future is original_future
    assert first['cancelled']() and len(recognizer.calls)==1 and recognizer.peak==1
    # Finishing a stale response cannot publish it, even though its HTTP job ran.
    first['gate'].set();wait_until(lambda:wrapper._future.done())
    discarded=capture(wrapper)
    assert not discarded['changed'] and discarded['lines']==[]
    wait_until(lambda:len(recognizer.calls)==2)
    assert recognizer.calls[1]['scene']==41 and recognizer.peak==1
    latest=finish(wrapper,recognizer.calls[1])
    assert latest['lines'][0]['text']=='refined 41 en'


def test_completed_old_result_is_discarded_when_capture_detects_new_pixels(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);first['gate'].set();wait_until(lambda:wrapper._future.done())
    core.native.scene=2
    observed=capture(wrapper)
    assert observed['changed'] and observed['lines']==[]
    clock.advance(3.1);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==2)
    assert recognizer.calls[1]['scene']==2


def test_same_rgb_cache_hit_skips_network_and_local_ocr_after_focus_reset_or_move(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);finish(wrapper,first)
    local_count=len(core.local_calls)
    wrapper.cancel_pending();core.native.alpha=255
    reused=capture(wrapper,x=400,y=-100)
    assert reused['changed'] and reused['lines'][0]['text']=='refined 1 en'
    assert (reused['lines'][0]['x'],reused['lines'][0]['y'])==(402,-97)
    assert len(recognizer.calls)==1 and len(core.local_calls)==local_count
    clock.advance(20);capture(wrapper,x=400,y=-100)
    assert len(recognizer.calls)==1


def test_focus_cancellation_prevents_stale_publication_and_can_restart_same_pixels(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig)
    wrapper.cancel_pending()
    assert first['cancelled']() and wrapper._frame is None
    first['gate'].set();wait_until(lambda:wrapper._future.done())
    assert capture(wrapper)['lines']==[]
    clock.advance(3.1);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==2)
    assert recognizer.calls[1]['scene']==1


def test_language_change_on_identical_pixels_starts_fresh_scope(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);finish(wrapper,first)
    changed=capture(wrapper,'ja')
    assert changed['changed'] and changed['lines']==[]
    assert core.local_calls[-1]==(1,'ja','auto')
    clock.advance(3.1);capture(wrapper,'ja')
    wait_until(lambda:len(recognizer.calls)==2)
    assert recognizer.calls[1]['language']=='ja'


@pytest.mark.parametrize('error,expected',[
    (RuntimeError('private path and API key must not cross this boundary'),'AI \u56fe\u50cf\u7cbe\u8bfb\u5931\u8d25\uff0c\u7ee7\u7eed\u4f7f\u7528\u672c\u5730\u8bc6\u522b\u3002'),
    (TranslationError('controlled API error'),'controlled API error'),
])
def test_failed_recognizer_falls_back_to_immutable_local_bounds(rig,error,expected):
    wrapper,core,recognizer,clock=rig
    recognizer.error=error;recognizer.mutate=True
    first=launch(rig);result=finish(wrapper,first)
    assert result['engine']=='local-fallback' and result['vision_error']==expected
    line=result['lines'][0]
    assert (line['text'],line['x'],line['y'],line['w'],line['h'])==('local 1',102,203,6,4)
    assert line['bg']==[0,0,0] and line['confidence']==42
    # Failures are cached briefly to prevent quota-spending retry storms.
    wrapper.reset();reused=capture(wrapper)
    assert reused['engine']=='local-fallback' and len(recognizer.calls)==1
    clock.advance(31);wrapper.reset();capture(wrapper);clock.advance(.5);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==2)


def test_blank_local_anchors_do_not_issue_an_image_request(rig):
    wrapper,core,recognizer,clock=rig
    core.blank=True;capture(wrapper);clock.advance(10)
    result=capture(wrapper)
    assert result['changed'] and result['lines']==[]
    assert not recognizer.calls and wrapper._future is None


def test_close_is_nonblocking_idempotent_and_does_not_stop_other_executor(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig)
    with ThreadPoolExecutor(max_workers=1) as unrelated:
        began=time.monotonic();wrapper.close()
        assert time.monotonic()-began<.5
        assert first['cancelled']() and core.closed==1
        assert unrelated.submit(lambda:42).result(timeout=1)==42
        wrapper.close();assert core.closed==1
        with pytest.raises(RuntimeError,match='closed'):capture(wrapper)
    first['gate'].set()


def test_success_cache_is_bounded_to_sixteen_frames(rig):
    wrapper,core,recognizer,clock=rig
    recognizer.block=False
    for scene in range(1,20):
        core.native.scene=scene;capture(wrapper);clock.advance(3.1);capture(wrapper)
        wait_until(lambda:wrapper._future is not None and wrapper._future.done())
        result=capture(wrapper)
        assert result['lines'][0]['text']==f'refined {scene} en'
        assert len(wrapper._cache)<=16
    assert len(wrapper._cache)==16


def test_fifty_background_animation_frames_do_not_restart_stability_or_pending_work(rig):
    wrapper,core,recognizer,clock=rig
    core.jitter_text=True
    assert capture(wrapper)['changed']
    generation=wrapper._generation;ready_at=wrapper._ready_at
    # Start while the full RGB frame changes on every poll. Only text pixels
    # and their geometry stay constant; OCR guesses deliberately vary too.
    for frame in range(1,51):
        core.native.background=frame;clock.advance(.05)
        result=capture(wrapper)
        assert not result['changed'] and result['lines']==[]
        assert wrapper._generation==generation and wrapper._ready_at==ready_at
    wait_until(lambda:len(recognizer.calls)==1)
    call=recognizer.calls[0]
    assert not call['cancelled']()
    call['gate'].set();wait_until(lambda:wrapper._future.done())
    core.native.background=51
    published=capture(wrapper)
    assert published['changed'] and published['lines'][0]['text']=='refined 1 en'
    # Animation after publication preserves displayed text and spends no call.
    for frame in range(52,102):
        core.native.background=frame;clock.advance(.1)
        assert not capture(wrapper)['changed']
    assert len(recognizer.calls)==1 and len(wrapper._cache)==1
    assert len(wrapper._raw_cache)==16
    assert all(len(key[-1])==32 and len(value[0][-1])==32 for key,value in wrapper._raw_cache.items())


def test_anchor_movement_cancels_even_with_identical_rgb_pixels(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);generation=wrapper._generation
    core.anchor_x=3;core.native.background=1
    changed=capture(wrapper)
    assert changed['changed'] and changed['lines']==[]
    assert first['cancelled']() and wrapper._generation>generation
    first['gate'].set();wait_until(lambda:wrapper._future.done())
    clock.advance(3.1);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==2)
    final=finish(wrapper,recognizer.calls[1])
    assert final['lines'][0]['x']==103


def test_anchor_signature_streams_union_pixels_once_and_retains_only_digest():
    image=Image.new('RGB',(64,64),(10,20,30))
    class CountCrops:
        size=image.size
        def __init__(self):self.area=0;self.peak=0
        def crop(self,box):
            area=(box[2]-box[0])*(box[3]-box[1]);self.area+=area;self.peak=max(self.peak,area)
            return image.crop(box)
    # Worst-case duplicate/overlapping boxes must not multiply copied pixels.
    anchors=[{'x':i%8,'y':i%16,'w':56,'h':48,'text':str(i)} for i in range(512)]
    counted=CountCrops();key=module.anchor_signature(counted,anchors,'en')
    assert counted.area<=64*64 and counted.peak<=64*64
    assert key[:3]==('en',64,64) and isinstance(key[-1],bytes) and len(key[-1])==32
    reordered=[{**line,'text':'different OCR guess'} for line in reversed(anchors)]
    assert module.anchor_signature(image,reordered,'en')==key
    assert module.anchor_signature(image,anchors[:-1],'en')!=key
    with pytest.raises(ValueError):module.anchor_signature(image,anchors+[anchors[0]],'en')


def test_signature_ignores_outside_pixels_but_detects_text_region_changes():
    image=Image.new('RGB',(16,12),'black');anchors=[{'x':2,'y':3,'w':6,'h':4}]
    original=module.anchor_signature(image,anchors,'en')
    image.putpixel((15,11),(255,0,0))
    assert module.anchor_signature(image,anchors,'en')==original
    image.putpixel((3,4),(255,255,255))
    assert module.anchor_signature(image,anchors,'en')!=original
    assert module.anchor_signature(image,anchors,'ja')!=original


def recognize_geometry_fixture(rig,rows):
    wrapper,core,recognizer,clock=rig
    lines=[{'text':text,'x':x,'y':y,'w':w,'h':h,'bg':[0,0,0],'fg':[255,255,255]}
           for text,x,y,w,h in rows]
    # Reverse the local backend order to exercise the production sort.
    core.recognize_image=lambda *_args,**_kwargs:{'lines':list(reversed(lines)),'ocr_ms':.1,'engine':'local'}
    received=[]
    def echo(_image,anchors,_language,**_kwargs):
        received.append(anchors)
        return anchors
    recognizer.recognize=echo
    wrapper.capture_ocr(0,0,1021,767,'en');clock.advance(.5)
    wrapper.capture_ocr(0,0,1021,767,'en')
    wait_until(lambda:wrapper._future is not None and wrapper._future.done())
    result=wrapper.capture_ocr(0,0,1021,767,'en')
    assert len(received)==1
    return lines,received[0],result


def test_native_sixteen_fragments_are_fifteen_physical_vision_anchors_and_two_paragraphs(rig):
    left=[
        ('On a routine',27,90,305,32),('trading mission',30,125,379,35),
        ('in the backwater',30,159,405,32),('Karonus system',27,194,356,36),
        ('your merchant',27,228,328,36),('ship, the',27,263,229,36),
        ('PRINCESS BLUE',27,298,331,31),('picks up a',27,332,254,36),
        ('Small Craft',27,367,277,32),('Distress Beacon.',27,401,401,32)]
    bottom=[
        ('"No life readings,"',24,570,455,36),('says Captain',538,570,306,36),
        ('Dalfree. "Looks like a derelict.',27,605,810,32),
        ("You're on EVA duty, Private, so scope",27,639,945,36),
        ("it out. Make it quick! We're behind",30,674,891,36),('schedule."',27,708,254,32)]
    original,anchors,result=recognize_geometry_fixture(rig,left+bottom)
    assert len(original)==16 and len(anchors)==15
    assert all('\n' not in line['text'] and '\r' not in line['text'] for line in anchors)
    assert anchors[10]['text']=='"No life readings," says Captain'
    assert tuple(anchors[10][key] for key in ('x','y','w','h'))==(24,570,820,36)
    assert original[10]['text']=='"No life readings,"' and original[11]['text']=='says Captain'
    paragraphs=merge_dialogue_lines(result['lines'])
    assert len(paragraphs)==2
    assert [len(line['text'].splitlines()) for line in paragraphs]==[10,5]
    assert paragraphs[1]['text'].count('says Captain')==1


@pytest.mark.parametrize('rows',[
    [('Load Game',30,100,145,28),('New Game',340,100,130,28),
     ('Settings',30,137,130,28),('Exit',340,137,64,28)],
    [('Create New Campaign',24,570,455,36),('Load Existing Campaign',538,570,306,36),
     ('Choose an option to continue playing.',27,605,810,32)],
])
def test_vision_preprocessing_keeps_ordinary_buttons_and_title_case_grid_separate(rig,rows):
    original,anchors,result=recognize_geometry_fixture(rig,rows)
    assert anchors==original
    assert merge_dialogue_lines(result['lines'])==original


def hud_rig(rig):
    """Two local anchors: one unchanged label and one animated instrument."""
    wrapper,core,recognizer,clock=rig
    native=core.native
    native.stable=1
    def pixels(x,y,w,h):
        identity=(native.stable,native.scene,x,y,w,h)
        changed=identity!=native.previous;native.previous=identity
        image=Image.new('RGB',(w,h),(native.stable,0,0))
        image.paste((native.scene,0,0),(10,3,15,7))
        return {'changed':changed,'capture_ms':.1,
                'bgra':image.tobytes('raw','BGRX') if changed else None}
    native.capture_bgra=pixels
    core.color=[0,0,0]
    core.hud_word='Power failure'
    core.hud_x=10
    def local(image,language,mode):
        core.local_calls.append((language,mode))
        return {'engine':'local','ocr_ms':.2,'lines':[
            {'text':'Gun laser','x':core.anchor_x,'y':3,'w':6,'h':4,
             'bg':list(core.color),'fg':[255,255,255]},
            {'text':f'{core.hud_word} {native.scene}','x':core.hud_x,'y':3,'w':5,'h':4,
             'bg':[0,0,0],'fg':[255,255,255]}]}
    core.recognize_image=local
    return wrapper,core,recognizer,clock


def test_changed_hud_preserves_exact_unchanged_anchor_during_ai_wait(rig):
    wrapper,core,recognizer,clock=hud_rig(rig)
    first=launch(rig)
    assert len(finish(wrapper,first)['lines'])==2
    for scene in range(2,42):
        core.native.scene=scene;clock.advance(.1)
        result=capture(wrapper)
        assert result['changed'] and len(result['lines'])==1
        assert result['lines'][0]['text']=='refined 1 en'
        assert (result['lines'][0]['x'],result['lines'][0]['y'])==(102,203)
        assert result['engine']=='vision-waiting'
    assert len(recognizer.calls)==1  # Only stable text persists, no retry storm.
    assert not capture(wrapper)['changed']


@pytest.mark.parametrize('change',['pixel','geometry','color','language','focus','missing'])
def test_retained_vision_anchor_requires_all_current_local_evidence(rig,change):
    wrapper,core,recognizer,clock=hud_rig(rig)
    first=launch(rig);finish(wrapper,first)
    core.native.scene=2
    language='en'
    if change=='pixel':core.native.stable=2
    elif change=='geometry':core.anchor_x=3
    elif change=='color':core.color=[1,0,0]
    elif change=='language':language='ja'
    elif change=='focus':wrapper.cancel_pending()
    elif change=='missing':core.recognize_image=lambda *_args,**_kwargs:{'lines':[],'ocr_ms':.1,'engine':'local'}
    result=capture(wrapper,language)
    assert result['changed'] and result['lines']==[]


@pytest.mark.parametrize('mode',['auto','pixel','native'])
def test_vision_local_anchors_respect_selected_ocr_mode(rig,mode):
    wrapper,core,recognizer,clock=rig
    core.mode=mode
    capture(wrapper)
    assert core.local_calls[-1]==(1,'en',mode)


def test_per_anchor_fingerprints_bound_overlapping_crop_area():
    image=Image.new('RGB',(64,64),'black')
    class CountCrops:
        size=image.size
        def __init__(self):self.area=0
        def crop(self,box):
            self.area+=(box[2]-box[0])*(box[3]-box[1])
            return image.crop(box)
    lines=[{'x':i%8,'y':i%8,'w':56,'h':56,'bg':[0,0,0],'fg':[255,255,255]}
           for i in range(512)]
    counted=CountCrops();keys=list(module._line_fingerprints(counted,lines,'en'))
    assert keys and counted.area<=64*64
    assert all(isinstance(key[-1],bytes) and len(key[-1])==32 for key,_ in keys)


def test_ignored_changing_hud_neither_resets_settle_nor_cancels_first_ai_job(rig):
    wrapper,core,recognizer,clock=hud_rig(rig)
    core.hud_word='SYS'
    initial=capture(wrapper)
    assert initial['changed'] and len(initial['lines'])==1
    assert initial['lines'][0]['_preserve_source']
    generation=wrapper._generation;ready=wrapper._ready_at
    for scene in range(2,12):
        core.native.scene=scene;clock.advance(.1)
        assert not capture(wrapper)['changed']
        assert wrapper._generation==generation and wrapper._ready_at==ready
    wait_until(lambda:len(recognizer.calls)==1)
    call=recognizer.calls[0]
    assert call['anchor_texts']==['Gun laser'] and not call['cancelled']()
    final=finish(wrapper,call)
    assert len(final['lines'])==2
    assert final['lines'][0]['text']=='refined 1 en'
    assert final['lines'][1]['text']=='SYS 11' and final['lines'][1]['_preserve_source']
    assert len(wrapper._published)==1
    for scene in range(12,42):
        core.native.scene=scene;clock.advance(.1)
        assert not capture(wrapper)['changed']
    assert len(recognizer.calls)==1


def test_ignored_barrier_geometry_updates_without_cancelling_stable_text(rig):
    wrapper,core,recognizer,clock=hud_rig(rig)
    core.hud_word='SYS'
    capture(wrapper);clock.advance(.5);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==1)
    finish(wrapper,recognizer.calls[0]);generation=wrapper._generation
    core.hud_x=9;core.native.scene=2
    update=capture(wrapper)
    assert update['changed'] and len(update['lines'])==2
    assert update['lines'][0]['text']=='refined 1 en'
    assert update['lines'][1]['x']==109 and update['lines'][1]['_preserve_source']
    assert wrapper._generation==generation and len(recognizer.calls)==1


def test_raw_cache_restores_current_frame_barriers_not_last_cached_scene(rig):
    wrapper,core,recognizer,clock=hud_rig(rig)
    core.hud_word='SYS'
    capture(wrapper);clock.advance(.5);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==1)
    finish(wrapper,recognizer.calls[0])
    core.native.scene=2;capture(wrapper)
    wrapper.reset();core.native.scene=1
    result=capture(wrapper)
    assert result['changed'] and result['lines'][1]['text']=='SYS 1'
    assert len(recognizer.calls)==1


def test_only_ignored_anchors_issue_no_vision_request(rig):
    wrapper,core,recognizer,clock=rig
    def local(*_args,**_kwargs):
        return {'lines':[{'text':text,'x':index*4,'y':3,'w':3,'h':4,
                         'bg':[0,0,0],'fg':[255,255,255]}
                        for index,text in enumerate(('300','SYS f ebm','Neu or Id gane?'))],
                'engine':'local','ocr_ms':.1}
    core.recognize_image=local
    result=capture(wrapper)
    assert len(result['lines'])==3 and all(line['_preserve_source'] for line in result['lines'])
    clock.advance(10);capture(wrapper)
    assert not recognizer.calls and wrapper._future is None


def test_vision_filter_keeps_barriers_and_suppresses_spanning_useful_anchor():
    local={'lines':[
        {'text':'Visible paragraph','x':1,'y':1,'w':12,'h':8},
        {'text':'300','x':3,'y':3,'w':3,'h':3},
        {'text':'Gun laser','x':20,'y':3,'w':12,'h':3}], 'ocr_ms':1}
    eligible,barriers=module._local_anchors(local,'en')
    assert [line['text'] for line in eligible['lines']]==['Gun laser']
    assert {line['text'] for line in barriers}=={'Visible paragraph','300'}
    assert all(line['_preserve_source'] for line in barriers)
    assert all('_preserve_source' not in line for line in local['lines'])


def test_trusted_cuda_frame_publishes_immediately_without_cloud_ocr(rig):
    wrapper,core,recognizer,clock=rig
    original=core.recognize_image
    def gpu(*args,**kwargs):
        result=original(*args,**kwargs)
        result.update(engine='rapidocr-cuda',cuda_status='active')
        result['lines'][0].update(text='Welcome',confidence=99)
        return result
    core.recognize_image=gpu
    first=capture(wrapper)
    assert first['changed'] and first['lines'][0]['text']=='Welcome'
    assert first['lines'][0]['x']==102 and first['vision_review']=='not_needed'
    clock.advance(10);capture(wrapper)
    assert not recognizer.calls and not wrapper.pending
    wrapper.reset()
    assert capture(wrapper,x=400)['lines'][0]['x']==402
    assert not recognizer.calls


def test_uncertain_cuda_frame_still_uses_cloud_review(rig):
    wrapper,core,recognizer,clock=rig
    original=core.recognize_image
    def gpu(*args,**kwargs):
        result=original(*args,**kwargs)
        result.update(engine='rapidocr-cuda',cuda_status='active')
        result['lines'][0].update(text='Welcome',confidence=82)
        return result
    core.recognize_image=gpu
    first=launch(rig)
    assert first['anchor_texts']==['Welcome']
    assert finish(wrapper,first)['lines'][0]['text']=='refined 1 en'
