# SPDX-License-Identifier: MIT
"""Real worker races with fake capture/network; no GUI, credentials or API calls."""
import threading
import time

import pytest

from nkc_galgame_translator.pipeline import Pipeline


def line(text, index=0, **changes):
    return {"text": text, "x": 20, "y": 20 + index * 80, "w": 240, "h": 24,
            "bg": [0, 0, 0], "fg": [255, 255, 255], **changes}


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    assert predicate(), "timed out waiting for worker state"


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = []

    def __call__(self, event):
        with self.lock:
            self.items.append(event)

    def snapshot(self):
        with self.lock:
            return list(self.items)


class FakeCore:
    def __init__(self, lines):
        self.lock = threading.Lock()
        self.lines = lines
        self.dirty = True
        self.resets = self.hides = self.captures = self.ocr_runs = 0
        self.capture_entered = threading.Event()
        self.capture_release = threading.Event()
        self.capture_release.set()
        self.fail = None

    def set_scene(self, lines):
        with self.lock:
            self.lines = lines
            self.dirty = True

    def reset(self):
        with self.lock:
            self.resets += 1
            self.dirty = True

    def hide_overlay(self):
        with self.lock:
            self.hides += 1

    def capture_ocr(self, *region, language):
        self.capture_entered.set()
        assert self.capture_release.wait(4)
        with self.lock:
            self.captures += 1
            if self.fail:
                raise self.fail
            changed, self.dirty = self.dirty, False
            # The real capture core hashes every poll and only performs OCR
            # for changed pixels. Count recognition separately from polling.
            self.ocr_runs += int(changed)
            return {"changed": changed, "lines": list(self.lines), "capture_ms": .1, "ocr_ms": .2}


def test_pending_capture_does_not_publish_or_stop_pipeline():
    core,engine,events=FakeCore([line('Welcome aboard')]),FakeEngine(),Recorder()
    original=core.capture_ocr
    attempts=[]
    def pending_then_ready(*args,**kwargs):
        attempts.append(1)
        if len(attempts)<=3:
            return {'changed':True,'pending':True,'lines':[line('Stale frame')],'capture_ms':0,'ocr_ms':0}
        return original(*args,**kwargs)
    core.capture_ocr=pending_then_ready
    pipeline=Pipeline(core,engine,events,interval=.005,settle=0)
    try:
        pipeline.start(lambda:(0,0,800,600),'game','en','zh-Hans')
        wait_until(lambda:bool(engine.calls))
        assert engine.calls==['Welcome aboard'] and not pipeline.stop_event.is_set()
        assert not any(event[0]=='error' for event in events.snapshot())
    finally:
        pipeline.stop();pipeline.join(3);pipeline.pool.shutdown(wait=True,cancel_futures=True)


class FakeEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []
        self.scopes = []
        self.gates = {}
        self.active = self.peak = 0

    def block(self, source):
        gate = threading.Event()
        self.gates[source] = gate
        return gate

    def release_all(self):
        for gate in self.gates.values():
            gate.set()

    def translate(self, game, source, target, text, chunk, context):
        with self.lock:
            self.calls.append(text)
            self.scopes.append((game, source, target, text, context))
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            chunk("\u90e8\u5206 " + text)
            if text in self.gates:
                assert self.gates[text].wait(4)
            chunk("\u5b8c\u6574 " + text)
            return "\u8bd1\u6587 " + text
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def make_pipeline():
    items = []
    def make(lines=None, *, region=None, **kwargs):
        core = FakeCore(lines if lines is not None else [line("Hello")])
        engine, events = FakeEngine(), Recorder()
        options = dict(interval=.005, settle=0, merge_lines=False, translation_workers=2)
        options.update(kwargs)
        pipeline = Pipeline(core, engine, events, **options)
        region_state = [region or (0, 0, 800, 600)]
        items.append((pipeline, core, engine))
        return pipeline, core, engine, events, region_state
    yield make
    for pipeline, core, engine in items:
        core.capture_release.set()
        engine.release_all()
        pipeline.stop()
        pipeline.join(4)
        pipeline.pool.shutdown(wait=True, cancel_futures=True)


def start(pipeline, region):
    pipeline.start(lambda: region[0], "game", "en", "zh-Hans", "test context")


def updates(events):
    return [e for e in events.snapshot() if e[0] == 'translation']


def finals(events):
    return [e for e in updates(events) if e[2][3]]


def objects(events):
    found = [e[2] for e in events.snapshot() if e[0] == 'objects']
    return found[-1] if found else []


def object_for(events, source):
    return next((o for o in objects(events) if o['line']['text'] == source), None)


@pytest.mark.parametrize('label,brackets,expected', [
    (True,True,'[\u82f1\u8bed\uff1a\u8bd1\u6587 Alpha]'), (True,False,'\u82f1\u8bed\uff1a\u8bd1\u6587 Alpha'),
    (False,True,'[\u8bd1\u6587 Alpha]'), (False,False,'\u8bd1\u6587 Alpha'),
])
def test_pipeline_formats_only_presentation_and_keeps_source_scope(make_pipeline,label,brackets,expected):
    p,core,engine,events,region=make_pipeline([line('Alpha')],show_source_label=label,
                                            show_translation_brackets=brackets)
    start(p,region)
    wait_until(lambda: len(finals(events))==1)
    assert finals(events)[0][2][1]['text']==expected
    assert engine.calls==['Alpha']
    assert engine.scopes==[('game','en','zh-Hans','Alpha','test context')]
    # Position updates reuse stored raw output and the same formatting, without translation.
    core.set_scene([line('Alpha',x=55)])
    wait_until(lambda: (object_for(events,'Alpha') or {}).get('line',{}).get('x')==55)
    assert engine.calls==['Alpha']


def latest_final_text(events, source):
    found=[event[2][1]['text'] for event in finals(events) if event[2][2]==source]
    return found[-1] if found else None


