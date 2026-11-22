# SPDX-License-Identifier: MIT
import json
import httpx
import pytest
from PIL import Image
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.vision import ScreenshotRecognizer,parse_chat_layout
from nkc_galgame_translator.api_providers import chat_options,provider_for


@pytest.mark.parametrize('base,model', [('https://api.deepseek.com','deepseek-flash'),
                                        ('https://api.openai.com/v1','gpt-4.1-mini'),
                                        ('https://provider.example/chat/v1','vision-demo')])
def test_current_slot_receives_one_image_and_returns_scaled_geometry(tmp_path,base,model):
    def handle(request):
        assert str(request.url)==base+'/chat/completions'
        assert request.headers['Authorization']=='Bearer synthetic-backend-test'
        payload=json.loads(request.content)
        assert payload['model']==model
        assert ('thinking' in payload)==(model=='deepseek-flash')
        assert payload['messages'][1]['content'][0]['image_url']['url'].startswith('data:image/png;base64,iVBOR')
        content=json.dumps({'lines':[{'text':'LOG','box':[100,200,450,700]}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        engine=TranslationEngine(dict(api_key='synthetic-backend-test',base_url=base,model=model),tmp_path/'test.db',client=client)
        try:
            rows=ScreenshotRecognizer(engine).recognize_frame(Image.new('RGB',(200,100)),cancelled=lambda:False)
            assert rows==[dict(text='LOG',x=20,y=20,w=70,h=50)]
            assert engine.get_stats()['session_requests']==1
        finally:
            engine.close()


@pytest.mark.parametrize('box',([0,0,1100,200],[0,0,0,20],[True,0,10,10]))
def test_bad_backend_boxes_cannot_be_drawn(box):
    choice={'finish_reason':'stop','message':{'content':json.dumps({'lines':[{'text':'x','box':box}]})}}
    with pytest.raises(ValueError):parse_chat_layout({'choices':[choice]},(100,100))


def test_presets_and_model_parameters():
    assert provider_for('https://api.deepseek.com.evil.example/v1')=='custom'
    payload={'model':'gpt-5','max_tokens':100,'temperature':0,'thinking':{'type':'disabled'}}
    assert chat_options(payload,'https://api.openai.com/v1')=={'model':'gpt-5','max_completion_tokens':100}


def test_rental_flyer_full_single_and_screen_paths(tmp_path):
    engine=TranslationEngine({'offline_only':True},tmp_path/'test.db')
    try:
        game='AoiChan.exe'
        ad='“\u683c\u5b89!\u99c5\u30c1\u30ab!\u6577\u91d1\u793c\u91d1\u306a\u3057!\u5373\u5165\u5c45\u53ef\u80fd!'
        assert engine.translate('game','ja','zh-Hans',ad,game_executable=game)=='\u79df\u91d1\u7279\u60e0\uff01\u90bb\u8fd1\u8f66\u7ad9\uff01\u514d\u62bc\u91d1\u3001\u514d\u793c\u91d1\uff01\u53ef\u7acb\u5373\u5165\u4f4f\uff01'
        rows=[dict(source_lang='ja',text='\u6577\u91d1\u793c\u91d1\u306a\u3057\uff01'),dict(source_lang='en',text='SETTINGS')]
        assert engine.translate_screen('game','ja','zh-Hant',rows,'','Aoichan',game)==['\u514d\u62bc\u91d1\u3001\u514d\u79ae\u91d1\uff01','\u8a2d\u5b9a']
        assert engine._game_label(('game','ja','zh-Hans'),ad,'Another.exe') is None
        second = '……\u76ee\u306b\u6b62\u307e\u3063\u305f\u306e\u306f\u305d\u3093\u306a\u5e83\u544a\u3002\u3002\u3002'
        flyer = ad + '\u3000\u30b7\u30a7\u30a2\u30cf\u30a6\u30b9\uff01 ”'
        assert engine.translate('game','ja','zh-Hans',flyer+'\n\n'+second,game_executable=game).splitlines() == [
            '\u79df\u91d1\u7279\u60e0\uff01\u90bb\u8fd1\u8f66\u7ad9\uff01\u514d\u62bc\u91d1\u3001\u514d\u793c\u91d1\uff01\u53ef\u7acb\u5373\u5165\u4f4f\uff01\u5408\u79df\u623f\uff01','……\u8fd9\u5219\u79df\u623f\u5e7f\u544a\u5438\u5f15\u4e86\u6211\u7684\u76ee\u5149\u3002']
        name = '\u300e\u58ee"……\u78ba\u304b\u306b\u7537\u6027\u3068\u3044\u3063\u3066\u3082\u901a\u3058\u308b\u540d\u524d\u3067\u306f\u3042\u308b\u3002'
        assert '“\u8475”' in engine.translate('game','ja','zh-Hans',name,game_executable=game)
        assert engine._game_label(('game','ja','zh-Hans'),name,'Another.exe') is None
    finally:
        engine.close()
