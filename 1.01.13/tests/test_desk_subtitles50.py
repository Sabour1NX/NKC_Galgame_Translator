# SPDX-License-Identifier: MIT
from threading import Event
from types import SimpleNamespace
from PIL import Image, ImageDraw
from nkc_galgame_translator.aoi_dialogue import (MINT_SAVE_CAPTION, candidates, erase_advance_markers,
                                    repair_ocr_rows, superseded_boxes)
from nkc_galgame_translator.live_capture import LiveCapture, follow_source, replaces_reading
from nkc_galgame_translator.pipeline import _quality_lines
from test_scroll29 import SyntheticNative
from test_pipeline import wait_until


def row(y, width, text):
    return dict(text=text,x=14,y=y-4,w=width+8,h=30,_source_ink=[18,y,width,22],
                fg=[255]*3,bg=[80,120,155],_subtitle_read=True,confidence=94)


def test_scene_highlight_and_arrow_do_not_join_two_baselines():
    image=Image.new('RGB',(540,125),(80,120,155))
    draw=ImageDraw.Draw(image)
    draw.line((2,0,2,124),fill='white',width=3)
    for y in (38,71):
        for x in range(28,354,18):
            draw.line((x,y,x+8,y+18),fill=(64,64,64),width=7)
            draw.line((x,y,x+8,y+18),fill='white',width=3)
    draw.polygon(((378,87),(386,91),(378,95)),fill=(195,210,225))
    located=[bounds for bounds,*_ in candidates(image)]
    assert any(25<=x<=31 and 36<=y<=39 and w>320 and h<=23 for x,y,w,h in located)
    assert any(25<=x<=31 and 69<=y<=72 and w>320 and h<=23 for x,y,w,h in located)


def test_blinking_double_arrow_does_not_change_subtitle_bounds_or_punctuation():
    with Image.new('RGB',(560,120),(80,120,155)) as plain:
        draw=ImageDraw.Draw(plain)
        for x in range(26,384,18):
            draw.line((x,50,x+8,70),fill=(64,64,64),width=7)
            draw.line((x,50,x+8,70),fill='white',width=3)
        with plain.copy() as blinking:
            draw=ImageDraw.Draw(blinking)
            for x in (387,398):
                draw.polygon(((x,65),(x+9,71),(x,77)),fill='white')
            measured = [{bounds for bounds,*_ in candidates(frame)} for frame in (plain,blinking)]
            assert measured[0] == measured[1]
            assert measured[0] and max(x+w for x,y,w,h in measured[0])<387
            rough=dict(text='\u672c\u5f53\u306b\uff1f\u3002',x=20,y=49,w=393,h=31,fg=[255]*3,bg=[80,120,155])
            clean = repair_ocr_rows(plain,[rough])
            assert clean == repair_ocr_rows(blinking,[rough])
            assert clean[0]['text']=='\u672c\u5f53\u306b\uff1f'
            assert follow_source(plain,blinking,clean)==clean


def test_touching_dim_arrow_is_erased_before_live_ocr_and_cannot_trigger_another_read():
    with Image.new('RGB',(560,124),(80,120,155)) as plain, plain.copy() as lit:
        for frame in (plain,lit):
            draw=ImageDraw.Draw(frame)
            for x in range(30,355,20):
                draw.line((x,32,x+7,57),fill='white',width=3)
        draw=ImageDraw.Draw(lit)
        for x in (372,383):
            draw.polygon(((x,50),(x+11,56),(x,62)),fill=(171,186,197))
        with erase_advance_markers(lit) as cleaned:
            assert cleaned is not lit
            assert cleaned.tobytes()==plain.tobytes()
            assert lit.getpixel((372,56))==(171,186,197)
        native=SyntheticNative(lit)
        calls=[]
        def read(image,language):
            calls.append(image.tobytes())
            return {'lines':[row(32,335,'\u305d\u306e\u5148\u3078\u9032\u307f\u307e\u3059\u3002')],'ocr_ms':1}
        live=LiveCapture(SimpleNamespace(native=native,_aoi=True,_capture_regions=(),
                                         mode='native',recognize_image=read))
        try:
            def capture():
                return live.capture(0,0,560,124,'ja')
            wait_until(lambda:bool(capture()['lines']))
            assert calls==[plain.tobytes()]
            revision=live.revision
            for frame in (plain,lit,plain,lit):
                native.image=frame
                assert not capture()['changed']
            assert live.revision==revision and len(calls)==1
        finally:
            live.close()


