# SPDX-License-Identifier: MIT
"""Offline concurrency proofs: a held search never holds display output."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import time

import httpx
import pytest

from test_translation import factory, tr, sse_response
from test_context_agent25 import context_response, wait_context


def test_held_search_does_not_block_first_or_next_translation_and_is_single_flight(factory):
    entered, release = threading.Event(), threading.Event()
    requests, chunks = [], []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if 'tools' in body:
            entered.set()
            assert release.wait(3)
            return context_response()
        return sse_response('\u76f4\u63a5\u8bd1\u6587')
    engine = factory(handler, context_web_search=True, max_concurrency=2)
    try:
        with ThreadPoolExecutor(1) as pool:
            task = pool.submit(tr, engine, on_chunk=chunks.append)
            assert task.result(1) == '\u76f4\u63a5\u8bd1\u6587'
            assert entered.wait(1) and not release.is_set()
            assert pool.submit(tr, engine, 'Second paragraph', on_chunk=chunks.append).result(1) == '\u76f4\u63a5\u8bd1\u6587'
        assert chunks and all('fictional' not in chunk for chunk in chunks)
        assert sum('tools' in body for body in requests) == 1
        assert engine.get_stats()['api_calls'] == 3
        assert len(engine.context_agent._flights) == 1
    finally:
        release.set()
        wait_context(engine)
    tr(engine, 'Third paragraph')
    wait_context(engine)
    context = json.loads(requests[-1]['messages'][1]['content'])['context']
    assert json.loads(context)['web_reference']['status'] == 'searched'
    assert engine.get_stats()['context_requests'] == 1


def test_single_network_slot_is_reserved_for_display(factory):
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return sse_response()
    engine = factory(handler, context_web_search=True, max_concurrency=1)
    tr(engine)
    tr(engine, 'Next')
    assert len(seen) == 2 and all('tools' not in body for body in seen)
    assert not engine.get_context_agent_status()['background_active']


def test_background_consumes_existing_network_capacity_not_an_extra_slot(factory):
    search_entered, display_entered, release = threading.Event(), threading.Event(), threading.Event()
    lock = threading.Lock()
    active = peak = displays = 0
    def handler(request):
        nonlocal active, peak, displays
        body = json.loads(request.content)
        with lock:
            active += 1
            peak = max(peak, active)
            if 'tools' not in body:displays += 1
            number = displays
        try:
            if 'tools' in body:
                search_entered.set()
                assert release.wait(3)
                return context_response()
            if number > 1:
                display_entered.set()
                assert release.wait(3)
            return sse_response()
        finally:
            with lock:active -= 1
    engine = factory(handler, context_web_search=True, max_concurrency=2)
    tr(engine)
    assert search_entered.wait(1)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(tr, engine, 'Second')
        assert display_entered.wait(1)
        second = pool.submit(tr, engine, 'Third')
        try:
            deadline = time.monotonic() + 1
            while not engine._foreground_waiters:
                assert time.monotonic() < deadline
                time.sleep(.005)
            with lock:assert active == peak == 2 and displays == 2
        finally:release.set()
        assert first.result(2) and second.result(2)
    wait_context(engine)
    assert peak == 2


def test_context_scope_language_and_identity_never_cross(factory):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return context_response() if 'tools' in body else sse_response()
    engine = factory(handler, context_web_search=True)
    tr(engine, warmup_scope='game-A')
    wait_context(engine)
    engine.translate('test-game', 'ja', 'zh-Hans', '\u3053\u3093\u306b\u3061\u306f', warmup_scope='game-A')
    wait_context(engine)
    engine.translate('test-game', 'en', 'ja', 'Hello', warmup_scope='game-A')
    wait_context(engine)
    tr(engine, warmup_scope='game-B')
    wait_context(engine)
    tr(engine, context='Different scene', warmup_scope='game-A')
    wait_context(engine)
    display = [body for body in requests if 'tools' not in body]
    assert len(display) == 5
    assert all('web_reference' not in json.loads(body['messages'][1]['content'])['context'] for body in display)


def test_close_cancels_joins_context_and_preserves_request_and_usage_counts(factory, tmp_path):
    entered = threading.Event()
    class SearchStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":2}}\n\n'
            entered.set()
            assert engine._stop.wait(3)
            yield b'data: [DONE]\n\n'
    def handler(request):
        return httpx.Response(200, stream=SearchStream()) if 'tools' in json.loads(request.content) else sse_response()
    engine = factory(handler, context_web_search=True, max_concurrency=2)
    tr(engine)
    assert entered.wait(1)
    engine.close()
    worker = engine.context_agent._background
    assert worker is not None and not worker.is_alive()
    assert not engine.context_agent._flights
    assert engine.get_stats()['api_calls'] == 2
    assert engine.get_stats()['prompt_tokens'] == 33
    assert engine.get_stats()['completion_tokens'] == 5
    assert engine.context_agent.status()['cache_entries'] == 0
    with sqlite3.connect(tmp_path/'codebook.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM usage').fetchone()[0] == 2
    assert engine._slots.acquire(False) and engine._slots.acquire(False)
    engine._slots.release();engine._slots.release()


def test_cancel_before_context_transport_starts_returns_reserved_slot(factory, monkeypatch):
    engine = factory(context_web_search=True, max_concurrency=2)
    def cancelled(*args):
        from nkc_galgame_translator.translation import TranslationCancelled
        raise TranslationCancelled('stopped before request')
    monkeypatch.setattr(engine.context_agent, 'resolve', cancelled)
    assert tr(engine)
    wait_context(engine)
    assert engine._slots.acquire(False) and engine._slots.acquire(False)
    engine._slots.release();engine._slots.release()
    assert engine.get_stats()['api_calls'] == 1


def test_thread_start_failure_keeps_completed_display_and_returns_slot(factory, monkeypatch):
    engine = factory(context_web_search=True, max_concurrency=2)
    def fail(_):raise RuntimeError('no worker resources')
    monkeypatch.setattr(threading.Thread, 'start', fail)
    assert tr(engine) == '\u4f60\u597d'
    assert engine._slots.acquire(False) and engine._slots.acquire(False)
    engine._slots.release();engine._slots.release()
    assert engine.get_stats()['api_calls'] == 1
    assert engine.get_stats()['context_failures'] == 1


@pytest.mark.parametrize('status', [401, 402, 403])
def test_background_auth_failure_has_negative_cache_without_replacing_display(factory, status):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(status, text='private-response-body') if 'tools' in body else sse_response('\u5df2\u663e\u793a')
    engine = factory(handler, context_web_search=True)
    assert tr(engine) == '\u5df2\u663e\u793a'
    wait_context(engine)
    assert tr(engine, 'Next paragraph') == '\u5df2\u663e\u793a'
    wait_context(engine)
    assert sum('tools' in body for body in seen) == 1
    assert engine.get_context_agent_status()['status'] == 'unavailable'
    assert 'private-response-body' not in str(engine.get_context_agent_status())


def test_many_scopes_do_not_queue_background_work(factory):
    entered, release = threading.Event(), threading.Event()
    searches = []
    def handler(request):
        body = json.loads(request.content)
        if 'tools' in body:
            searches.append(body)
            entered.set()
            assert release.wait(3)
            return context_response()
        return sse_response()
    engine = factory(handler, context_web_search=True, max_concurrency=2)
    try:
        tr(engine, warmup_scope='first')
        assert entered.wait(1)
        worker = engine.context_agent._background
        for index in range(10):
            tr(engine, warmup_scope=f'other-{index}')
        assert searches and len(searches) == 1
        assert engine.context_agent._background is worker
        assert len(engine.context_agent._flights) == 1
    finally:
        release.set()
        wait_context(engine)
    assert len(searches) == 1