def coherent_line(text,index=0):
    # Mixed-only labels apply to a contiguous text block, not the whole frame.
    return line(text,index,y=20+index*32)


def test_mixed_only_reformats_visible_results_without_new_requests_or_revisions(make_pipeline):
    english,japanese='Alpha','\u30b2\u30fc\u30e0\u3092\u958b\u59cb'
    p,core,engine,events,region=make_pipeline([line(english)],source_label_mixed_only=True)
    start(p,region)
    wait_until(lambda:latest_final_text(events,english)=='[\u8bd1\u6587 Alpha]')
    original=object_for(events,english);generation=p.generation
    core.set_scene([coherent_line(english),coherent_line(japanese,1)])
    wait_until(lambda:latest_final_text(events,english)=='[\u82f1\u8bed\uff1a\u8bd1\u6587 Alpha]'
               and latest_final_text(events,japanese)=='[\u65e5\u8bed\uff1a\u8bd1\u6587 '+japanese+']')
    assert sorted(engine.calls)==sorted([english,japanese])
    core.set_scene([line(english)])
    wait_until(lambda:latest_final_text(events,english)=='[\u8bd1\u6587 Alpha]')
    current=object_for(events,english)
    assert (current['track_id'],current['revision'])==(original['track_id'],original['revision'])
    assert p.generation==generation
    assert sorted(engine.calls)==sorted([english,japanese])
    # A retained missing object's reappearance restores mixed formatting, not an API task.
    core.set_scene([coherent_line(english),coherent_line(japanese,1)])
    wait_until(lambda:latest_final_text(events,english)=='[\u82f1\u8bed\uff1a\u8bd1\u6587 Alpha]')
    assert sorted(engine.calls)==sorted([english,japanese])


@pytest.mark.parametrize('show,brackets', [(False,True),(False,False),(True,False)])
def test_mixed_only_keeps_master_and_bracket_switches_independent(make_pipeline,show,brackets):
    p,core,engine,events,region=make_pipeline([coherent_line('Alpha'),coherent_line('\u30b2\u30fc\u30e0',1)],
        source_label_mixed_only=True,show_source_label=show,show_translation_brackets=brackets)
    start(p,region)
    expected=('\u82f1\u8bed\uff1a' if show else '')+'\u8bd1\u6587 Alpha'
    if brackets:expected='['+expected+']'
    wait_until(lambda:latest_final_text(events,'Alpha')==expected)
    core.set_scene([line('Alpha')])
    single='[\u8bd1\u6587 Alpha]' if brackets else '\u8bd1\u6587 Alpha'
    wait_until(lambda:latest_final_text(events,'Alpha')==single)
    assert engine.calls.count('Alpha')==1


def test_mixed_only_ignores_target_language_and_regional_source_aliases(make_pipeline,monkeypatch):
    import nkc_galgame_translator.pipeline as module
    codes={'US':'en-US','GB':'en-GB','Chinese':'zh-CN','Japanese':'ja-JP'}
    monkeypatch.setattr(module,'detect_source_language',lambda text,selected:codes[text])
    p,core,engine,events,region=make_pipeline([coherent_line('US'),coherent_line('GB',1),coherent_line('Chinese',2)],
                                            source_label_mixed_only=True)
    start(p,region)
    wait_until(lambda:len(finals(events))==3)
    assert all('\uff1a' not in e[2][1]['text'] for e in finals(events))
    core.set_scene([coherent_line('US'),coherent_line('GB',1),coherent_line('Chinese',2),coherent_line('Japanese',3)])
    wait_until(lambda:latest_final_text(events,'US')=='[\u82f1\u8bed\uff1a\u8bd1\u6587 US]')
    wait_until(lambda:engine.calls.count('Japanese')==1)
    assert all(engine.calls.count(text)==1 for text in codes)


def test_mixed_only_reformats_inflight_stream_without_closing_brackets_or_restart(make_pipeline):
    p,core,engine,events,region=make_pipeline([coherent_line('Alpha'),coherent_line('\u30b2\u30fc\u30e0',1)],
                                            source_label_mixed_only=True)
    gate=engine.block('Alpha')
    start(p,region)
    def latest_alpha():
        rows=[event[2] for event in updates(events) if event[2][2]=='Alpha']
        return rows[-1] if rows else None
    wait_until(lambda:latest_alpha() is not None and latest_alpha()[1]['text']=='[\u82f1\u8bed\uff1a\u90e8\u5206 Alpha')
    first=latest_alpha()
    core.set_scene([line('Alpha')])
    wait_until(lambda:latest_alpha()[1]['text']=='[\u90e8\u5206 Alpha')
    latest=latest_alpha()
    assert latest[3] is False
    assert (latest[0],latest[1]['_revision'])==(first[0],first[1]['_revision'])
    assert engine.calls.count('Alpha')==1
    gate.set()
    wait_until(lambda:latest_final_text(events,'Alpha')=='[\u8bd1\u6587 Alpha]')
    assert engine.calls.count('Alpha')==1


@pytest.mark.parametrize('value', ['false',0,1,None])
def test_mixed_only_pipeline_boolean_validation(value):
    with pytest.raises(ValueError):Pipeline(None,None,None,source_label_mixed_only=value)


