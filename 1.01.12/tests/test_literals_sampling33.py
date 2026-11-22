# SPDX-License-Identifier: MIT
import json
import re
from statistics import median
from time import monotonic

import httpx
import pytest

from nkc_galgame_translator.literal_rules import literal_ranges, only_literals, redact_credentials
from nkc_galgame_translator.pipeline import _quality_lines
from nkc_galgame_translator.selection_regions import limit_two_layers
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.tracking import ObjectTracker
from nkc_galgame_translator.tuning import validate_tuning
from test_pipeline import make_pipeline, start, wait_until
from test_translation import sse_response


def test_standalone_name_and_labeled_password_require_no_model(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('protected rows must stay local'))) as client:
        with TranslationEngine({'api_key':'synthetic'},tmp_path/'literal.sqlite3',client=client) as engine:
            assert engine.translate('Test','en','zh-Hans','DirectX 12')=='DirectX 12'
    password='cafe\u0301-873!'
    rows=[dict(x=0,y=0,w=80,h=22,text='Password:'),
          dict(x=85,y=0,w=105,h=22,text=password),
          dict(x=0,y=70,w=90,h=22,text='START GAME')]
    result={row['text']:row for row in _quality_lines(rows,'en',(0,0),True)}
    assert result[password]['_ocr_rejection_reason']=='protected_literal'
    assert not result['START GAME'].get('_preserve_source')
    assert not only_literals('START GAME') and not literal_ranges('Password is required.')


@pytest.mark.parametrize('damaged',[False,True])
def test_model_preserves_exact_password_spell_and_technical_name(tmp_path,damaged):
    password='cafe\u0301-873!'
    spell='\u300cNaru malek\u300d'
    text=f'Password: "{password}"; spell: {spell}; enable NVIDIA DLSS 3.5.'
    chunks=[]
    outgoing=[]
    def reply(request):
        decoded=json.loads(request.content)['messages']
        outgoing.append(decoded)
        row=json.loads(decoded[-1]['content'])
        tokens=re.findall(r'__GLT_[0-9a-f]+_\d{4}__',row['text'])
        assert all(secret not in str(decoded) for secret in (password,spell,'NVIDIA DLSS 3.5'))
        assert len(tokens)==3
        translated=f'\u5bc6\u7801\uff1a{tokens[0]}\uff1b\u5492\u8bed\uff1a{tokens[1]}\uff1b\u542f\u7528{tokens[2]}\u3002'
        return sse_response(translated if not damaged else translated.replace(tokens[0],'wrong'))
    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        with TranslationEngine({'api_key':'synthetic'},tmp_path/'literal.sqlite3',client=client) as engine:
            result=engine.translate('Test','en','zh-Hans',text,chunks.append)
            records=engine.list_translation_history('Test','en','zh-Hans')
    assert len(outgoing)==1 and len(chunks)==1
    if damaged:
        assert result==text and not records
    else:
        assert result==f'\u5bc6\u7801\uff1a"{password}"\uff1b\u5492\u8bed\uff1a{spell}\uff1b\u542f\u7528NVIDIA DLSS 3.5\u3002'
        assert records[0]['translation']==result
        assert password not in redact_credentials(result) and spell in redact_credentials(result)


def test_overlap_cap_checks_actual_triple_intersection():
    first=dict(x=0,y=0,w=10,h=10,text='a')
    second=dict(x=5,y=0,w=10,h=10,text='b')
    triple=dict(x=8,y=2,w=9,h=9,text='c')
    disjoint_intersections=dict(x=0,y=8,w=4,h=8,text='d')
    duplicate={**first,'x':1}
    result=limit_two_layers([first,second,triple,disjoint_intersections,duplicate])
    assert result==[first,second,disjoint_intersections]


def test_password_composition_change_revises_tracked_content_immediately():
    row=dict(x=4,y=6,w=120,h=20,text='Password: "Ae\u0301ther-823"')
    with ObjectTracker() as tracker:
        previous,=tracker.update([row]).tracks
        changed,=tracker.update([{**row,'text':'Password: "A\u00e9ther-823"'}]).tracks
        assert changed.track_id==previous.track_id and changed.revision==previous.revision+1


@pytest.mark.parametrize('mode',['off','auto','supersample'])
def test_supersampling_starts_before_motion_while_auto_waits(make_pipeline,mode):
    assert validate_tuning({'sampling_mode':mode})['sampling_mode']==mode
    pipe,core,_,_,region=make_pipeline(interval=.2,sampling_mode=mode)
    original=core.capture_ocr
    reads=[]
    def capture(*args,**kw):
        reads.append(monotonic())
        return {**original(*args,**kw),'pixel_motion':len(reads) in (3,4)}
    core.capture_ocr=capture
    start(pipe,region)
    wait_until(lambda:len(reads)>=6,timeout=3)
    intervals=[b-a for a,b in zip(reads,reads[1:6])]
    if mode=='supersample':
        assert median(intervals[:2])<.14
    else:
        assert intervals[0]>.15
    if mode=='auto':
        assert median(intervals[2:])<.14
    elif mode=='off':
        assert min(intervals)>.15

def test_touching_ocr_margins_do_not_suppress_chat_paragraph():
    top = dict(x=10, y=10, w=90, h=35)
    left = dict(top, text='\u7532', _source_ink=[15, 15, 45, 20])
    right = dict(top, text='\u4e59', _source_ink=[65, 15, 30, 20])
    lower = dict(x=10, y=40, w=100, h=65, text='\u304b\u306a\n\u3067\u3059',
                 _source_rows=[dict(ink_bounds=[5, 6, 70, 20]), dict(ink_bounds=[5, 38, 80, 20])])
    assert limit_two_layers([left, right, lower]) == [left, right, lower]