def test_mint_autosave_subtitle_keeps_its_ink_color_and_one_owner():
    with Image.new('RGB',(700,150),(52,81,105)) as frame:
        draw=ImageDraw.Draw(frame)
        for x in range(38,520,22):
            draw.line((x,76,x+7,100),fill=(127,255,212),width=5)
        first={**row(40,505,'\u3053\u306e\u30b2\u30fc\u30e0\u306f\u30aa\u30fc\u30c8\u30bb\u30fc\u30d6\u3068\u306a\u3063\u3066\u304a\u308a\u307e\u3059\u3002'),'x':26}
        raw=dict(text=MINT_SAVE_CAPTION,x=28,y=70,w=510,h=36,fg=[245]*3,bg=[52,81,105],confidence=98)
        measured,=repair_ocr_rows(frame,[raw])
        assert measured['fg']==[127,255,212] and measured['_subtitle_read']
        x,_,w,_=measured['_source_ink']
        assert measured['x']+measured['w']<=x+w+3
        rough={**raw,'text':'\u5c31\u5bdd\u3059\u308b\u3068\u9032\u884c\u72b6\u6cc1\u3092\u4fdd\u5b58\u3057\u307e\u3059\u3002'}
        assert [entry['text'] for entry in _quality_lines([rough,first,measured],'ja',(0,0),True,'Aoichan.exe')]==[
            first['text'],MINT_SAVE_CAPTION]


def test_replace_spanning_observation_only_after_both_lines_are_verified():
    a,b=row(20,180,'\u4e00\u884c\u76ee\u3002'),row(52,230,'\u4e8c\u884c\u76ee\u3002')
    wide=dict(text='rough OCR',x=15,y=19,w=235,h=58)
    third={**wide,'h':91}
    assert superseded_boxes([wide,third],[a,b])==[third]
    assert superseded_boxes([wide],[a,a])==[wide]
    assert superseded_boxes([wide],[a,{**b,'_selection_id':1}])==[wide]
    assert replaces_reading({**a,'_subtitle_read':False,'text':'earlier noisy, longer reading'},a)


def test_appended_line_enters_preview_with_first_line_visible(monkeypatch):
    a,b=row(20,100,'\u4e00\u884c\u76ee\u3067\u3059\u3002'),row(68,153,'\u4e8c\u884c\u76ee\u3067\u3059\u3002')
    screen=Image.new('RGB',(300,150),(80,120,155));native=SyntheticNative(screen)
    release=Event();preview_seen=Event();skipped=[]
    def preview(source,rows,reader,minimum,*,limit,skip_ink):
        skipped.extend(skip_ink)
        preview_seen.set()
        return [b]
    def slow_read(*args):
        release.wait(4)
        return {'lines':[a,b]}
    monkeypatch.setattr('nkc_galgame_translator.aoi_dialogue.recover',preview)
    core=SimpleNamespace(native=native,_aoi=True,mode='auto',min_confidence=55,_capture_regions=(),
                         _page_reader=SimpleNamespace(available=lambda:True),recognize_image=slow_read)
    live=LiveCapture(core)
    try:
        native.capture_bgra(0,0,*screen.size)
        live.origin=(0,0,*screen.size,'ja')
        live.frame=screen.copy();live.lines=[a]
        native.image=screen.copy()
        ImageDraw.Draw(native.image).rectangle((20,68,170,85),fill='white')
        capture=lambda:live.capture(0,0,*screen.size,'ja')
        seen=[]
        def collect():
            seen.extend(r['text'] for r in capture().get('lines',[]))
            return set(seen)=={a['text'],b['text']}
        collect()
        assert preview_seen.wait(1)
        wait_until(collect)
        assert skipped==[tuple(a['_source_ink'])]
    finally:
        release.set();live.close()
