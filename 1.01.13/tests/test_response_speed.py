# SPDX-License-Identifier: MIT
"""Cache freshness, bounded memory, deterministic full-frame parallelism."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import threading
from PIL import Image
from nkc_galgame_translator.tuning import PERFORMANCE_PRESETS, validate_tuning

spec=importlib.util.spec_from_file_location('speed_helper',Path(__file__).resolve().parents[1]/'tools/ocr_helper.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def test_ocr_cache_keeps_current_geometry_and_invalidates_pixels_language_and_source(monkeypatch):
    refiner=helper.RegionalRefiner(object(),2);calls=[]
    def read(job):
        calls.append(job)
        return {**job[1],'text':'recognized words','confidence':95}
    monkeypatch.setattr(refiner,'_read_one',read)
    source=dict(text='source words',x=10,y=10,w=90,h=24,confidence=80)
    with Image.new('RGB',(300,120),'white') as image:
        try:
            first=refiner.refine(image,[source],'eng')[0]
            moved=refiner.refine(image,[{**source,'x':110,'y':60}],'eng')[0]
            assert len(calls)==1 and moved['x']==110 and moved['y']==60 and moved['text']==first['text']
            image.putpixel((12,12),(0,0,0))
            refiner.refine(image,[source],'eng');assert len(calls)==2
            refiner.refine(image,[source],'jpn');assert len(calls)==3
            refiner.refine(image,[{**source,'text':'different source'}],'eng');assert len(calls)==4
            refiner.refine(image,[{**source,'confidence':81}],'eng');assert len(calls)==5
        finally:refiner.close()


def test_failed_refinement_retries_and_cache_is_bounded(monkeypatch):
    refiner=helper.RegionalRefiner(object(),1);calls=[]
    source=dict(text='original words',x=10,y=10,w=90,h=24,confidence=80)
    def read(job):
        calls.append(1)
        if len(calls)==1:raise RuntimeError('transient')
        return {**job[1],'text':'recognized words'}
    monkeypatch.setattr(refiner,'_read_one',read)
    with Image.new('RGB',(150,80),'white') as image:
        try:
            assert refiner.refine(image,[source],'eng')==[source]
            assert not refiner._cache
            assert refiner.refine(image,[source],'eng')[0]['text']=='recognized words'
            for index in range(270):refiner.refine(image,[{**source,'text':str(index)+' words'}],'eng')
            assert len(refiner._cache)==256
        finally:refiner.close()
    assert not refiner._cache


def test_discovery_passes_overlap_but_merge_primary_first(monkeypatch):
    barrier=threading.Barrier(2);threads=[]
    class Tess:
        class PSM:AUTO=3;SPARSE_TEXT=11
        class OEM:LSTM_ONLY=1
    class Engine:
        def __init__(self,**kwargs):self.mode=kwargs.get('psm',3);self.owner=threading.get_ident()
        def SetImageBytes(self,*_):assert self.owner==threading.get_ident()
        def SetPageSegMode(self,mode):self.mode=mode
        def Recognize(self):threads.append(threading.get_ident());barrier.wait(timeout=3)
        def End(self):pass
    Tess.PyTessBaseAPI=Engine
    def lines(engine,*_):
        return [dict(text='primary' if engine.mode==3 else 'supplement',x=10,y=10,w=90,h=24,confidence=96)]
    monkeypatch.setattr(helper,'read_lines',lines)
    discovery=helper.ParallelDiscovery(Tess)
    with Image.new('RGB',(150,80),'white') as image:
        try:result=helper.recognize(Engine(),Tess,image,'jpn','pixel',discovery=discovery)
        finally:discovery.close()
    assert len(set(threads))==2 and result[0]['text']=='primary' and len(result)==1


def test_failed_primary_waits_for_supplement_before_releasing_image():
    entered=threading.Event();finished=threading.Event()
    pool=ThreadPoolExecutor(1)
    class Discovery:
        def submit(self,image,language):
            def work():
                assert entered.wait(2)
                assert image.getpixel((0,0))==(255,255,255)
                finished.set();return []
            return pool.submit(work)
    class Tess:
        class PSM:AUTO=3
    class Engine:
        def SetImageBytes(self,*_):pass
        def SetPageSegMode(self,*_):pass
        def Recognize(self):entered.set();raise RuntimeError('primary failure')
    import pytest
    with Image.new('RGB',(20,20),'black') as image:
        try:
            with pytest.raises(RuntimeError):helper.recognize(Engine(),Tess,image,'eng','pixel',discovery=Discovery())
            assert finished.is_set()
        finally:pool.shutdown()


def test_presets_are_valid_and_custom_values_are_not_overridden():
    for values in PERFORMANCE_PRESETS.values():
        result=validate_tuning(values)
        assert result['translation_workers']==result['max_concurrency']
        assert result['capture_interval_ms']*result['track_missing_frames']==500
    assert validate_tuning({'capture_interval_ms':333,'settle_ms':777})['settle_ms']==777
