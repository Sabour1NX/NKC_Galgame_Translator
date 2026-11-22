# SPDX-License-Identifier: MIT
"""The retired local mode can browse archives, but never produces translations."""
import json
import sqlite3
import httpx
import pytest
from nkc_galgame_translator.translation import TranslationEngine, TranslationError

@pytest.mark.parametrize('key',[None,'','   ','YOUR_API_KEY'])
def test_no_key_keeps_terms_readable_and_does_not_construct_http(tmp_path,monkeypatch,key):
    monkeypatch.setattr(httpx,'Client',lambda *a,**kw:pytest.fail('Unexpected HTTP client'))
    with TranslationEngine({'api_key':key},tmp_path/'book.sqlite3') as engine:
        engine.set_term('G','en','zh-CN','Hello','\u4f60\u597d')
        assert engine.list_terms('G','en','zh-CN')==[{'source':'Hello','target':'\u4f60\u597d'}]
        chunks=[]
        with pytest.raises(TranslationError,match='API'):
            engine.translate('G','en','zh-CN','Hello',on_chunk=chunks.append)
        assert chunks==[] and engine.get_stats()['api_calls']==0
        assert engine.explain_local('G','en','zh-CN','Hello')['route']=='api_required'
        assert engine.get_stats()['in_flight']==0

def test_no_key_browses_prior_ai_history_without_translating(tmp_path):
    from test_translation import sse_response
    path=tmp_path/'archive.sqlite3'
    with httpx.Client(transport=httpx.MockTransport(lambda request:sse_response('\u4f60\u597d'))) as client:
        with TranslationEngine({'api_key':'synthetic'},path,client=client) as engine:
            engine.translate('G','en','zh-CN','Hello',context='Tutorial')
    with TranslationEngine({},path) as engine:
        history=engine.list_translation_history('G','en','zh-CN')
        assert history[0]['context']=='Tutorial' and history[0]['translation']=='\u4f60\u597d'
        with pytest.raises(TranslationError):engine.translate('G','en','zh-CN','Hello')
        assert engine.get_stats()['api_calls']==0

def test_legacy_plain_cache_is_retained_without_making_offline_translation(tmp_path):
    path=tmp_path/'legacy.sqlite3'
    with TranslationEngine({},path) as engine:
        with engine._db:
            engine._db.execute('INSERT INTO translations VALUES(?,?,?,?,?,?,?,?)',('old','G','en','zh-CN','Hi','\u55e8','old',1))
    with TranslationEngine({},path) as engine:
        with pytest.raises(TranslationError):engine.translate('G','en','zh-CN','Hi')
        assert engine._db.execute('SELECT target FROM translations').fetchone()[0]=='\u55e8'

def test_same_language_and_empty_need_no_api(tmp_path):
    with TranslationEngine({},tmp_path/'book.sqlite3') as engine:
        assert engine.translate('G','en','en','Hello')=='Hello'
        assert engine.translate('G','en','zh-CN','')==''
        assert engine.get_stats()['total_requests']==0


def test_explicit_browse_only_pauses_network_even_with_saved_key(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('Browsing must not request API'))) as client:
        with TranslationEngine({'api_key':'synthetic','offline_only':True},tmp_path/'book.sqlite3',client=client) as engine:
            engine.set_term('G','en','zh-CN','Hello','\u4f60\u597d')
            assert engine.list_terms('G','en','zh-CN')
            with pytest.raises(TranslationError):engine.translate('G','en','zh-CN','Hello')
            assert engine.get_stats()['api_calls']==0
