# SPDX-License-Identifier: MIT
from PIL import Image
from nkc_galgame_translator.live_capture import superseded_fragments, merge_cloud_rows
from nkc_galgame_translator.windose_warning import SOURCE, WarningGeometry, recover, verified


def line(x,y,w,h,text):
    return dict(x=x,y=y,w=w,h=h,text=text)


def test_partial_or_blank_pixels_cannot_authorize_game_localization():
    rows=[line(10,10,220,18,'\u73fe\u4ee3\u65e5\u672c'),line(10,66,400,18,'\u66b4\u529b\u7684\u3060\u3063\u305f\u308a\u3001')]
    with Image.new('RGB',(500,150),'#fff8ff') as empty:
        assert recover(empty,rows)==rows
    assert not verified({'_windose_geometry':{'rows':[[1,1,5,8]]}})


def test_local_complete_row_replaces_previous_parts_but_keeps_other_selections():
    whole=dict(line(9,40,500,44,SOURCE),_windose_geometry=WarningGeometry(((1,1,495,17),(1,25,24,17))))
    part=line(200,40,200,18,'\u7cbe\u795e\u306b\u8ca0\u8377')
    neighbor=line(10,95,300,18,'\u96a3\u306e\u672c\u6587')
    foreign=dict(part,_selection_id=1)
    assert superseded_fragments([whole,part,neighbor,foreign],[whole])==[neighbor,foreign]
    assert merge_cloud_rows([whole],[dict(whole,text='\u65ad\u7247',_windose_geometry=None)])[0]['text']==SOURCE
