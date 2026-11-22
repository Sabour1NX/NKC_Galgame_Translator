# SPDX-License-Identifier: MIT
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import time

import httpx
import pytest

from nkc_galgame_translator.translation import TranslationEngine, TranslationError, TranslationCancelled, LocalTranslationMiss, BudgetExceeded


def sse(text='\u6a21\u578b\u8bd1\u6587'):
    event={'choices':[{'delta':{'content':text},'finish_reason':'stop'}]}
    return httpx.Response(200,text='data: '+json.dumps(event,ensure_ascii=False)+'\n\ndata: [DONE]\n\n')


def tr(engine,text,game='A',**kwargs):
    return engine.translate(game,'en','zh-Hans',text,**kwargs)


def imported(engine,entries,shared=True,replace=False,game='A'):
    return engine.import_terms([{'source':a,'target':b} for a,b in entries],game,'en','zh-Hans',shared,replace)


@pytest.fixture
def engine(tmp_path):
    with TranslationEngine({},tmp_path/'expert.sqlite3') as result:yield result


def test_atomic_import_preserve_replace_duplicates_and_delete(engine):
    assert imported(engine,[('A','\u7532'),('B','\u4e59')])=={'inserted':2,'updated':0,'skipped':0}
    assert imported(engine,[('A','\u65b0\u7532'),('A','\u65b0\u7532')])=={'inserted':0,'updated':0,'skipped':2}
    assert dict((t['source'],t['target']) for t in engine.list_shared_terms('en','zh-Hans'))['A']=='\u7532'
    assert imported(engine,[('A','\u65b0\u7532')],replace=True)=={'inserted':0,'updated':1,'skipped':0}
    with pytest.raises(TranslationError):imported(engine,[('C','\u4e19'),('Bad','')])
    with pytest.raises(TranslationError):tr(engine,'C')
    assert dict((t['source'],t['target']) for t in engine.list_shared_terms('en','zh-Hans'))['A']=='\u65b0\u7532'
    assert engine.delete_shared_term('en','zh-Hans','A')
    assert not engine.delete_shared_term('en','zh-Hans','A')
    with pytest.raises(TranslationError):tr(engine,'A')


@pytest.mark.parametrize('entries',[[('X','\u7532'),('X','\u4e59')],[('HP {n}','\u751f\u547d\u503c')],[('HP {n}{n}','\u751f\u547d\u503c {n}')],[('X','\x00')]])
def test_import_rejects_ambiguous_or_invalid_complete_batch(engine,entries):
    with pytest.raises(TranslationError):imported(engine,[('Uncommitted','\u672a\u63d0\u4ea4'),*entries])
    assert not engine.list_shared_terms('en','zh-Hans')


def test_import_bad_languages_and_game_capacity_do_not_partially_write(engine):
    with pytest.raises(TranslationError):engine.import_terms([{'source':'A','target':'\u7532'}],'A','','zh-Hans')
    with pytest.raises(TranslationError):imported(engine,[(str(n),'\u503c') for n in range(5001)],shared=False)
    assert engine.list_terms('A','en','zh-Hans')==[]


def test_concurrent_imports_keep_game_capacity_atomic_across_instances(tmp_path):
    path=tmp_path/'x.db'
    with TranslationEngine({},path) as first,TranslationEngine({},path) as second:
        imported(first,[(f'entry{i}','\u8bd1\u6587') for i in range(4999)],shared=False)
        barrier=threading.Barrier(2)
        def write(engine,source):
            barrier.wait(3)
            return imported(engine,[(source,'\u8bd1\u6587')],shared=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(write,first,'first'),pool.submit(write,second,'second')]
            errors=[task.exception(4) for task in tasks]
        assert sum(isinstance(error,TranslationError) for error in errors)==1
        assert len(first.list_terms('A','en','zh-Hans'))==5000


def test_import_database_error_rolls_back_entire_merge_and_revision(engine):
    engine._db.execute("CREATE TRIGGER reject_test_term BEFORE INSERT ON shared_glossary WHEN new.source='reject' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    engine._db.commit()
    with pytest.raises(sqlite3.IntegrityError):imported(engine,[('before','\u6b64\u524d'),('reject','\u62d2\u7edd')])
    assert engine.list_shared_terms('en','zh-Hans')==[]
    assert engine._shared_revision(('A','en','zh-Hans'))==0


def test_configured_concurrency_is_bounded_to_sixteen(tmp_path):
    with TranslationEngine({'max_concurrency':100},tmp_path/'x.db') as e:assert e.max_concurrency==16


def test_aggressive_same_language_returns_source_without_api_or_storage(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('Same language must not call API'))) as client:
        with TranslationEngine({'api_key':'synthetic','aggressive_mode':True},tmp_path/'x.db',client=client) as e:
            chunks=[]
            assert e.translate('A','zh-Hans','zh-Hans','\u5df2\u7ecf\u662f\u4e2d\u6587',chunks.append)=='\u5df2\u7ecf\u662f\u4e2d\u6587'
            assert chunks==['\u5df2\u7ecf\u662f\u4e2d\u6587']
            stats=e.get_stats()
            assert stats['api_calls']==stats['cached_sentences']==stats['terms_learned']==0


@pytest.mark.parametrize('aggressive',[False,True])
def test_local_explanation_checks_closed_engine_before_mode(tmp_path,aggressive):
    e=TranslationEngine({'api_key':'synthetic','aggressive_mode':aggressive},tmp_path/'x.db')
    e.close()
    with pytest.raises(TranslationCancelled):e.explain_local('A','en','zh-Hans','Exit')
