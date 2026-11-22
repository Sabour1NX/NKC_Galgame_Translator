# SPDX-License-Identifier: MIT
"""Unlimited request policy, using synthetic HTTP and small real workloads."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import httpx
from PIL import Image
import pytest

from nkc_galgame_translator.translation import (BudgetExceeded, LocalTranslationMiss,
                                   TranslationEngine, TranslationError)
from nkc_galgame_translator.vision import VisionRecognizer


def sse(text='\u6a21\u578b\u8bd1\u6587'):
    event={'choices':[{'delta':{'content':text},'finish_reason':'stop'}]}
    return httpx.Response(200,text='data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n')


@pytest.fixture
def factory(tmp_path):
    clients=[];engines=[]
    def make(handler=None,**settings):
        client=httpx.Client(transport=httpx.MockTransport(handler or (lambda request:sse())))
        clients.append(client)
        engine=TranslationEngine({'api_key':'synthetic-test-key','max_retries':0,
            'retry_delay':0,'auto_promote_short_terms':False,**settings},
            tmp_path/f'engine-{len(engines)}.sqlite3',client=client)
        engines.append(engine)
        return engine
    yield make
    for engine in engines:engine.close()
    for client in clients:client.close()


def translate(engine,text='Welcome',**kwargs):
    return engine.translate('Game','en','zh-Hans',text,**kwargs)


def progress(engine):
    return engine.get_warmup_status('Game','en','zh-Hans',warmup_scope='profile:Game')


def test_default_is_finite_and_zero_still_forbids_requests(factory):
    engine=factory(max_requests=0)
    assert not engine.unlimited_requests
    assert engine.get_stats()['requests_remaining']==0
    assert progress(engine)['reason']=='ai_only'
    with pytest.raises(BudgetExceeded):translate(engine,warmup_scope='profile:Game')
    assert engine.get_stats()['api_calls']==0
    engine.set_term('Game','en','zh-Hans','Welcome','\u6b22\u8fce')
    with pytest.raises(TranslationError):translate(engine,warmup_scope='profile:Game')


@pytest.mark.parametrize('value',[None,0,1,'true','false',[],{},.5])
def test_unlimited_switch_is_strict_boolean(factory,value):
    with pytest.raises(TranslationError,match='API \u8bf7\u6c42\u65e0\u4e0a\u9650\u987b\u4e3a\u5f00\u6216\u5173\u3002'):
        factory(unlimited_requests=value)


@pytest.mark.parametrize('max_requests',[0,1,10000])
def test_unlimited_ai_continues_past_old_cap_without_local_phase(factory,max_requests):
    engine=factory(unlimited_requests=True,max_requests=max_requests,warmup_limit=2)
    # Simulate an already long-running session, not 10,000 paid requests.
    engine._stats['session_requests']=10000
    engine.set_term('Game','en','zh-Hans','Welcome','\u56fa\u5b9a\u8bd1\u6587')
    assert progress(engine)['reason']=='ai_only' and not progress(engine)['active']
    assert translate(engine,warmup_scope='profile:Game')=='\u6a21\u578b\u8bd1\u6587'
    assert translate(engine,warmup_scope='profile:Game')=='\u6a21\u578b\u8bd1\u6587'
    assert engine.get_context_status('Game','en','zh-Hans',warmup_scope='profile:Game')['records']==2
    assert translate(engine,warmup_scope='profile:Game')=='\u6a21\u578b\u8bd1\u6587'
    stats=engine.get_stats()
    assert stats['session_requests']==10003 and stats['total_requests']==3
    assert stats['unlimited_requests'] is True and stats['requests_remaining'] is None
    assert stats['warmup_reserved']==0 and stats['in_flight']==0
    assert json.loads(json.dumps(stats))['requests_remaining'] is None


def test_finite_limit_and_remaining_are_unchanged_when_explicitly_disabled(factory):
    engine=factory(unlimited_requests=False,max_requests=1)
    assert engine.get_stats()['requests_remaining']==1
    assert translate(engine,'First',warmup_scope='profile:Game')=='\u6a21\u578b\u8bd1\u6587'
    assert engine.get_stats()['requests_remaining']==0
    assert progress(engine)['reason']=='ai_only'
    with pytest.raises(BudgetExceeded):translate(engine,'Second',warmup_scope='profile:Game')
    assert engine.get_stats()['session_requests']==1


def test_unlimited_still_counts_retries_and_respects_retry_bound(factory):
    attempts=[]
    def handler(request):
        attempts.append(request)
        return httpx.Response(503) if len(attempts)%2 else sse()
    engine=factory(handler,unlimited_requests=True,max_requests=0,max_retries=1)
    assert translate(engine)=='\u6a21\u578b\u8bd1\u6587'
    assert len(attempts)==2
    stats=engine.get_stats()
    assert stats['session_requests']==stats['total_requests']==2
    assert stats['failures']==1 and stats['requests_remaining'] is None
    failing=factory(lambda request:httpx.Response(503),unlimited_requests=True,
                    max_requests=0,max_retries=1)
    with pytest.raises(TranslationError,match='HTTP 503'):translate(failing)
    assert failing.get_stats()['session_requests']==2


def test_unlimited_aggressive_calls_keep_bounded_concurrency_and_atomic_counts(factory):
    lock=threading.Lock();release=threading.Event();two_active=threading.Event()
    active=peak=calls=0
    def handler(request):
        nonlocal active,peak,calls
        with lock:
            active+=1;calls+=1;peak=max(peak,active)
            if active==2:two_active.set()
        try:
            assert release.wait(3)
            return sse()
        finally:
            with lock:active-=1
    engine=factory(handler,unlimited_requests=True,max_requests=0,max_concurrency=2,
                   aggressive_mode=True)
    engine._stats['session_requests']=10000
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(translate,engine,'Welcome '+str(i)) for i in range(4)]
        try:
            assert two_active.wait(2)
            assert calls==2 and peak==2
        finally:release.set()
        assert [future.result(timeout=3) for future in futures]==['\u6a21\u578b\u8bd1\u6587']*4
    stats=engine.get_stats()
    assert calls==4 and peak==2 and active==0
    assert stats['session_requests']==10004 and stats['total_requests']==4
    assert stats['in_flight']==0


def test_vision_and_translation_share_unlimited_counter_after_10000(factory):
    kinds=[]
    def handler(request):
        body=json.loads(request.content);kinds.append(body['stream'])
        if body['stream']:return sse()
        content=json.dumps({'lines':[{'id':0,'text':'Welcome'}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':content},
                                                  'finish_reason':'stop'}]})
    engine=factory(handler,unlimited_requests=True,max_requests=0)
    engine._stats['session_requests']=10000
    anchors=[{'text':'Welc0me','x':0,'y':0,'w':100,'h':20,'bg':[0,0,0],'fg':[255,255,255]}]
    with Image.new('RGB',(100,20)) as image:
        lines=VisionRecognizer(engine).recognize(image,anchors,'en')
    assert lines[0]['text']=='Welcome'
    assert translate(engine)=='\u6a21\u578b\u8bd1\u6587'
    assert kinds==[False,True]
    stats=engine.get_stats()
    assert stats['session_requests']==10002 and stats['total_requests']==2
    assert stats['requests_remaining'] is None


def test_unlimited_does_not_override_offline_or_input_bounds(factory):
    calls=[]
    engine=factory(lambda request:calls.append(request),unlimited_requests=True,
                   max_requests=0,offline_only=True)
    engine.set_term('Game','en','zh-Hans','Welcome','\u6b22\u8fce')
    with pytest.raises(TranslationError):translate(engine,warmup_scope='profile:Game')
    with pytest.raises(TranslationError):translate(engine,'Unknown',warmup_scope='profile:Game')
    assert engine.offline_only and not calls
    online=factory(lambda request:calls.append(request),unlimited_requests=True,
                   max_requests=0,max_input_chars=64)
    with pytest.raises(TranslationError,match='\u6587\u672c\u8fc7\u957f'):translate(online,'x'*65)
    assert not calls and online.get_stats()['session_requests']==0
