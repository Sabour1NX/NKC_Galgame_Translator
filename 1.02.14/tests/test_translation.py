# SPDX-License-Identifier: MIT
"""Offline tests. No DeepSeek credentials or internet are needed."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
import threading
import time

import httpx
import pytest

from nkc_galgame_translator.translation import (
    BudgetExceeded, TranslationCancelled, TranslationEngine, TranslationError,
    _mask_terms,
)


def sse_response(text="\u4f60\u597d", *, finish="stop", done=True, usage=True, pieces=None):
    events = []
    for piece in pieces if pieces is not None else list(text):
        events.append({"choices": [{"delta": {"content": piece}, "finish_reason": None}]})
    events.append({"choices": [{"delta": {}, "finish_reason": finish}]})
    if usage:
        events.append({"choices": [], "usage": {"prompt_tokens": 21, "completion_tokens": 3}})
    data = ": keep-alive\n\n" + "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events)
    if done:
        data += "data: [DONE]\n\n"
    return httpx.Response(200, text=data, headers={"Content-Type": "text/event-stream"})


@pytest.fixture
def factory(tmp_path):
    engines, clients = [], []

    def make(handler=None, **settings):
        handler = handler or (lambda request: sse_response())
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        engine = TranslationEngine({"api_key": "not-a-real-key", "retry_delay": 0,
                                    "auto_promote_short_terms": False,
                                    **settings}, tmp_path / "codebook.sqlite3", client=client)
        engines.append(engine)
        return engine

    yield make
    for engine in engines:
        engine.close()
    for client in clients:
        client.close()


def tr(engine, text="Hello", **kwargs):
    return engine.translate("test-game", "en", "zh-Hans", text, **kwargs)


def test_windose_rebirth_label_and_ocr_variant(factory):
    requests=[]
    engine=factory(lambda request:requests.append(request) or sse_response('\u5176\u4ed6\u8bd1\u540d'))
    chunks=[]
    assert engine.translate('NEEDY GIRL OVERDOSE (Windose)','ja','zh-Hans','\u30a2\u30ab\u8ee2\u751f',chunks.append)=='\u8f6c\u751f'
    assert engine.translate('My save','ja','zh-Hans','\u30a2\u529b\u8ee2\u751f',chunks.append,game_executable='Windose.exe')=='\u8f6c\u751f'
    assert chunks==['\u8f6c\u751f','\u8f6c\u751f'] and not requests
    assert engine.translate('Other game','ja','zh-Hans','\u30a2\u30ab\u8ee2\u751f')=='\u5176\u4ed6\u8bd1\u540d'


def test_sse_stream_and_usage(factory):
    requests = []
    def handler(request):
        requests.append(request)
        return sse_response("\u4f60\u597d\u4e16\u754c")
    engine = factory(handler)
    chunks = []
    assert tr(engine, on_chunk=chunks.append) == "\u4f60\u597d\u4e16\u754c"
    assert chunks[:4] == ["\u4f60", "\u4f60\u597d", "\u4f60\u597d\u4e16", "\u4f60\u597d\u4e16\u754c"]
    stats=engine.get_stats()
    assert stats['first_token_samples']==1
    assert stats['last_first_token_ms']>=0
    assert stats['mean_first_token_ms']==stats['last_first_token_ms']
    body = json.loads(requests[0].content)
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["stream"] is True
    assert body["max_tokens"] == 512
    assert requests[0].url == "https://api.deepseek.com/chat/completions"
    stats = engine.get_stats()
    assert stats["api_calls"] == 1
    assert stats["prompt_tokens"] == 21
    assert stats["completion_tokens"] == 3


@pytest.mark.parametrize('value', ['private-sentinel-do-not-echo', -1, float('nan'),
                                 float('inf'), None, {}, [], True, 3.5, 2**80])
def test_invalid_usage_cannot_replace_valid_translation_or_leak(factory, tmp_path, value):
    def handler(request):
        response = sse_response('\u6b63\u5e38\u8bd1\u6587', usage=False)
        usage = json.dumps({'choices': [], 'usage': {
            'prompt_tokens': value, 'completion_tokens': value}})
        return httpx.Response(200, text=response.text.replace(
            'data: [DONE]', 'data: '+usage+'\n\ndata: [DONE]'))
    engine = factory(handler)
    assert tr(engine) == '\u6b63\u5e38\u8bd1\u6587'
    assert engine.get_stats()['prompt_tokens'] == 0
    assert engine.get_stats()['completion_tokens'] == 0
    assert tr(engine) == '\u6b63\u5e38\u8bd1\u6587'
    assert engine.get_stats()['api_calls'] == 2
    with sqlite3.connect(tmp_path/'codebook.sqlite3') as db:
        assert 'private-sentinel-do-not-echo' not in '\n'.join(db.iterdump())


def test_invalid_usage_does_not_overwrite_sanitized_stream_error(factory):
    secret = 'private-sentinel-do-not-echo'
    usage = json.dumps({'choices': [], 'usage': {
        'prompt_tokens': secret, 'completion_tokens': secret}})
    response = sse_response('\u622a\u65ad\u8bd1\u6587', finish='length', usage=False)
    response_text = response.text.replace('data: [DONE]', 'data: '+usage+'\n\ndata: [DONE]')
    engine = factory(lambda request: httpx.Response(200, text=response_text))
    with pytest.raises(TranslationError, match='\u672a\u5b8c\u6574\u7ed3\u675f') as caught:
        tr(engine)
    assert secret not in str(caught.value)
    assert engine.get_stats()['cached_sentences'] == 0
    assert engine.get_stats()['failures'] == 1


@pytest.mark.parametrize('value', [9, 9.0, '9'])
def test_valid_numeric_usage_remains_counted(factory, value):
    usage = json.dumps({'choices': [], 'usage': {
        'prompt_tokens': value, 'completion_tokens': value}})
    response_text = sse_response(usage=False).text.replace(
        'data: [DONE]', 'data: '+usage+'\n\ndata: [DONE]')
    engine = factory(lambda request: httpx.Response(200, text=response_text))
    assert tr(engine) == '\u4f60\u597d'
    assert engine.get_stats()['prompt_tokens'] == 9
    assert engine.get_stats()['completion_tokens'] == 9


def test_archive_is_persistent_but_new_calls_always_request_ai(factory):
    engine = factory()
    assert tr(engine) == tr(engine) == '\u4f60\u597d'
    assert engine.get_stats()['api_calls'] == 2
    assert engine.get_stats()['cache_hits'] == 0
    reopened = factory()
    assert len(reopened.list_translation_history('test-game','en','zh-Hans')) == 2
    assert tr(reopened) == '\u4f60\u597d'
    assert reopened.get_stats()['api_calls'] == 1
    assert reopened.list_translation_history('other-game','en','zh-Hans') == []



def test_model_and_endpoint_partition_cache(factory):
    tr(factory())
    other = factory(model="other-model")
    tr(other)
    assert other.get_stats()["api_calls"] == 1
    other_endpoint = factory(base_url="https://translator.example/v1")
    tr(other_endpoint)
    assert other_endpoint.get_stats()["api_calls"] == 1


def test_exact_glossary_can_be_browsed_without_key_but_does_not_translate(factory):
    engine = factory(api_key='', max_requests=0)
    engine.set_term('test-game','en','zh-Hans','Remilia','\u857e\u7c73\u8389\u4e9a')
    assert engine.list_terms('test-game','en','zh-Hans')[0]['target'] == '\u857e\u7c73\u8389\u4e9a'
    with pytest.raises(TranslationError, match='API'):
        tr(engine, 'Remilia')
    assert engine.get_stats()['api_calls'] == 0



def test_terms_are_untrusted_references_instead_of_local_substitution(factory):
    sent=[]
    def handler(request):
        sent.append(json.loads(json.loads(request.content)['messages'][-1]['content']))
        return sse_response('\u6a21\u578b\u7ed3\u679c')
    engine = factory(handler)
    engine.set_term('test-game','en','zh-Hans','Remilia','\u857e\u7c73\u8389\u4e9a')
    assert tr(engine,'Welcome Remilia') == '\u6a21\u578b\u7ed3\u679c'
    assert sent[0]['text'] == 'Welcome Remilia'
    assert json.loads(sent[0]['context'])['terms'] == [{'source':'Remilia','translation':'\u857e\u7c73\u8389\u4e9a'}]
    engine.set_term('test-game','en','zh-Hans','Remilia','\u857e\u7c73')
    tr(engine,'Welcome Remilia')
    assert json.loads(sent[1]['context'])['terms'][0]['translation'] == '\u857e\u7c73'
    assert engine.delete_term('test-game','en','zh-Hans','Remilia')



def test_mask_overlap_cjk_ascii_boundaries_and_duplicates():
    source = "cat concatenate catfish cat. \u30ec\u30df\u30ea\u30a2\u30fb\u30b9\u30ab\u30fc\u30ec\u30c3\u30c8\u3068\u30ec\u30df\u30ea\u30a2 cat\u3067\u3059"
    terms = [{"source": "cat", "target": "\u732b"},
             {"source": "\u30ec\u30df\u30ea\u30a2", "target": "\u857e\u7c73"},
             {"source": "\u30ec\u30df\u30ea\u30a2\u30fb\u30b9\u30ab\u30fc\u30ec\u30c3\u30c8", "target": "\u857e\u7c73\u8389\u4e9a·\u65af\u5361\u96f7\u7279"}]
    masked = _mask_terms(source, terms)
    assert "concatenate catfish" in masked.text
    assert masked.restore(masked.text, final=True) == "\u732b concatenate catfish \u732b. \u857e\u7c73\u8389\u4e9a·\u65af\u5361\u96f7\u7279\u3068\u857e\u7c73 \u732b\u3067\u3059"
    assert len(masked.replacements) == 3
    assert masked == _mask_terms(source, terms)


def test_translation_stream_is_raw_ai_without_local_term_placeholders(factory):
    engine=factory(lambda request:sse_response('\u6b22\u8fce Remilia'))
    engine.set_term('test-game','en','zh-Hans','Remilia','\u56fa\u5b9a\u66ff\u6362\u4e0d\u5f97\u53d1\u751f')
    chunks=[]
    assert tr(engine,'Welcome Remilia',on_chunk=chunks.append)=='\u6b22\u8fce Remilia'
    assert chunks[-1]=='\u6b22\u8fce Remilia'



@pytest.mark.parametrize('result',['\u4f60\u597d','__broken__'])
def test_ai_output_does_not_require_locally_invented_placeholders(factory,result):
    engine=factory(lambda request:sse_response(result))
    engine.set_term('test-game','en','zh-Hans','Hello','\u65e7\u8bd1\u6587')
    assert tr(engine)==result



def test_reference_terms_are_isolated_by_game_and_language(factory):
    sent=[]
    def handler(request):
        sent.append(json.loads(json.loads(request.content)['messages'][-1]['content']))
        return sse_response()
    engine=factory(handler)
    engine.set_term('other','en','zh-Hans','Hello','\u79d8\u5bc6\u5176\u4ed6\u6863\u6848')
    tr(engine)
    assert '\u79d8\u5bc6\u5176\u4ed6\u6863\u6848' not in sent[-1]['context']



def test_duplicate_concurrent_requests_singleflight(factory):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def handler(request):
        calls.append(request)
        entered.set()
        assert release.wait(3)
        return sse_response()
    engine = factory(handler)
    with ThreadPoolExecutor(max_workers=10) as pool:
        first = pool.submit(tr, engine)
        assert entered.wait(2)
        rest = [pool.submit(tr, engine) for _ in range(9)]
        deadline = time.monotonic() + 2
        while engine.get_stats()["shared_requests"] < 9 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert engine.get_stats()["shared_requests"] == 9
        release.set()
        assert [future.result(3) for future in [first, *rest]] == ["\u4f60\u597d"] * 10
    assert len(calls) == 1
    assert engine.get_stats()["shared_requests"] == 9


def test_concurrency_limit(factory):
    lock = threading.Lock()
    active = peak = 0
    def handler(request):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return sse_response()
    engine = factory(handler, max_concurrency=2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda number: tr(engine, str(number)), range(8)))
    assert results == ["\u4f60\u597d"] * 8
    assert peak == 2


def test_budget_is_atomic_and_archive_does_not_bypass_it(factory):
    engine = factory(max_requests=2)
    tr(engine)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(tr, engine, str(i)) for i in range(6)]
    errors = [future.exception() for future in futures]
    assert sum(isinstance(error, BudgetExceeded) for error in errors) == 5
    assert engine.get_stats()["api_calls"] == 2
    with pytest.raises(BudgetExceeded):
        tr(engine)


@pytest.mark.parametrize("status", [401, 402, 403, 404, 400, 302])
def test_http_errors_do_not_leak_server_content_or_key(factory, status):
    engine = factory(lambda request: httpx.Response(status, text="private-credential"), api_key="private-credential")
    failures = []
    engine.on_backend_failure = lambda owner, code: failures.append((owner, code))
    with pytest.raises(TranslationError) as error:
        tr(engine)
    assert "private-credential" not in str(error.value)
    assert str(status) in str(error.value)
    assert failures == [(engine, f'HTTP {status}')]
    assert engine.get_stats()["api_calls"] == 1


def test_transient_retry_is_bounded_and_counted(factory):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429) if calls == 1 else sse_response()
    engine = factory(handler)
    failures = []
    engine.on_backend_failure = lambda owner, code: failures.append(code)
    assert tr(engine) == "\u4f60\u597d"
    assert engine.get_stats()["api_calls"] == 2
    assert engine.get_stats()["failures"] == 1
    assert failures == []


def test_retry_cannot_exceed_budget(factory):
    engine = factory(lambda request: httpx.Response(503), max_requests=1)
    with pytest.raises(BudgetExceeded):
        tr(engine)
    assert engine.get_stats()["api_calls"] == 1


@pytest.mark.parametrize('failure,code', [(httpx.ReadTimeout, 'LLM_TIMEOUT'), (httpx.ConnectError, 'LLM_CONNECTION')])
def test_network_timeout_retries_then_safe_error(factory, failure, code):
    def handler(request):
        raise failure("credential-in-unsafe-exception")
    engine = factory(handler)
    failures = []
    engine.on_backend_failure = lambda owner, value: failures.append(value)
    with pytest.raises(TranslationError) as error:
        tr(engine)
    assert "credential" not in str(error.value)
    assert failures == [code]
    assert engine.get_stats()["api_calls"] == 2


@pytest.mark.parametrize("finish,done,text", [("length", True, "\u534a\u53e5"), ("stop", False, "\u4e0d\u5b8c\u6574"),
                                           (None, True, "\u672a\u77e5"), ("content_filter", True, ""),
                                           ("stop", True, "  ")])
def test_incomplete_and_truncated_not_cached(factory, finish, done, text):
    engine = factory(lambda request: sse_response(text, finish=finish, done=done))
    with pytest.raises(TranslationError):
        tr(engine)
    assert engine.get_stats()["cached_sentences"] == 0
    assert engine.get_stats()["api_calls"] == 1


def test_bad_sse_rejected(factory):
    engine = factory(lambda request: httpx.Response(200, text="data: {broken json}\n\n"))
    with pytest.raises(TranslationError, match="\u65e0\u6548"):
        tr(engine)


def test_api_v1_path_supported(factory):
    urls = []
    engine = factory(lambda request: urls.append(str(request.url)) or sse_response(), base_url="https://api.deepseek.com/v1/")
    tr(engine)
    assert urls == ["https://api.deepseek.com/v1/chat/completions"]


@pytest.mark.parametrize("url", ["http://api.deepseek.com", "https://secret@api.deepseek.com", "https://api.deepseek.com?key=secret"])
def test_unsafe_endpoint_rejected(factory, url):
    with pytest.raises(TranslationError):
        factory(base_url=url)


def test_oversize_and_missing_key_do_not_spend_budget(factory):
    engine = factory(api_key="")
    with pytest.raises(TranslationError, match="API"):
        tr(engine)
    with pytest.raises(TranslationError, match="\u6587\u672c\u8fc7\u957f"):
        tr(engine, "a" * 4001)
    assert engine.get_stats()["api_calls"] == 0


def test_same_language_and_empty_are_free(factory):
    engine = factory(api_key="")
    assert engine.translate("test", "en", "en", "Hello") == "Hello"
    assert tr(engine, "  ") == ""
    assert engine.get_stats()["api_calls"] == 0


def test_close_is_idempotent_and_cancels_new_work(factory):
    engine = factory()
    engine.close()
    engine.close()
    with pytest.raises(TranslationCancelled):
        tr(engine)


def test_db_contains_no_api_key(factory, tmp_path):
    engine = factory(api_key="unique-secret-value-never-store")
    tr(engine)
    engine.close()
    with sqlite3.connect(tmp_path / "codebook.sqlite3") as db:
        dump = "\n".join(db.iterdump())
    assert "unique-secret-value-never-store" not in dump


def test_reference_edit_during_request_keeps_raw_ai_and_captured_context(factory):
    entered,release=threading.Event(),threading.Event()
    def handler(request):
        entered.set(); assert release.wait(3)
        return sse_response('\u539f\u59cb\u6a21\u578b\u8bd1\u6587')
    engine=factory(handler)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(tr,engine)
        assert entered.wait(2)
        engine.set_term('test-game','en','zh-Hans','Hello','\u540e\u6765\u624b\u6539')
        release.set()
        assert pending.result(3)=='\u539f\u59cb\u6a21\u578b\u8bd1\u6587'
    history=engine.list_translation_history('test-game','en','zh-Hans')
    assert history[0]['translation']=='\u539f\u59cb\u6a21\u578b\u8bd1\u6587'
    assert '\u540e\u6765\u624b\u6539' not in history[0]['prompt_context']



def test_singleflight_error_propagates_and_future_is_removed(factory):
    entered, release = threading.Event(), threading.Event()
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(3)
        return httpx.Response(401)
    engine = factory(handler)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(tr, engine)]
        assert entered.wait(2)
        pending.extend(pool.submit(tr, engine) for _ in range(3))
        time.sleep(0.05)
        release.set()
        assert all(isinstance(future.exception(3), TranslationError) for future in pending)
    assert calls == 1
    assert engine.get_stats()["in_flight"] == 0
    with pytest.raises(TranslationError):
        tr(engine)
    assert calls == 2


def test_close_cancels_waiting_and_in_flight_requests(factory):
    entered, release = threading.Event(), threading.Event()
    def handler(request):
        entered.set()
        assert release.wait(3)
        return sse_response()
    engine = factory(handler, max_concurrency=1)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(tr, engine, "one")]
        assert entered.wait(2)
        pending.extend([pool.submit(tr, engine, "one"), pool.submit(tr, engine, "two")])
        engine.close()
        release.set()
        assert all(isinstance(future.exception(3), TranslationCancelled) for future in pending)


def test_reference_lookup_does_not_materialize_entire_glossary(factory, monkeypatch):
    engine = factory()
    tr(engine)
    def unexpected(*args):
        pytest.fail("bounded reference must not load the whole glossary")
    monkeypatch.setattr(engine, "list_terms", unexpected)
    assert tr(engine) == "\u4f60\u597d"




def test_success_stores_full_history_without_expert_term_learning(factory):
    engine=factory(lambda request:sse_response('\u857e\u7c73\u8389\u4e9a'),auto_promote_short_terms=True)
    tr(engine,'Remilia')
    assert engine.list_terms('test-game','en','zh-Hans')==[]
    assert engine.get_context_status('test-game','en','zh-Hans')['records']==1
    assert engine.get_stats()['api_calls']==1



def test_prior_translation_becomes_ai_reference_for_next_sentence(factory):
    sent=[]
    def handler(request):
        sent.append(json.loads(json.loads(request.content)['messages'][-1]['content']))
        return sse_response('\u857e\u7c73\u8389\u4e9a')
    engine=factory(handler)
    tr(engine,'Remilia'); tr(engine,'Welcome Remilia')
    assert sent[-1]['text']=='Welcome Remilia'
    recent=json.loads(sent[-1]['context'])['recent_translations']
    assert recent[0]['source']=='Remilia' and recent[0]['translation']=='\u857e\u7c73\u8389\u4e9a'



def test_auto_learning_is_optional_and_does_not_learn_sentences(factory):
    engine = factory(auto_promote_short_terms=False)
    tr(engine, "Remilia")
    assert engine.list_terms("test-game", "en", "zh-Hans") == []
    enabled = factory(auto_promote_short_terms=True)
    tr(enabled, "You are welcome")
    assert enabled.list_terms("test-game", "en", "zh-Hans") == []
    assert enabled.get_stats()["terms_learned"] == 0


def test_manual_reference_edit_does_not_replace_stored_ai_result(factory):
    engine=factory()
    tr(engine)
    engine.set_term('test-game','en','zh-Hans','Hello','\u624b\u5de5\u8bed\u5883')
    assert engine.list_translation_history('test-game','en','zh-Hans')[0]['translation']=='\u4f60\u597d'



def test_each_completed_call_is_preserved_even_identical_text(factory):
    engine=factory()
    for _ in range(4): tr(engine)
    assert engine.get_stats()['api_calls']==4
    assert engine.get_context_status('test-game','en','zh-Hans')['records']==4



def test_parallel_labels_all_append_context_history(factory):
    engine=factory()
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(lambda i:tr(engine,str(i)),range(6)))==['\u4f60\u597d']*6
    assert engine.get_context_status('test-game','en','zh-Hans')['records']==6
    assert engine.get_stats()['terms_learned']==0



def test_invalid_translation_is_not_promoted(factory):
    engine = factory(lambda request: sse_response("\u8fd9\u662f\u89e3\u91ca\uff1a\u4e0d\u5e94\u6210\u4e3a\u672f\u8bed\u3002"), auto_promote_short_terms=True)
    tr(engine, "Start")
    assert engine.list_terms("test-game", "en", "zh-Hans") == []