def test_one_text_changes_without_global_clear_or_retranslating_other(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Alpha'), line('Beta', 1)])
    start(p, region)
    wait_until(lambda: len(finals(events)) == 2)
    alpha, beta = object_for(events, 'Alpha'), object_for(events, 'Beta')
    session = p.generation
    clears = len([e for e in events.snapshot() if e[0] == 'clear'])
    core.set_scene([line('Alpha new'), line('Beta', 1)])
    wait_until(lambda: len(finals(events)) == 3)
    updated = object_for(events, 'Alpha new')
    assert updated['track_id'] == alpha['track_id']
    assert updated['revision'] > alpha['revision']
    assert object_for(events, 'Beta')['track_id'] == beta['track_id']
    assert engine.calls.count('Beta') == 1
    assert p.generation == session
    assert len([e for e in events.snapshot() if e[0] == 'clear']) == clears
    assert core.hides == 0


def test_moving_objects_keep_translation_and_revision(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Moving')])
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    first = object_for(events, 'Moving')
    core.set_scene([line('Moving', x=45, y=30, bg=[15, 15, 15])])
    wait_until(lambda: object_for(events, 'Moving')['line']['x'] == 45)
    moved = object_for(events, 'Moving')
    assert (moved['track_id'], moved['revision']) == (first['track_id'], first['revision'])
    time.sleep(.04)
    assert engine.calls == ['Moving']
    assert len(finals(events)) == 1  # App moves the existing rendered region.


def test_old_revision_inflight_chunks_and_completion_are_suppressed(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Old')])
    old_gate = engine.block('Old')
    start(p, region)
    wait_until(lambda: engine.calls == ['Old'])
    old = object_for(events, 'Old')
    core.set_scene([line('New')])
    wait_until(lambda: object_for(events, 'New') is not None)
    current = object_for(events, 'New')
    assert old['track_id'] == current['track_id']
    assert old['revision'] != current['revision']
    checkpoint = len(events.snapshot())
    old_gate.set()
    wait_until(lambda: any(e[2][2] == 'New' for e in finals(events)))
    assert not any(e[2][2] == 'Old' for e in finals(events))
    assert all(e[2][1]['_revision'] != old['revision']
               for e in events.snapshot()[checkpoint:] if e[0] == 'translation')


def test_callbacks_use_current_geometry(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Move while streaming')])
    gate = engine.block('Move while streaming')
    start(p, region)
    wait_until(lambda: len(updates(events)) == 1)
    core.set_scene([line('Move while streaming', x=65, y=35)])
    wait_until(lambda: object_for(events, 'Move while streaming')['line']['x'] == 65)
    gate.set()
    wait_until(lambda: len(finals(events)) == 1)
    assert finals(events)[0][2][1]['x'] == 65
    assert finals(events)[0][2][1]['y'] == 35
    assert len(engine.calls) == 1


@pytest.mark.parametrize('offline', [False, True])
def test_fixed_source_rows_keep_raw_stream_and_cache_breaks(make_pipeline, offline):
    source = [line('The airlock opens at a touch...and'), line('cycles you smoothly in.', y=50)]
    raw = '\u6c14\u95f8\u8f7b\u89e6\u5373\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002'
    original = '\n'.join(row['text'] for row in source)
    p, core, engine, events, region = make_pipeline(source, merge_lines=True)
    engine.offline_only = offline
    calls = []
    def translate(game, source_language, target, text, chunk, context):
        calls.append(text)
        for size in range(len(raw) + 1):
            chunk(raw[:size])
        return raw
    engine.translate = translate
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    assert calls == [original]
    rendered = finals(events)[0][2][1]
    assert rendered['text'] == '[\u82f1\u8bed\uff1a\u6c14\u95f8\u8f7b\u89e6\u5373\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002]'
    assert rendered['_fixed_layout'] is True
    assert len(rendered['_source_rows']) == 2
    assert finals(events)[0][2][2] == original
    assert next(iter(p._states.values())).output == (raw, True)
    previous = ''
    for event in updates(events):
        current = event[2][1]['text']
        assert current.startswith(previous)
        previous = current
    if offline:
        assert len(updates(events)) == 1


def test_changed_source_row_evidence_reuses_translation_without_removing_breaks(make_pipeline):
    rows = [line('The airlock opens at a touch...and'), line('cycles you smoothly in.', y=50)]
    original = '\n'.join(row['text'] for row in rows)
    p, core, engine, events, region = make_pipeline(rows, merge_lines=True)
    engine.offline_only = True
    calls = []
    def translate(game, source, target, text, chunk, context):
        calls.append(text)
        return '\u6c14\u95f8\u6253\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002'
    engine.translate = translate
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    first = object_for(events, original)
    assert finals(events)[-1][2][1]['text'] == '[\u82f1\u8bed\uff1a\u6c14\u95f8\u6253\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002]'
    assert len(finals(events)[-1][2][1]['_source_rows']) == 2
    core.set_scene([line(original, h=54)])
    wait_until(lambda: len(finals(events)) == 2)
    current = object_for(events, original)
    assert (current['track_id'], current['revision']) == (first['track_id'], first['revision'])
    assert finals(events)[-1][2][1]['text'] == '[\u82f1\u8bed\uff1a\u6c14\u95f8\u6253\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002]'
    assert finals(events)[-1][2][1]['_source_line_count'] == 2
    core.set_scene(rows)
    wait_until(lambda: len(finals(events)) == 3)
    assert finals(events)[-1][2][1]['text'] == '[\u82f1\u8bed\uff1a\u6c14\u95f8\u6253\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002]'
    assert calls == [original]


def test_numeric_columns_remain_geometry_barriers_without_translation(make_pipeline):
    values = [line('forged credits', y=20, w=220), line('488', x=400, y=20, w=50),
              line('hybrid grain', y=50, w=230), line('25', x=415, y=50, w=35),
              line('antibiotics', y=80, w=220), line('86', x=415, y=80, w=35)]
    p, core, engine, events, region = make_pipeline(values, merge_lines=True)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 3)
    assert set(engine.calls) == {'forged credits', 'hybrid grain', 'antibiotics'}
    assert len(objects(events)) == 6
    assert p.get_stats()['preserved_source'] == 3
    for event in finals(events):
        assert event[2][1]['w'] <= 230 and event[2][1]['h'] == 24
        assert event[2][1]['_fixed_layout']


def test_missing_and_reappearing_object_reuses_completed_result(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Persistent')], max_missing=2)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    first = object_for(events, 'Persistent')
    core.set_scene([])
    wait_until(lambda: objects(events) == [])
    core.set_scene([line('Persistent', x=22)])
    wait_until(lambda: len(finals(events)) == 2)
    assert object_for(events, 'Persistent')['track_id'] == first['track_id']
    assert engine.calls == ['Persistent']


def test_result_finishing_while_invisible_reappears_without_new_request(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Hidden')], max_missing=2)
    gate = engine.block('Hidden')
    start(p, region)
    wait_until(lambda: len(updates(events)) == 1)
    core.set_scene([])
    wait_until(lambda: objects(events) == [])
    gate.set()
    wait_until(lambda: engine.active == 0)
    assert finals(events) == []
    core.set_scene([line('Hidden')])
    wait_until(lambda: len(finals(events)) == 1)
    assert engine.calls == ['Hidden']


@pytest.mark.parametrize('workers', [1,4,8,16])
def test_configured_translation_jobs_run_concurrently_with_fixed_bound(make_pipeline,workers):
    total=workers+2
    p, core, engine, events, region = make_pipeline([line(f'Item{i}', i) for i in range(total)], translation_workers=workers)
    gates = [engine.block(f'Item{i}') for i in range(workers)]
    start(p, region)
    wait_until(lambda: engine.active == workers)
    assert p.get_stats()['inflight'] == workers
    assert p.get_stats()['pending'] == 2
    time.sleep(.04)
    assert len(engine.calls) == workers
    for gate in gates:
        gate.set()
    wait_until(lambda: len(finals(events)) == total)
    assert engine.peak == workers


def test_old_work_occupies_slots_without_unbounded_executor_submission(make_pipeline):
    p, core, engine, events, region = make_pipeline([line(f'Old{i}', i) for i in range(32)])
    first, second = engine.block('Old0'), engine.block('Old1')
    submitted = []
    original_submit = p.pool.submit
    def submit(*args, **kwargs):
        submitted.append(args)
        return original_submit(*args, **kwargs)
    p.pool.submit = submit
    start(p, region)
    wait_until(lambda: len(engine.calls) == 2)
    for i in range(5):
        core.set_scene([line(f'Latest{i}')])
        wait_until(lambda: object_for(events, f'Latest{i}') is not None)
    assert len(submitted) == 2
    assert p.get_stats()['inflight'] == 2
    first.set(); second.set()
    wait_until(lambda: 'Latest4' in engine.calls)
    assert set(engine.calls) == {'Old0', 'Old1', 'Latest4'}
    assert engine.peak <= 2


def test_latest_observation_queue_drops_old_frames_during_slow_tracking(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Initial')])
    entered, release = threading.Event(), threading.Event()
    update = p.tracker.update
    def slow_update(lines, origin, **kwargs):
        entered.set()
        assert release.wait(10)
        return update(lines, origin=origin, **kwargs)
    p.tracker.update = slow_update
    start(p, region)
    assert entered.wait(2)
    try:
        for index in range(8):
            source = f'Newest{index}'
            core.set_scene([line(source)])
            # A timing event is emitted after the corresponding observation is
            # queued. Acknowledge every scene before replacing the fake frame.
            wait_until(lambda: any(e[0] == 'timing' and
                e[2]['lines'][0]['text'] == source for e in events.snapshot()))
        with p._state_lock:
            assert p.get_stats()['observation_queue'] == 1
            # Optional unchanged-frame confirmations are observations too;
            # exactly one was consumed and exactly one remains queued.
            assert p.get_stats()['queue_drops'] == p._observation_serial - 2
            assert p.get_stats()['queue_drops'] >= 7
    finally:
        release.set()
    wait_until(lambda: 'Newest7' in engine.calls)
    assert engine.calls == ['Newest7']
    assert not any(o['line']['text'] == 'Initial' for e in events.snapshot() if e[0] == 'objects' for o in e[2])


def test_settle_is_per_object_while_other_object_changes(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('A'), line('Stable', 1)], settle=.075)
    start(p, region)
    wait_until(lambda: object_for(events, 'A') is not None)
    for text in ['Ab', 'Abc', 'Abcd', 'Abcde']:
        time.sleep(.025)
        core.set_scene([line(text), line('Stable', 1)])
    wait_until(lambda: 'Stable' in engine.calls)
    assert not any(text in engine.calls for text in ['A', 'Ab', 'Abc', 'Abcd'])
    wait_until(lambda: 'Abcde' in engine.calls)
    assert engine.calls.count('Stable') == 1


def test_focus_loss_clears_and_unchanged_pixels_resume(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    generation = p.generation
    region[0] = None
    wait_until(lambda: p.generation != generation)
    assert any(e[0] == 'clear' for e in events.snapshot())
    region[0] = (0, 0, 800, 600)
    wait_until(lambda: len(finals(events)) == 2)
    assert core.resets >= 2 and core.hides >= 1


def test_stop_during_capture_emits_nothing_after_stop(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    core.capture_release.clear()
    start(p, region)
    assert core.capture_entered.wait(2)
    p.stop()
    checkpoint = len(events.snapshot())
    core.capture_release.set()
    assert p.join(2)
    assert not p.alive and engine.calls == []
    assert events.snapshot()[checkpoint:] == []


def test_stop_during_tracking_waits_for_both_workers(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    entered, release = threading.Event(), threading.Event()
    update = p.tracker.update
    def blocked(lines, origin, **kwargs):
        entered.set()
        assert release.wait(3)
        return update(lines, origin=origin, **kwargs)
    p.tracker.update = blocked
    start(p, region)
    assert entered.wait(2)
    p.stop()
    checkpoint = len(events.snapshot())
    assert p.alive and not p.join(.01)
    release.set()
    assert p.join(2)
    assert engine.calls == []
    assert events.snapshot()[checkpoint:] == []


def test_stop_during_api_stream_suppresses_later_events(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    gate = engine.block('Hello')
    start(p, region)
    wait_until(lambda: len(updates(events)) == 1)
    p.stop()
    assert p.join(2)
    checkpoint = len(events.snapshot())
    gate.set()
    wait_until(lambda: engine.active == 0)
    assert events.snapshot()[checkpoint:] == []


def test_error_events_are_object_revision_tagged(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    def fail(*args):
        raise RuntimeError('private provider body ' + 'sk-' + 'confidential-' * 5)
    engine.translate = fail
    start(p, region)
    wait_until(lambda: any(e[0] == 'line_error' for e in events.snapshot()))
    track = object_for(events, 'Hello')
    error = next(e for e in events.snapshot() if e[0] == 'line_error')
    assert error[2] == (track['track_id'], track['revision'], '\u8be5\u6587\u5b57\u6846\u7ffb\u8bd1\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u914d\u7f6e\u6216\u7a0d\u540e\u91cd\u8bd5\u3002')
    core.set_scene([line('Hello', x=22)])
    time.sleep(.04)
    assert len([e for e in events.snapshot() if e[0] == 'line_error']) == 1


def test_error_from_superseded_revision_never_reaches_ui(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    entered, release = threading.Event(), threading.Event()
    def translate(game, source, target, text, chunk, context):
        if text == 'Hello':
            entered.set(); assert release.wait(3); raise RuntimeError('old failure')
        return 'new result'
    engine.translate = translate
    start(p, region)
    assert entered.wait(2)
    core.set_scene([line('Changed')])
    wait_until(lambda: object_for(events, 'Changed') is not None)
    release.set()
    wait_until(lambda: len(finals(events)) == 1)
    assert not any(e[0] == 'line_error' for e in events.snapshot())


def test_nonlinguistic_lines_keep_barriers_and_object_cap_applies(make_pipeline):
    source_lines = [line(''), line('  '), line('12345', x=600, w=80), line('!@#$', x=600, y=60, w=80)]
    source_lines.extend(line(f'Word{i}', i) for i in range(50))
    p, core, engine, events, region = make_pipeline(source_lines)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 30)
    assert len(engine.calls) == 30
    assert p.get_stats()['objects'] == 32
    assert p.get_stats()['preserved_source'] == 2


def test_capture_error_stops_both_threads_without_translation(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    core.fail = RuntimeError('capture failed')
    start(p, region)
    wait_until(lambda: p.stop_event.is_set())
    assert p.join(2)
    assert engine.calls == [] and core.hides > 0
    assert [e[2] for e in events.snapshot() if e[0] == 'error'] == ['\u6355\u83b7\u6216\u8bc6\u522b\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u6e38\u620f\u7a97\u53e3\u548c\u533a\u57df\u3002']


def test_coordinator_error_stops_without_translation(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    def fail(*args, **kwargs):
        raise RuntimeError('tracking failed')
    p.tracker.update = fail
    start(p, region)
    wait_until(lambda: p.stop_event.is_set())
    assert p.join(2)
    assert engine.calls == []
    assert [e[2] for e in events.snapshot() if e[0] == 'error'] == ['\u6355\u83b7\u6216\u8bc6\u522b\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u6e38\u620f\u7a97\u53e3\u548c\u533a\u57df\u3002']


def test_origin_move_preserves_track_identity_and_translation(make_pipeline):
    p, core, engine, events, region = make_pipeline()
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    track = object_for(events, 'Hello')
    core.set_scene([line('Hello', x=420, y=320)])
    region[0] = (400, 300, 800, 600)
    wait_until(lambda: object_for(events, 'Hello')['line']['x'] == 420)
    assert object_for(events, 'Hello')['track_id'] == track['track_id']
    assert object_for(events, 'Hello')['revision'] == track['revision']
    assert engine.calls == ['Hello']


def test_stream_events_have_revision_and_final_flags_after_object_announcement(make_pipeline):
    original = line('Streaming')
    p, core, engine, events, region = make_pipeline([original])
    gate = engine.block('Streaming')
    start(p, region)
    wait_until(lambda: len(updates(events)) == 1)
    track = object_for(events, 'Streaming')
    payload = updates(events)[0][2]
    assert payload == (track['track_id'], {**track['line'], 'text': '[\u82f1\u8bed\uff1a\u90e8\u5206 Streaming', 'final': False,
                                         '_revision': track['revision']}, 'Streaming', False)
    snapshot = events.snapshot()
    assert next(i for i, e in enumerate(snapshot) if e[0] == 'objects') < next(i for i, e in enumerate(snapshot) if e[0] == 'translation')
    gate.set()
    wait_until(lambda: len(finals(events)) == 1)
    assert [e[2][1]['final'] for e in updates(events)] == [False, False, True]


def test_newlines_and_empty_chunks_are_preserved(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('First\nSecond')])
    def translate(game, source, target, text, chunk, context):
        assert text == 'First\nSecond'
        chunk(''); chunk('\u7b2c\u4e00\u884c\n\u7b2c'); chunk('\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c')
        return '\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c'
    engine.translate = translate
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    assert [e[2][1]['text'] for e in updates(events)] == ['', '[\u82f1\u8bed\uff1a\u7b2c\u4e00\u884c\n\u7b2c', '[\u82f1\u8bed\uff1a\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c', '[\u82f1\u8bed\uff1a\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c]']
    assert [e[2][1]['final'] for e in updates(events)] == [False, False, False, True]


def test_adjacent_dialogue_merges_before_object_tracking(make_pipeline):
    first, second = line('First dialogue'), line('Second dialogue', y=50)
    p, core, engine, events, region = make_pipeline([first, second], merge_lines=True)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    assert engine.calls == ['First dialogue\nSecond dialogue']
    assert len(objects(events)) == 1
    assert finals(events)[0][2][1]['h'] == 54


def test_unchanged_frame_confirms_twice_without_more_ocr_or_api(make_pipeline):
    p, core, engine, events, region = make_pipeline(interval=.03)
    start(p, region)
    wait_until(lambda: core.captures >= 8)
    snapshots = [e[2] for e in events.snapshot() if e[0] == 'objects']
    assert len(snapshots) == 3  # Original observation plus two confirmations.
    assert snapshots[0] == snapshots[1] == snapshots[2]
    assert len([e for e in events.snapshot() if e[0] == 'timing']) == 1
    assert core.ocr_runs == 1 and engine.calls == ['Hello']
    assert len(finals(events)) == 1
    count = core.captures
    wait_until(lambda: core.captures >= count + 4)
    assert len([e for e in events.snapshot() if e[0] == 'objects']) == 3
    assert core.ocr_runs == 1 and engine.calls == ['Hello']


@pytest.mark.parametrize('keep_other_visible', [False,True])
def test_unchanged_confirmation_does_not_consume_missing_tolerance(make_pipeline,keep_other_visible):
    scene = [line('Persistent'),line('Other',1)]
    p, core, engine, events, region = make_pipeline(scene,max_missing=2,interval=.02)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 2)
    identity = object_for(events,'Persistent')['track_id']
    remaining = [line('Other',1)] if keep_other_visible else []
    core.set_scene(remaining)
    wait_until(lambda: object_for(events,'Persistent') is None)
    baseline = core.captures
    wait_until(lambda: core.captures >= baseline + 6)
    core.set_scene(scene)
    wait_until(lambda: object_for(events,'Persistent') is not None)
    wait_until(lambda: any(e[2][0] == identity and e[2][2] == 'Persistent'
                          for e in finals(events)[2:]))
    assert object_for(events,'Persistent')['track_id'] == identity
    assert engine.calls.count('Persistent') == 1
    assert engine.calls.count('Other') == 1


def test_merged_dialogue_preserves_capture_origin_for_immediate_window_movement(make_pipeline):
    from nkc_galgame_translator.presentation import OverlayState
    p, core, engine, events, region = make_pipeline([
        line('First dialogue'),line('Second dialogue',y=50)],merge_lines=True,interval=.03)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    original = objects(events)[0]
    assert original['line']['_capture_origin'] == (0,0)
    state = OverlayState()
    state.apply_objects([original])
    state.apply_translation(original['track_id'],finals(events)[0][2][1])
    core.set_scene([line('First dialogue',x=24,y=17),
                    line('Second dialogue',x=24,y=47)])
    region[0] = (4,-3,800,600)
    wait_until(lambda: objects(events) and objects(events)[0]['line'].get('_capture_origin') == (4,-3))
    moved = objects(events)[0]
    assert (moved['track_id'],moved['revision']) == (original['track_id'],original['revision'])
    assert state.apply_objects([moved])
    shown = state.rendered[original['track_id']]
    assert (shown['x'],shown['y'],shown['_capture_origin']) == (24,17,(4,-3))
    assert engine.calls == ['First dialogue\nSecond dialogue']


def test_unchanged_frame_confirmations_allow_real_resize_to_reach_presentation(make_pipeline):
    from nkc_galgame_translator.presentation import OverlayState
    p, core, engine, events, region = make_pipeline([line('Resizing',h=40)],interval=.03)
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    identity = object_for(events,'Resizing')['track_id']
    state = OverlayState()
    state.apply_objects(objects(events))
    state.apply_translation(identity,finals(events)[0][2][1])
    checkpoint = len(events.snapshot())
    core.set_scene([line('Resizing',h=71)])
    wait_until(lambda: len([e for e in events.snapshot()[checkpoint:]
                           if e[0] == 'objects' and e[2][0]['line']['h'] == 71]) == 3)
    changes = [e[2] for e in events.snapshot()[checkpoint:]
               if e[0] == 'objects' and e[2][0]['line']['h'] == 71]
    for observed in changes[:2]:
        state.apply_objects(observed)
        assert state.rendered[identity]['h'] == 40
    state.apply_objects(changes[2])
    assert state.rendered[identity]['h'] == 71
    assert core.ocr_runs == 2 and engine.calls == ['Resizing']


def test_generation_namespaces_unique_and_pipeline_cannot_restart(make_pipeline):
    first, c1, e1, events1, region1 = make_pipeline()
    second, c2, e2, events2, region2 = make_pipeline()
    start(first, region1); start(second, region2)
    wait_until(lambda: finals(events1) and finals(events2))
    assert first.generation != second.generation
    with pytest.raises(RuntimeError, match='\u91cd\u590d\u542f\u52a8'):
        start(first, region1)
    first.stop(); first.join()
    with pytest.raises(RuntimeError, match='\u91cd\u590d\u542f\u52a8'):
        start(first, region1)


def test_mixed_english_japanese_boxes_route_and_label_independently(make_pipeline):
    english = 'Welcome to the Scarlet Mansion.'
    japanese = '\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002'
    p, core, engine, events, region = make_pipeline([line(english), line(japanese, 1)])
    p.start(lambda: region[0], 'game', 'ja', 'zh-Hans', 'test context')
    wait_until(lambda: len(finals(events)) == 2)
    assert {(row[1], row[3]) for row in engine.scopes} == {('en', english), ('ja', japanese)}
    displayed = {e[2][2]: e[2][1] for e in finals(events)}
    assert displayed[english]['text'] == f'[\u82f1\u8bed\uff1a\u8bd1\u6587 {english}]'
    assert displayed[japanese]['text'] == f'[\u65e5\u8bed\uff1a\u8bd1\u6587 {japanese}]'
    assert displayed[english]['source_lang'] == 'en'
    assert displayed[japanese]['source_lang'] == 'ja'
    assert object_for(events, english)['line']['text'] == english
    assert object_for(events, japanese)['line']['text'] == japanese


def test_offline_complete_result_emits_one_final_label_without_fake_stream_resize(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Welcome')])
    engine.offline_only = True
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    assert len(updates(events)) == 1
    assert finals(events)[0][2][1]['text'] == '[\u82f1\u8bed\uff1a\u8bd1\u6587 Welcome]'
    core.set_scene([])
    wait_until(lambda: objects(events) == [])
    core.set_scene([line('Welcome')])
    wait_until(lambda: len(finals(events)) == 2)
    assert len(updates(events)) == 2
    assert engine.calls == ['Welcome']


def test_adjacent_different_languages_do_not_merge(make_pipeline):
    p, core, engine, events, region = make_pipeline([
        line('Welcome'), line('\u3088\u3046\u3053\u305d', y=50)], merge_lines=True)
    p.start(lambda: region[0], 'game', 'ja', 'zh-Hans')
    wait_until(lambda: len(finals(events)) == 2)
    assert len(objects(events)) == 2
    assert set(engine.calls) == {'Welcome', '\u3088\u3046\u3053\u305d'}


def test_language_change_rejects_old_language_stream(make_pipeline):
    p, core, engine, events, region = make_pipeline([line('Welcome')])
    old_gate = engine.block('Welcome')
    p.start(lambda: region[0], 'game', 'ja', 'zh-Hans')
    wait_until(lambda: len(updates(events)) == 1)
    old = object_for(events, 'Welcome')
    core.set_scene([line('\u3088\u3046\u3053\u305d')])
    wait_until(lambda: object_for(events, '\u3088\u3046\u3053\u305d') is not None)
    current = object_for(events, '\u3088\u3046\u3053\u305d')
    assert current['track_id'] == old['track_id']
    assert current['revision'] > old['revision']
    old_gate.set()
    wait_until(lambda: len(finals(events)) == 1)
    assert finals(events)[0][2][1]['text'] == '[\u65e5\u8bed\uff1a\u8bd1\u6587 \u3088\u3046\u3053\u305d]'
    assert finals(events)[0][2][1]['source_lang'] == 'ja'


def test_display_labels_never_enter_real_sentence_cache_or_api_request(tmp_path):
    import json
    import sqlite3
    import httpx
    from nkc_galgame_translator.translation import TranslationEngine

    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        data = {'choices': [{'delta': {'content': '\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986'}, 'finish_reason': None}]}
        finish = {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}
        return httpx.Response(200, text='data: ' + json.dumps(data, ensure_ascii=False) +
            '\n\ndata: ' + json.dumps(finish) + '\n\ndata: [DONE]\n\n',
            headers={'Content-Type':'text/event-stream'})
    database = tmp_path/'codebook.sqlite3'
    english, japanese = 'Welcome to the Scarlet Mansion.', '\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002'
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        engine = TranslationEngine({'api_key':'test-token','auto_promote_short_terms':False}, database, client=client)
        core, events = FakeCore([line(english), line(japanese, 1)]), Recorder()
        p = Pipeline(core, engine, events, interval=.005, settle=0, merge_lines=False)
        try:
            p.start(lambda: (0,0,800,600), 'game', 'ja', 'zh-Hans', 'context')
            wait_until(lambda: len(finals(events)) == 2)
            assert {e[2][1]['text'] for e in finals(events)} == {'[\u82f1\u8bed\uff1a\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986]', '[\u65e5\u8bed\uff1a\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986]'}
            assert engine.translate('game','en','zh-Hans',english,context='context') == '\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986'
            assert len(requests) == 3  # A new invocation uses AI; history is reference only.
            assert '[\u82f1\u8bed\uff1a' not in json.dumps(requests,ensure_ascii=False)
            assert '[\u65e5\u8bed\uff1a' not in json.dumps(requests,ensure_ascii=False)
            with sqlite3.connect(database) as connection:
                assert set(connection.execute('SELECT src_lang,source,target FROM translations')) == {
                    ('en',english,'\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986'), ('ja',japanese,'\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986')}
        finally:
            p.stop(); p.join(3); p.pool.shutdown(wait=True, cancel_futures=True); engine.close()


def test_obvious_ocr_error_preserves_pixels_and_other_boxes_continue(make_pipeline):
    bad = 'Neu or Id gane?'
    p, core, engine, events, region = make_pipeline([line(bad), line('Welcome aboard',1)])
    start(p,region)
    wait_until(lambda: len(finals(events))==1 and len(objects(events))==2)
    assert engine.calls==['Welcome aboard']
    assert object_for(events,bad)['line']['_preserve_source'] is True
    assert p.get_stats()['preserved_source']==1
    assert p.get_stats()['pending']==0
    assert all(update[2][2]!=bad for update in updates(events))


def test_hud_noise_is_ignored_while_readable_menu_words_translate(make_pipeline):
    skipped = ['Siiius', 'SYS f ebn', 'HP 300', 'F1']
    accepted = ['STATUS', 'CHART', 'QUERY', 'SCAN', 'COCKPIT', '(Gun laser)']
    p, core, engine, events, region = make_pipeline([
        line(text, index) for index, text in enumerate(skipped + accepted)])
    start(p, region)
    wait_until(lambda: len(finals(events)) == len(accepted))
    assert set(engine.calls) == set(accepted)
    assert p.get_stats()['preserved_source'] == len(skipped)
    assert all(object_for(events, text)['line']['_preserve_source'] for text in skipped)


def test_identical_translation_keeps_pixels_without_label_or_late_stream(make_pipeline):
    from nkc_galgame_translator.presentation import OverlayState
    p, core, engine, events, region = make_pipeline([line('Sirius')])
    def unchanged(game, source, target, text, chunk, context):
        chunk(text)
        return text
    engine.translate = unchanged
    start(p, region)
    wait_until(lambda: len(finals(events)) == 1)
    assert all(event[2][1]['text'] == '' for event in updates(events))
    last = finals(events)[0]
    assert last[2][1]['_translation_unchanged'] is True
    state = OverlayState()
    state.apply_objects(objects(events))
    for event in updates(events):
        state.apply_translation(event[2][0], event[2][1])
    assert state.rendered == {}
    assert not state.apply_translation(last[2][0], {
        **last[2][1], 'text': '\u8fdf\u5230\u7684\u7247\u6bb5', 'final': False, '_translation_unchanged': False})
    assert state.rendered == {}


def test_rejected_ocr_barrier_splits_paragraph_without_hiding_its_row(make_pipeline):
    from nkc_galgame_translator.presentation import OverlayState
    p,core,engine,events,region=make_pipeline([
        line('Welcome to the station',w=360),
        line('Neu or Id gane?',y=50,w=360),
        line('Your mission begins here',y=80,w=360)],merge_lines=True)
    start(p,region)
    wait_until(lambda:len(finals(events))==2)
    assert set(engine.calls)=={'Welcome to the station','Your mission begins here'}
    state=OverlayState();state.apply_objects(objects(events))
    for event in finals(events):state.apply_translation(event[2][0],event[2][1])
    assert len(state.rendered)==2
    assert all(r['y']+r['h']<=50 or r['y']>=74 for r in state.rendered.values())


def test_spanning_ocr_object_cannot_translate_over_a_rejected_row(make_pipeline):
    p,core,engine,events,region=make_pipeline([
        line('Welcome to the station and its new mission',w=400,h=100),
        line('Neu or Id gane?',y=50,w=240),line('Exit',y=180)],merge_lines=True)
    start(p,region)
    wait_until(lambda:len(finals(events))==1 and len(objects(events))==3)
    assert engine.calls==['Exit']
    assert p.get_stats()['preserved_source']==2
    assert object_for(events,'Welcome to the station and its new mission')['line']['_ocr_rejection_reason']=='overlapping_rejected_region'


def test_rejected_row_outside_object_cap_still_protects_its_pixels(make_pipeline):
    p,core,engine,events,region=make_pipeline([
        line('Welcome to the station and its new mission',w=400,h=100),
        line('Neu or Id gane?',y=50,w=240)],merge_lines=False,max_objects=1)
    start(p,region)
    wait_until(lambda:len(objects(events))==1)
    assert objects(events)[0]['line']['_preserve_source']
    assert p.get_stats()['preserved_source']==1
    assert engine.calls==[] and updates(events)==[]


def test_good_to_bad_clears_old_stream_immediately_and_recovers(make_pipeline):
    from nkc_galgame_translator.presentation import OverlayState
    good,bad='New or Old game?','Neu or Id gane?'
    p,core,engine,events,region=make_pipeline([line(good)],max_missing=30)
    old_gate=engine.block(good)
    start(p,region)
    wait_until(lambda:len(updates(events))==1)
    initial=object_for(events,good);old_event=updates(events)[0]
    state=OverlayState();state.apply_objects(objects(events))
    assert state.apply_translation(old_event[2][0],old_event[2][1])
    core.set_scene([line(bad)])
    wait_until(lambda:object_for(events,bad) is not None)
    observed=object_for(events,bad)
    assert observed['revision']>initial['revision']
    state.apply_objects(objects(events));assert state.rendered=={}
    assert not state.apply_translation(old_event[2][0],old_event[2][1])
    checkpoint=len(updates(events));old_gate.set()
    wait_until(lambda:p.get_stats()['inflight']==0)
    assert len(updates(events))==checkpoint and engine.calls==[good]
    core.set_scene([line(good)])
    wait_until(lambda:len(finals(events))==1)
    recovered=object_for(events,good)
    assert recovered['revision']>observed['revision'] and not recovered['line'].get('_preserve_source')
    state.apply_objects(objects(events));last=finals(events)[0]
    assert state.apply_translation(last[2][0],last[2][1]) and len(state.rendered)==1
    assert engine.calls==[good,good]


@pytest.mark.parametrize('bad', ['Neu or Id gane?', 'Siiius', 'SYS f ebn', 'F1', 'HP 300'])
@pytest.mark.parametrize('options',[
    {'offline_only':True},
    {'aggressive_mode':True,'unlimited_requests':True},
    {'warmup_limit':512,'unlimited_requests':True},
])
def test_rejected_ocr_never_reaches_cached_dictionary_or_llm(tmp_path,options,bad):
    import httpx
    from nkc_galgame_translator.translation import TranslationEngine
    with httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('Rejected OCR reached HTTP'))) as client:
        with TranslationEngine({'api_key':'test-token',**options},tmp_path/'private.sqlite3',client=client) as engine:
            engine.set_term('game','en','zh-Hans',bad,'\u5386\u53f2\u9519\u8bef\u8bd1\u6587')
            before=engine.get_stats()
            core,events=FakeCore([line(bad)]),Recorder()
            pipeline=Pipeline(core,engine,events,interval=.005,settle=0,warmup_scope='profile:game')
            try:
                pipeline.start(lambda:(0,0,800,600),'game','en','zh-Hans')
                wait_until(lambda:pipeline.get_stats()['preserved_source']==1)
                # Wait for the exact unchanged-image confirmation path too.
                wait_until(lambda:core.captures>=4)
                assert updates(events)==[]
                after=engine.get_stats()
                assert after['session_requests']==0 and after['glossary_hits']==before['glossary_hits']==0
                assert after['short_texts']==after['complex_texts']==0
                assert engine.list_terms('game','en','zh-Hans')==[{'source':bad,'target':'\u5386\u53f2\u9519\u8bef\u8bd1\u6587'}]
                assert engine.get_warmup_status('game','en','zh-Hans',warmup_scope='profile:game')['completed']==0
            finally:
                pipeline.stop();pipeline.join(3);pipeline.pool.shutdown(wait=True,cancel_futures=True)
