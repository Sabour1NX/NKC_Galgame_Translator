# SPDX-License-Identifier: MIT
"""Warmup is retired: scope identity now separates persistent AI context."""
import httpx
import pytest
from nkc_galgame_translator.translation import TranslationEngine, TranslationError
from test_translation import sse_response

@pytest.mark.parametrize('limit',[0,50,100,512,1000])
@pytest.mark.parametrize('aggressive',[False,True])
def test_legacy_warmup_does_not_switch_away_from_ai(tmp_path,limit,aggressive):
    with httpx.Client(transport=httpx.MockTransport(lambda request:sse_response())) as client:
        with TranslationEngine({'api_key':'synthetic','warmup_limit':limit,'aggressive_mode':aggressive},tmp_path/'book.sqlite3',client=client) as engine:
            for _ in range(3):engine.translate('G','en','zh-CN','Hello',warmup_scope='profile:G')
            assert engine.get_stats()['api_calls']==3
            state=engine.get_warmup_status('G','en','zh-CN',warmup_scope='profile:G')
            assert state['reason']=='ai_only' and not state['active']
            assert engine.get_context_status('G','en','zh-CN',warmup_scope='profile:G')['records']==3

@pytest.mark.parametrize('identity',['',3,'bad\nidentity','x'*1025])
def test_invalid_context_identity_rejected_before_network(tmp_path,identity):
    with TranslationEngine({'api_key':'synthetic'},tmp_path/'book.sqlite3') as engine:
        with pytest.raises(TranslationError):engine.translate('','en','zh-CN','Hello',warmup_scope=identity)
        assert engine.get_stats()['api_calls']==0
