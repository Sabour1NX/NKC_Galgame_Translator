import json
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.context_archive import scope_key

def test_page_batch_budget_and_isolation(tmp_path):
    config=dict(api_key='dummy-synthetic-for-test',model='test',context_web_search=False,active_scene_summary=False)
    calls=[];published=[]
    with TranslationEngine(config,tmp_path/'test.db') as engine:
        def fake(scope,masked,ctx,callback,*,page_blocks):
            calls.append((page_blocks,ctx))
            answer=json.dumps({k:'\u8bd1\u6587'+k for k in page_blocks},ensure_ascii=False)
            callback(answer[:-2]);callback(answer)
            return answer
        engine._request=fake
        def page(strings):
            return engine.translate_screen('game','ja','zh-Hans',[dict(source_lang='ja',text=s) for s in strings],
                '\u624b\u5199\u5907\u6ce8',None,'game.exe',on_block=lambda i,t:published.append((i,t)))
        assert page(['\u805e\u3044\u3066\u3044\u307e\u3059','\u4eca\u65e5\u306f\u5143\u6c17\u3067\u3059'])==['\u8bd1\u65870','\u8bd1\u65871']
        assert len(calls)==1 and published==[(0,'\u8bd1\u65870'),(1,'\u8bd1\u65871')]
        assert page(['\u9577\u3044\u6587\u7ae0'*500]*5) is None and len(calls)==1
        assert page(['\u5225\u306e\u753b\u9762\u3067\u3059','\u6b21\u3078\u9032\u307f\u307e\u3059'])==['\u8bd1\u65870','\u8bd1\u65871']
        assert '\u805e\u3044\u3066\u3044\u307e\u3059' not in calls[-1][1]
        engine.save_profile('game',notes='\u624b\u5199\u5907\u6ce8',source_lang='ja',target_lang='zh-Hans')
        with engine._db:engine.context_archive.store_summary(scope_key(('game','ja','zh-Hans')),20,'\u89d2\u8272\u6b63\u5728\u804a\u5929')
        record=engine.get_profile('game')
        assert record['notes']=='\u624b\u5199\u5907\u6ce8' and record['summary_note']=='\u89d2\u8272\u6b63\u5728\u804a\u5929'
