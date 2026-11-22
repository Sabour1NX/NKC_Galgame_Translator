# SPDX-License-Identifier: MIT
from PIL import Image, ImageDraw
from nkc_galgame_translator.aoi_dialogue import candidates
from nkc_galgame_translator.live_capture import replaces_reading
from nkc_galgame_translator.translation import TranslationEngine


def test_two_inks_on_textured_background_have_separate_baselines():
    im=Image.new('RGB',(600,130),(60,78,110))
    pen=ImageDraw.Draw(im)
    for x in range(0,600,24):
        pen.line((x,0,x,129),fill=(65,85,120))
    for i in range(14):
        for y,color in ((44,'white'),(86,(130,245,200))):
            x=80+i*19
            pen.line((x,y,x+10,y+20),fill=color,width=3)
    found=list(candidates(im))
    assert len(found)==2
    assert found[0][0][1]<found[1][0][1]
    assert found[0][2]!=found[1][2]


def test_full_frame_fragment_cannot_displace_complete_cursor_subtitle():
    old=dict(x=15,y=45,w=360,h=35,text='\u305d\u306e\u8f9e\u4ee4\u306f\u5510\u7a81\u3060\u3063\u305f\u3002',_attention_inferred=True)
    assert not replaces_reading(old,dict(x=210,y=46,w=175,h=35,text='\u5510\u7a81\u3060\u3063\u305f'))
    whole={**old,'_subtitle_read':True}
    assert replaces_reading(old,whole)
    assert not replaces_reading(old,{**whole,'_selection_id':1})


def test_sleep_help_is_scoped_to_the_game_and_target_language():
    engine=object.__new__(TranslationEngine)
    text='\u5c31\u5bdd\u6642\u306b\u9032\u884c\u72b6\u6cc1\u304c\u81ea\u52d5\u7684\u306b\u4fdd\u5b58\u3055\u308c\u307e\u3059\u3002'
    assert engine._game_label(('game','ja','zh-Hans'),text,'AoiChan.exe')=='\u5c31\u5bdd\u65f6\u4f1a\u81ea\u52a8\u4fdd\u5b58\u6e38\u620f\u8fdb\u5ea6\u3002'
    assert engine._game_label(('game','ja','en'),text,'AoiChan.exe') is None
    assert engine._game_label(('game','ja','zh-Hans'),text,'other.exe') is None


def test_negative_save_message_keeps_its_meaning(monkeypatch):
    from nkc_galgame_translator import aoi_dialogue
    from types import SimpleNamespace
    sentence='\u5c31\u5bdd\u6642\u306b\u9032\u884c\u72b6\u6cc1\u304c\u81ea\u52d5\u7684\u306b\u4fdd\u5b58\u3055\u308c\u307e\u305b\u3093\u3002'
    engine=SimpleNamespace(available=lambda:True,recognize=lambda *_:{
        'lines':[{'text':sentence,'confidence':95}]})
    ink=Image.new('L',(100,26),255)
    monkeypatch.setattr(aoi_dialogue,'candidates',lambda _: [((2,2,100,26),ink,[255]*3,[40]*3)])
    result=aoi_dialogue.recover(Image.new('RGB',(110,40)),[],engine,55)
    assert result[0]['text']==sentence
