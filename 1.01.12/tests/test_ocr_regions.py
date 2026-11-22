# SPDX-License-Identifier: MIT
"""Whole-frame before regional work, bounded threads, actual pixel geometry."""
import importlib.util
import json
from pathlib import Path
from copy import deepcopy
import threading
import time

from PIL import Image, ImageDraw
import pytest

from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.ocr_regions import RegionRefiner, refine_ink, has_visual_separator
from nkc_galgame_translator.layout import merge_dialogue_lines

SPEC=importlib.util.spec_from_file_location('whole_frame_helper',Path(__file__).resolve().parents[1]/'tools/ocr_helper.py')
HELPER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(HELPER)


def row(text='This is a complete sentence',x=10,y=10,w=250,h=24,**extra):
    return dict(text=text,x=x,y=y,w=w,h=h,bg=[0,0,0],fg=[255,255,255],**extra)


@pytest.mark.parametrize('workers',[0,9,True,2.5,'2',None])
def test_invalid_workers_fail_before_starting_native_or_threads(workers):
    with pytest.raises(ValueError):RegionRefiner(workers)
    with pytest.raises(ValueError):OcrCore(refine_workers=workers)


def test_parallel_pixel_reads_have_private_engines_and_keep_input_order(monkeypatch):
    barrier=threading.Barrier(2);seen=[];ended=[]
    class Engine:
        def __init__(self,**_):self.owner=threading.get_ident()
        def End(self):ended.append(self.owner)
    class Tess:
        PyTessBaseAPI=Engine
        class PSM:SINGLE_LINE=7
        class OEM:LSTM_ONLY=1
    def read(engine,tess,image,line):
        assert engine.owner==threading.get_ident()
        seen.append(engine.owner);barrier.wait(timeout=3)
        if line['text']=='first':time.sleep(.02)
        return {**line,'text':line['text']+' read'}
    monkeypatch.setattr(HELPER,'refine_pixel_line',read)
    refiner=HELPER.RegionalRefiner(Tess,2)
    source=[dict(text=text,x=10,y=10+i*30,w=80,h=24,confidence=60) for i,text in enumerate(['first','second'])]
    before=deepcopy(source)
    try:
        output=refiner.refine(Image.new('RGB',(200,100)),source,'eng')
    finally:refiner.close()
    assert [item['text'] for item in output]==['first read','second read']
    assert source==before and len(set(seen))==2 and sorted(ended)==sorted(seen)
    assert [(p['x'],p['y'],p['w'],p['h']) for p in output]==[(p['x'],p['y'],p['w'],p['h']) for p in source]


def test_full_frame_discovery_precedes_refinement_and_supplement_cannot_duplicate(monkeypatch):
    calls=[]
    class Tess:
        class PSM:AUTO=3;SPARSE_TEXT=11
    class Engine:
        def SetImageBytes(self,data,w,h,*_):calls.append(('frame',w,h))
        def SetPageSegMode(self,mode):calls.append(('mode',mode))
        def Recognize(self):calls.append(('read',))
    primary=[dict(text='Original complete row',x=10,y=10,w=250,h=24,confidence=85)]
    supplemental=[dict(text='Would duplicate',x=12,y=10,w=240,h=24,confidence=96),
                  dict(text='A newly discovered row',x=10,y=60,w=250,h=24,confidence=90)]
    results=iter([primary,supplemental])
    monkeypatch.setattr(HELPER,'read_lines',lambda *_:next(results))
    class Refiner:
        def refine(self,image,lines,language):
            assert calls==[('frame',400,160),('mode',3),('read',),('mode',11),('read',)]
            assert image.size==(400,160)
            return lines
    result=HELPER.recognize(Engine(),Tess,Image.new('RGB',(400,160),'white'),'eng','pixel',Refiner())
    assert [line['text'] for line in result]==['Original complete row','A newly discovered row']


def test_refinement_uses_measured_ink_and_keeps_outer_rectangle_and_uncertain_texture():
    image=Image.new('RGB',(300,70),'black');draw=ImageDraw.Draw(image)
    for x in range(20,190,25):draw.rectangle((x,16,x+10,30),fill='white')
    source=row(w=200,h=30,_source_ink=[12,12,196,26])
    original=deepcopy(source);refined=refine_ink(image,source)
    assert refined['_source_ink']==[19,15,163,17]
    assert [refined[k] for k in ('x','y','w','h')]==[source[k] for k in ('x','y','w','h')]
    assert source==original
    assert refine_ink(image,{**source,'text':'arbitrary different text length'})['_source_ink']==refined['_source_ink']
    # Mixed-color side margin is not enough evidence to invent a tighter mask.
    for y in range(12,38):draw.point((10,y),fill=(y*5,50,70))
    assert refine_ink(image,source)['_source_ink']==source['_source_ink']


def test_visual_rule_between_rows_prevents_grouping_but_json_cannot_forge_evidence():
    image=Image.new('RGB',(320,100),'black');draw=ImageDraw.Draw(image)
    source=[row('The first complete message',y=10),row('The second separate message',y=40)]
    assert len(merge_dialogue_lines(source))==1
    draw.line((10,36,259,36),fill='white',width=1)
    refiner=RegionRefiner(2)
    try:result=refiner.refine(image,source)
    finally:refiner.close()
    assert has_visual_separator(result[1]) and not has_visual_separator(result[0])
    assert len(merge_dialogue_lines(result))==2
    assert not has_visual_separator(json.loads(json.dumps(result[1])))
    assert '_row_boundary' not in source[1]


def test_scattered_pixels_between_rows_are_not_a_horizontal_separator():
    image=Image.new('RGB',(320,100),'black');draw=ImageDraw.Draw(image)
    for x in range(10,260,30):draw.point((x,36),fill='white')
    source=[row(y=10),row(y=40)]
    refiner=RegionRefiner(2)
    try:result=refiner.refine(image,source)
    finally:refiner.close()
    assert not any(has_visual_separator(line) for line in result)
    assert len(merge_dialogue_lines(result))==1


def test_failed_regional_read_preserves_the_original_full_frame_detection(monkeypatch):
    class Tess:pass
    refiner=HELPER.RegionalRefiner(Tess,2)
    source=[dict(text='an original reading',x=5,y=8,w=160,h=24,confidence=61)]
    monkeypatch.setattr(refiner,'_read_one',lambda _:(_ for _ in ()).throw(RuntimeError('bad crop')))
    try:assert refiner.refine(Image.new('RGB',(200,80)),source,'eng')==source
    finally:refiner.close()
