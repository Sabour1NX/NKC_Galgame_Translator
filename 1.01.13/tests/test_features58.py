# SPDX-License-Identifier: MIT
import csv
import json
import time
from pathlib import Path

from PIL import Image
import pytest

from nkc_galgame_translator.localization_export import Exporter, Line, export_preferences
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.themes import palette, validate_theme


@pytest.mark.parametrize('format_',('txt','json','csv'))
def test_export_waits_selects_best_and_creates_distinct_game_sessions(tmp_path,format_):
    errors=[]
    writer=Exporter(tmp_path,format_,1,lambda: errors.append(True))
    def page(session,text,score):
        writer.offer(session,'Game:/Test',[Line(1,'Welcome to the station.',text,'zh-Hans',score)],
                     Image.new('RGB',(60,30)))
    page(1,'\u6b22\u8fce\u6765\u5230\u8f66\u7ad9\u3002',(0,60))
    page(1,'\u6b22\u8fce\u62b5\u8fbe\u8f66\u7ad9\u3002',(1,90))
    assert not list(tmp_path.iterdir())
    deadline=time.monotonic()+4
    while not list(tmp_path.glob(f'*.{format_}')) and time.monotonic()<deadline:
        time.sleep(.04)
    page(2,'\u6b22\u8fce\u62b5\u8fbe\u8f66\u7ad9\u3002',(1,90))
    writer.close()
    assert not errors
    docs=sorted(tmp_path.glob(f'*.{format_}'),key=lambda p:p.stat().st_mtime_ns)
    assert len(docs)==2 and len(list(tmp_path.glob('*.png')))==2
    body=docs[0].read_text('utf-8-sig')
    assert '\u6b22\u8fce\u62b5\u8fbe\u8f66\u7ad9\u3002' in body and '\u6b22\u8fce\u6765\u5230\u8f66\u7ad9\u3002' not in body
    if format_=='txt':
        assert body.startswith('[') and '\n\u539f\u6587\uff1a\nWelcome to the station.\n\n\u7ffb\u8bd1:\n' in body
        assert '\u4e0b\u4e00\u53e5' not in body
    elif format_=='json':
        assert (tmp_path/json.loads(body)[0]['screenshot']).is_file()
    else:
        rows=list(csv.reader(body.splitlines()))
        assert rows[0]==['\u65f6\u95f4\u6233','\u539f\u6587','\u7ffb\u8bd1','\u622a\u56fe'] and (tmp_path/rows[1][3]).is_file()


def test_only_complete_pages_expose_raw_export_text():
    state=OverlayState()
    row=dict(track_id=1,revision=1,line=dict(text='Hello',x=10,y=10,w=80,h=20))
    state.apply_objects([row])
    state.apply_translation(1,dict(text='[\u4f60',_revision=1,final=False))
    assert state.completed_page() is None
    state.apply_translation(1,dict(text='[\u4f60\u597d]',_revision=1,final=True,_raw_translation='\u4f60\u597d'))
    assert state.completed_page()[0][2]['_raw_translation']=='\u4f60\u597d'
    state.apply_objects([row,{**row,'track_id':2}])
    assert state.completed_page() is None


def test_theme_and_export_settings():
    assert palette({'interface_theme':'neon'})[0]=='#18112E'
    choices={'paper':'#111111','surface':'#212121','ink':'#FFFFFF','accent':'#AbCd00'}
    assert validate_theme(dict(interface_theme='custom',interface_colors=choices))['interface_colors']['accent']=='#ABCD00'
    for invalid in ('red','#fff','#0000000'):
        with pytest.raises(ValueError):
            validate_theme(dict(interface_theme='custom',interface_colors={**choices,'accent':invalid}))
    prefs=export_preferences({})
    assert not prefs['localization_enabled'] and prefs['localization_wait']==15

