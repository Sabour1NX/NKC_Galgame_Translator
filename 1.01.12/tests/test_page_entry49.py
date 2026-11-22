# SPDX-License-Identifier: MIT
import threading
from types import SimpleNamespace

from PIL import Image
from nkc_galgame_translator.aoi_menu import TRANSLATIONS
from nkc_galgame_translator.aoi_dialogue import OPENING_PROMPT
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.live_capture import LiveCapture
from nkc_galgame_translator.pipeline import Pipeline
from test_pipeline import FakeCore, FakeEngine, Recorder, finals, wait_until
from test_scroll29 import SyntheticNative


def test_verified_title_labels_bypass_settle_and_busy_translator():
    words=list(TRANSLATIONS)
    engine=FakeEngine()
    events=Recorder()
    rows=[dict(text=word,x=100,y=40+45*i,w=160,h=32,confidence=100,fg=[255]*3,
               bg=[85,103,139],_source_ink=[115,44+45*i,130,23],_layout_cell=True,
               _center_label=True,_aoi_button=i) for i,word in enumerate(words)]
    core=FakeCore(rows)
    pipe=Pipeline(core,engine,events,interval=.02,settle=30,translation_workers=1,
                  game_executable='AoiChan.exe',persist_results=True,show_source_label=False,
                  show_translation_brackets=False)
    blocked=threading.Event()
    try:
        job=pipe.pool.submit(blocked.wait,5)
        pipe._inflight[job]=('old-page',)
        pipe.start(lambda:(0,0,640,480),'Aoichan','ja','zh-Hans')
        wait_until(lambda:len(finals(events))==5)
        assert not engine.calls
        assert [event[2][1]['text'] for event in finals(events)]==[TRANSLATIONS[w][0] for w in words]
    finally:
        blocked.set();pipe.stop();pipe.join(3)


def test_rental_flyer_remains_translated_when_following_line_appears():
    ad='“\u683c\u5b89\uff01\u5373\u5165\u5c45\u53ef\u80fd\uff01\u30b7\u30a7\u30a2\u30cf\u30a6\u30b9\uff01”'
    narration='……\u76ee\u306b\u6b62\u307e\u3063\u305f\u306e\u306f\u305d\u3093\u306a\u5e83\u544a\u3002'
    first=dict(text=ad,x=24,y=50,w=453,h=30,confidence=98,fg=[255]*3,bg=[54,84,108])
    next_row=dict(first,text=narration,y=86,w=280)
    core=FakeCore([first])
    engine=FakeEngine()
    events=Recorder()
    pipe=Pipeline(core,engine,events,interval=.02,settle=0,translation_workers=1,
                  game_executable='Aoichan.exe',persist_results=True,
                  show_source_label=False,show_translation_brackets=False)
    try:
        pipe.start(lambda:(0,0,640,480),'Aoichan','ja','zh-Hans')
        wait_until(lambda:len(finals(events))==1)
        assert finals(events)[0][2][1]['text']=='\u79df\u91d1\u7279\u60e0\uff01\u53ef\u7acb\u5373\u5165\u4f4f\uff01\u5408\u79df\u623f\uff01'
        core.set_scene([first,next_row])
        wait_until(lambda:len(finals(events))==2)
        frame = [payload for kind,_,payload in events.snapshot() if kind=='objects'][-1]
        assert {item['line']['text'] for item in frame}=={ad,narration}
        assert finals(events)[1][2][1]['text']=='……\u8fd9\u5219\u79df\u623f\u5e7f\u544a\u5438\u5f15\u4e86\u6211\u7684\u76ee\u5149\u3002'
        assert not engine.calls
    finally:
        pipe.stop()
        pipe.join(3)


def test_opening_prompt_keeps_one_translation_and_layout_across_ocr_phases():
    line=dict(text=OPENING_PROMPT,x=34,y=100,w=580,h=38,confidence=98,fg=[255]*3,bg=[54,84,108],
              _source_ink=[39,104,567,27],_scroll_clip=(0,0,800,350))
    blink={**line,'text':'>\u30aa\u30fc\u30d7\u30cb\u30f3\u30b0\u3092\u30b9\u30ad\u30c3\u30d7\u3057\u307e\u3059\u304b?\u300d','x':31,'y':96,'w':612,'h':46,
           '_source_ink':[36,100,599,34]}
    fragment={**blink,'text':'\u30aa\u30fc\u30d7\u30cb\u30f3\u30b0\u3092\u30b9','w':95}
    core=FakeCore([line])
    events,engine=Recorder(),FakeEngine()
    overlay=OverlayState()
    pipe=Pipeline(core,engine,events,interval=.012,settle=0,persist_results=True,
                  game_executable='Aoichan.exe',show_source_label=False,show_translation_brackets=False)
    try:
        pipe.start(lambda:(0,0,800,350),'Aoichan','ja','zh-Hans')
        wait_until(lambda:len(finals(events))==1)
        initial=len(events.snapshot())
        core.set_scene([blink,fragment])
        wait_until(lambda:len([e for e in events.snapshot()[initial:] if e[0]=='objects'])>=3)
        for kind,_,payload in events.snapshot():
            if kind=='objects':
                overlay.apply_objects(payload)
            elif kind=='translation':
                overlay.apply_translation(payload[0],payload[1])
        assert len(finals(events))==1 and not engine.calls
        result,=overlay.display_regions()
        assert result['text']=='\u8981\u8df3\u8fc7\u5f00\u573a\u5417\uff1f'
        assert result['_source_ink']==line['_source_ink']
        assert [result[key] for key in ('x','y','w','h')]==[line[key] for key in ('x','y','w','h')]
        # Permit actual resize immediately for the same caption.
        item,=overlay.objects.values()
        observed={**item,'line':{**item['line'],'x':64,'w':620,'_scroll_clip':(0,0,900,400)}}
        overlay.apply_objects([observed])
        assert overlay.display_regions()[0]['w']==620
    finally:
        pipe.stop();pipe.join(3)


def test_page_preview_discards_previous_scene_even_when_full_ocr_is_busy(monkeypatch):
    first=Image.new('RGB',(320,200),(30,45,75))
    next_page=Image.new('RGB',first.size,(220,210,190))
    native=SyntheticNative(first)
    started=threading.Event();release=threading.Event();full=threading.Event()
    def preview(image,*args,**kwargs):
        started.set();release.wait(3)
        row=dict(text='\u65e5\u672c\u8a9e\u306e\u8aac\u660e',x=10,y=10,w=140,h=25,fg=[255]*3,bg=[30,45,75])
        return [row] if image.getpixel((0,0))==(30,45,75) else []
    monkeypatch.setattr('nkc_galgame_translator.aoi_dialogue.recover',preview)
    def full_read(*args):
        full.wait(3);return dict(lines=[],ocr_ms=0)
    core=SimpleNamespace(native=native,_capture_regions=(),_aoi=True,mode='auto',
                         _page_reader=SimpleNamespace(available=lambda:True),min_confidence=55,
                         recognize_image=full_read)
    live=LiveCapture(core)
    try:
        live.capture(0,0,*first.size,'ja')
        assert started.wait(1)
        native.image=next_page
        assert live.capture(0,0,*first.size,'ja')['scene_cut']
        release.set()
        wait_until(lambda:live._page[-1].done())
        assert not live.capture(0,0,*first.size,'ja')['lines']
    finally:
        full.set();release.set();live.close()
