# SPDX-License-Identifier: MIT
import sqlite3
from threading import current_thread

from nkc_galgame_translator.context_archive import scope_key
from nkc_galgame_translator.event_queue import DisplayEvents
from nkc_galgame_translator.live_capture import cursor_correction
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.translation import TranslationEngine
from tools.cuda_ocr_helper import ArenaRun
from test_pipeline import FakeCore, FakeEngine, Recorder, finals, line, wait_until


def test_cumulative_stream_cleanup_preserves_barriers_and_final():
    events=DisplayEvents()
    def fragment(n):
        return ('translation',3,(1,{'_revision':2,'text':str(n)},'source',False))
    for i in range(10000):
        events.put(fragment(i))
    barrier=('objects',3,[])
    events.put(barrier)
    events.put(fragment(10000))
    last=('translation',3,(1,{'_revision':2,'text':'done'},'source',True))
    events.put(last)
    assert events.qsize()==4
    assert [events.get_nowait() for _ in range(4)]==[fragment(9999),barrier,fragment(10000),last]


def test_cursor_recovers_partial_without_replacing_verified_or_adjacent_caption():
    old=line('Hello',confidence=63)
    new=dict(old,text='Hello there',w=290,confidence=92)
    assert cursor_correction(old,new)
    assert not cursor_correction(dict(old,_subtitle_read=True),new)
    assert not cursor_correction(dict(old,y=54),new)
    assert not cursor_correction(dict(old,_selection_id=1),new)


def test_cursor_dispatch_survives_enabled_page_batch():
    class Engine(FakeEngine):
        def screen_budget(self):return 16384
        def translate(self,*args,**kwargs):
            self.worker=current_thread().name
            return super().translate(*args,**kwargs)
        def translate_screen(self,game,src,dst,rows,*args,**kwargs):
            self.batch=[r['text'] for r in rows]
            return self.batch
    rows=[line('First example'),line('Second example',1),line('Focused example',2,_pointer_priority=True)]
    engine,events=Engine(),Recorder()
    pipe=Pipeline(FakeCore(rows),engine,events,interval=.02,settle=0,merge_lines=False,
                  cursor_attention=True,persist_results=True,translation_workers=2)
    try:
        pipe.start(lambda:(0,0,800,600),'test','en','zh-Hans')
        wait_until(lambda:len(finals(events))>=3)
        assert engine.calls==['Focused example']
        assert engine.worker.startswith('cursor-translate')
        assert engine.batch==['First example','Second example']
    finally:
        pipe.stop()
        pipe.join(4)


def test_legacy_archive_totals_survive_rollback_and_profile_deletion(tmp_path):
    path=tmp_path/'history.db'
    config={'offline_only':True}
    scope=('test','ja','zh-Hans')
    with TranslationEngine(config,path) as engine:
        archive=engine.context_archive
        with engine._db:
            archive.record(scope,None,'old','done','','','test')
        original=archive.status(scope)
    with sqlite3.connect(path) as db:
        db.executescript('DROP TRIGGER ai_event_added; DROP TRIGGER ai_event_removed; DROP TABLE ai_event_totals; DROP TABLE ai_archive_migrations;')
    with TranslationEngine(config,path) as engine:
        archive=engine.context_archive
        assert archive.status(scope)==original
        archive.record(scope,None,'extra','done','','','test')
        assert archive.status(scope)['records']==2
        engine._db.rollback()
        assert archive.status(scope)==original
        with engine._db:
            archive.delete_profile(scope[0])
        assert archive.status(scope)['records']==0


def test_arena_trim_requires_sustained_drop_and_keeps_session():
    class Input:
        def __init__(self,size):self.nbytes=size
    options=object()
    calls=[]
    def run(*args):calls.append(len(args))
    arena=ArenaRun(run,options)
    for size in (200,30,200,30,30,30,30):
        arena(None,{'input':Input(size)})
    assert calls==[2,2,2,2,2,3,2]
    assert arena.trims==1
