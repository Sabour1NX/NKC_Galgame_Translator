from PIL import Image,ImageDraw
import pytest
from nkc_galgame_translator.palette_rows import find_rows,normalized_row,merge_readings
from nkc_galgame_translator.translation import TranslationEngine


def test_physical_caption_detection_separates_neighboring_colors():
    with Image.new('RGB',(280,100),(239,225,250)) as frame:
        draw=ImageDraw.Draw(frame)
        for x,color in [(29,(68,37,207)),(153,(183,66,62))]:
            for offset in range(0,43,7):
                draw.line((x+offset,39,x+offset,51),fill=color,width=2)
                draw.line((x+offset,39,x+offset+4,39),fill=color,width=2)
        rows=find_rows(frame)
        for x,fg in [(29,(68,37,207)),(153,(183,66,62))]:
            row=next(r for r in rows if r[0]==x and r[1]==39)
            assert row[4:]==((239,225,250),fg)
            with normalized_row(frame,row) as ink:
                assert ink.getextrema()==(0,255)


def test_two_labels_replace_fused_menu_without_removing_neighbor():
    def row(x,w,text):
        return dict(x=x,y=10,w=w,h=14,text=text,confidence=84)
    adjacent=row(276,31,'\u5225')
    result=merge_readings([row(0,235,'\u4ea4\u6d41\u89aa\u71b1'),adjacent],[row(0,113,'\u4ea4\u6d41'),row(141,94,'\u89aa\u71b1')])
    assert [r['text'] for r in result]==['\u4ea4\u6d41','\u89aa\u71b1','\u5225']


@pytest.mark.parametrize('target,expected',[('zh-Hans','\u4eb2\u70ed'),('zh-Hant','\u89aa\u71b1')])
def test_bed_action_is_scoped_to_windose(tmp_path,target,expected):
    with TranslationEngine({'offline_only':True},tmp_path/'book.sqlite3') as engine:
        emitted=[]
        assert engine.translate('profile','ja',target,'\u3048\u3063\u3061\u306a\u3053\u3068',emitted.append,game_executable='Windose.exe')==expected
        assert emitted==[expected]
        assert engine.get_stats()['session_requests']==0


def test_short_fragments_do_not_replace_a_complete_physical_row():
    row=dict(x=18,y=12,w=410,h=22,text='\u8ff7\u3063\u305f\u3089\u3001\u6b21\u306e\u6307\u793a\u3092\u9078\u3093\u3067\u307f\u308b\u3068\u826f\u3044\u304b\u3082\uff01',confidence=92)
    a={**row,'w':62,'text':'\u8ff7\u3063\u305f\u3089'}
    b={**row,'x':134,'w':70,'text':'\u6307\u793a\u3092'}
    assert merge_readings([row],[a,b])==[row]


def test_physical_caption_detection_keeps_wide_rows():
    bg=(239,207,239);fg=(79,28,207)
    with Image.new('RGB',(980,96),bg) as frame:
        draw=ImageDraw.Draw(frame)
        for x in range(28,871,21):
            draw.rectangle((x,29,x+4,47),fill=fg)
            draw.rectangle((x+5,33,x+10,43),fill=fg)
        assert any(x==28 and right>860 for x,y,right,bottom,*_ in find_rows(frame))


def test_windose_medicine_label_does_not_require_a_cloud_call(tmp_path):
    with TranslationEngine({'offline_only':True},tmp_path/'book.sqlite3') as engine:
        for reading in ('\u304a\u304f\u3059\u308a','B<\u8e6d','B\u304f\u78e8'):
            assert engine.translate('demo','ja','zh-Hans',reading,game_executable='Windose.exe')=='\u836f\u54c1'
        assert engine.get_stats()['session_requests']==0
