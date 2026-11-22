# SPDX-License-Identifier: MIT
"""Refresh races with real worker scheduling; synthetic OCR/network, no desktop."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading
import time

import pytest
from PIL import Image

from nkc_galgame_translator.frame_cache import FrameCache
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.translation import BudgetExceeded, TranslationError
from test_pipeline import FakeCore, FakeEngine, Recorder, line, wait_until
from test_translation import factory, sse_response, tr
from test_vision_core import rig, capture, launch, finish


class EpochEngine(FakeEngine):
    def __init__(self):
        super().__init__();self.epoch=0;self.request_epochs=[];self.entered=[]
    def advance_request_epoch(self):
        self.epoch+=1;return self.epoch
    def translate(self,*args,request_epoch=None,**kwargs):
        self.request_epochs.append(request_epoch)
        return super().translate(*args,**kwargs)


def cleanup(pipeline,engine,core):
    core.capture_release.set();engine.release_all()
    pipeline.stop();assert pipeline.join(3)
    pipeline.pool.shutdown(wait=True,cancel_futures=True)


def test_refresh_same_pixels_new_epoch_old_callbacks_hidden_and_repeats_coalesced():
    core=FakeCore([line('Welcome aboard')]);engine=EpochEngine();events=Recorder()
    gate=engine.block('Welcome aboard')
    p=Pipeline(core,engine,events,interval=.01,settle=0,translation_workers=2)
    region=(30,40,500,400);providers=[]
    def provider():providers.append(region);return region
    try:
        assert not p.request_retranslation()
        p.start(provider,'game','en','zh-Hans')
        wait_until(lambda:len(engine.calls)==1)
        previous=p.generation
        assert p.request_retranslation() and p.generation!=previous
        refreshed=p.generation
        for _ in range(100):assert p.request_retranslation()
        wait_until(lambda:len(engine.calls)==2)
        assert engine.request_epochs==[1,2] and p.generation==refreshed
        assert p.get_stats()['refresh_pending'] and p.get_stats()['inflight']<=2
        gate.set()
        wait_until(lambda:not p.get_stats()['refresh_pending'])
        clear_index=next(i for i,e in enumerate(events.items) if e[0]=='clear' and e[1]==refreshed)
        assert all(e[1]==refreshed for e in events.items[clear_index:] if e[0]=='translation')
        assert any(e[0]=='translation' and e[2][3] for e in events.items[clear_index:])
        assert core.ocr_runs==2 and set(providers)=={region}
        assert p.request_retranslation()
        wait_until(lambda:len(engine.calls)==3)
        assert engine.request_epochs[-1]==3
    finally:cleanup(p,engine,core)
    assert not p.request_retranslation()


def test_refresh_waits_for_selected_target_and_does_not_capture_another_window():
    core=FakeCore([line('Welcome aboard')]);engine=EpochEngine();events=Recorder();region=[(0,0,500,400)]
    p=Pipeline(core,engine,events,interval=.01,settle=0)
    try:
        p.start(lambda:region[0],'game','en','zh-Hans')
        wait_until(lambda:len(engine.calls)==1)
        region[0]=None;wait_until(lambda:not p._capture_active)
        n=core.captures
        assert p.request_retranslation()
        time.sleep(.05)
        assert core.captures==n and len(engine.calls)==1
        region[0]=(0,0,500,400)
        wait_until(lambda:len(engine.calls)==2)
    finally:cleanup(p,engine,core)


def test_refresh_interrupts_capture_poll_wait_and_stop_does_not_wait_for_network():
    core=FakeCore([line('Welcome aboard')]);engine=EpochEngine();events=Recorder()
    p=Pipeline(core,engine,events,interval=5,settle=0,translation_workers=1)
    try:
        p.start(lambda:(0,0,500,400),'game','en','zh-Hans')
        wait_until(lambda:len(engine.calls)==1)
        wait_until(lambda:engine.active==0)
        engine.block('Welcome aboard')
        assert p.request_retranslation()
        wait_until(lambda:len(engine.calls)==2,timeout=1)
        started=time.monotonic();p.stop();assert p.join(.5)
        assert time.monotonic()-started<.8
    finally:cleanup(p,engine,core)


def test_blank_refresh_completes_without_translation():
    core=FakeCore([]);engine=EpochEngine();p=Pipeline(core,engine,Recorder(),interval=.01,settle=0)
    try:
        p.start(lambda:(0,0,500,400),'game','en','zh-Hans')
        wait_until(lambda:core.ocr_runs==1)
        assert p.request_retranslation()
        wait_until(lambda:core.ocr_runs==2 and not p.get_stats()['refresh_pending'])
        assert engine.calls==[]
    finally:cleanup(p,engine,core)


def test_ocr_refresh_clears_exact_image_cache_preserves_rois_and_target():
    core=object.__new__(OcrCore)
    core._lock=threading.RLock();core._frames=FrameCache();core.mode='auto'
    core._capture_regions=((0,0,16,12),);core._capture_language='en';core._source_reference=None
    core._style_matcher=None;core.min_confidence=55;core.cuda_status='disabled'
    resets=[];core.native=SimpleNamespace(reset=lambda:resets.append(1),target=(123,456))
    calls=[]
    def recognize(*args):
        calls.append(1);return {'lines':[],'engine':'test','ocr_ms':1}
    core._recognize_image_uncached=recognize
    with Image.new('RGB',(16,12)) as image:
        assert not core.recognize_image(image)['frame_cache_hit']
        assert core.recognize_image(image)['frame_cache_hit']
        core.request_refresh()
        assert not core.recognize_image(image)['frame_cache_hit']
    assert len(calls)==2 and resets==[1]
    assert core._capture_regions==((0,0,16,12),) and core.native.target==(123,456)


def test_vision_refresh_cancels_old_generation_and_rejects_old_completion(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);old_generation=wrapper._generation
    assert wrapper.recognition_pending
    wrapper.request_refresh()
    assert first['cancelled']() and wrapper._generation>old_generation
    assert not wrapper._cache and not wrapper._raw_cache and not wrapper._published
    capture(wrapper);clock.advance(.5);capture(wrapper)
    assert len(recognizer.calls)==1  # Old task still occupies the sole worker.
    first['gate'].set();wait_until(lambda:wrapper._future.done())
    capture(wrapper);wait_until(lambda:len(recognizer.calls)==2)
    assert not wrapper._cache
    second=recognizer.calls[1]
    assert not second['cancelled']()
    result=finish(wrapper,second)
    assert result['changed'] and result['lines'] and not wrapper.recognition_pending
    assert recognizer.peak==1 and len(core.local_calls)==2


def test_vision_refresh_does_not_reuse_successful_transcript(rig):
    wrapper,core,recognizer,clock=rig
    first=launch(rig);finish(wrapper,first)
    assert wrapper._cache
    wrapper.request_refresh();capture(wrapper);clock.advance(.5);capture(wrapper)
    wait_until(lambda:len(recognizer.calls)==2)
    finish(wrapper,recognizer.calls[1])
    assert len(core.local_calls)==2


def test_explicit_epoch_cannot_join_old_inflight_and_history_is_retained(factory):
    gates=[threading.Event(),threading.Event()];calls=[];lock=threading.Lock()
    def handler(_):
        with lock:i=len(calls);calls.append(i)
        assert gates[i].wait(3)
        return sse_response('old' if i==0 else 'new')
    engine=factory(handler,max_concurrency=2,context_agent_enabled=False)
    old_epoch=engine.advance_request_epoch()
    with ThreadPoolExecutor(max_workers=2) as pool:
        old=pool.submit(tr,engine,request_epoch=old_epoch)
        wait_until(lambda:len(calls)==1)
        fresh_epoch=engine.advance_request_epoch()
        fresh=pool.submit(tr,engine,request_epoch=fresh_epoch)
        try:
            wait_until(lambda:len(calls)==2)
        finally:
            for gate in gates:gate.set()
        assert {old.result(),fresh.result()}=={'old','new'}
    assert engine.get_stats()['api_calls']==2
    assert engine.get_profile('test-game')['progress']['completed']==2
    assert engine.get_context_status('test-game','en','zh-Hans')['records']==2


def test_refresh_epoch_obeys_shared_request_budget(factory):
    engine=factory(max_requests=1,unlimited_requests=False)
    tr(engine,request_epoch=engine.advance_request_epoch())
    with pytest.raises(BudgetExceeded):tr(engine,request_epoch=engine.advance_request_epoch())
    assert engine.get_stats()['api_calls']==1


@pytest.mark.parametrize('epoch',[-1,True,'new',1.5])
def test_invalid_request_epoch_rejected_before_network(factory,epoch):
    engine=factory()
    with pytest.raises(TranslationError):tr(engine,request_epoch=epoch)
    assert engine.get_stats()['api_calls']==0
