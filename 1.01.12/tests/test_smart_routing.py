# SPDX-License-Identifier: MIT
"""Legacy smart/template settings never re-enable local translation."""
import json
import httpx
import pytest
from nkc_galgame_translator.translation import TranslationEngine, BudgetExceeded
from test_translation import sse_response

@pytest.mark.parametrize('text',['Hello','HP 120','Hello / Exit','A very long sentence. It continues here.','New Game','Remilia','Hello\nExit'])
@pytest.mark.parametrize('legacy',[{}, {'smart_mode':True,'expert_enabled':True,'use_shared_dictionary':True}, {'smart_mode':False,'expert_enabled':False}])
def test_all_lengths_and_retired_settings_use_ai(tmp_path,text,legacy):
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        return sse_response('\u6a21\u578b\u8bd1\u6587')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with TranslationEngine({'api_key':'synthetic',**legacy},tmp_path/'book.sqlite3',client=client) as engine:
            engine.set_term('G','en','zh-CN',text,'\u672c\u5730\u503c')
            engine.import_terms([{'source':'HP {n}','target':'\u751f\u547d {n}'}],'G','en','zh-CN',shared=True)
            assert engine.translate('G','en','zh-CN',text)=='\u6a21\u578b\u8bd1\u6587'
            assert json.loads(requests[0]['messages'][1]['content'])['text']==text
            assert engine.get_stats()['ai_only'] and not engine.get_stats()['expert_enabled']
            assert engine.explain_local('G','en','zh-CN',text)['route']=='llm'
            assert engine.get_stats()['template_hits']==engine.get_stats()['glossary_hits']==0

def test_budget_cannot_fall_back_to_local_rules(tmp_path):
    with TranslationEngine({'api_key':'synthetic','max_requests':0},tmp_path/'book.sqlite3') as engine:
        engine.set_term('G','en','zh-CN','Hello','\u4f60\u597d')
        with pytest.raises(BudgetExceeded):engine.translate('G','en','zh-CN','Hello')
        assert engine.get_stats()['api_calls']==0
