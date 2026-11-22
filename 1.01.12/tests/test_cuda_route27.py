# SPDX-License-Identifier: MIT
"""Exercise GPU routing/fallback without CUDA, HTTP or game capture."""
from PIL import Image
import pytest
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.vision_core import VisionCore


class FakeCuda:
    def __init__(self,root,**settings):self.settings=settings;self.calls=0;self.closes=0;self.failure=False
    def available(self):return True
    def recognize(self,image,language):
        self.calls+=1
        if self.failure:raise RuntimeError('synthetic GPU failure')
        return {'engine':'rapidocr-cuda','ocr_ms':12,'lines':[
            {'text':'Start game','x':10,'y':10,'w':80,'h':20,'confidence':98}],
            'cuda':{'provider':'CUDAExecutionProvider'}}
    def close(self):self.closes+=1


def test_cuda_maps_original_coordinates_caches_and_obeys_disable(monkeypatch):
    import nkc_galgame_translator.cuda_ocr as module
    monkeypatch.setattr(module,'CudaOcr',FakeCuda)
    with OcrCore(cuda_enabled=True,cuda_quality=77,cuda_memory_mb=1536) as core:
        assert core.cuda.settings=={'quality':77,'memory_mb':1536}
        image=Image.new('RGB',(150,70),'white')
        response=core.recognize_image(image,'en')
        assert response['engine']=='rapidocr-cuda' and response['cuda_status']=='active'
        assert response['lines'][0]['x']==8 and response['lines'][0]['y']==8
        assert core.recognize_image(image,'en')['frame_cache_hit']
        assert core.cuda.calls==1
    with OcrCore(cuda_enabled=False) as disabled:assert disabled.cuda is None


def test_cuda_failure_latches_and_falls_back_without_repeated_startup(monkeypatch):
    import nkc_galgame_translator.cuda_ocr as module
    monkeypatch.setattr(module,'CudaOcr',FakeCuda)
    with OcrCore(cuda_enabled=True) as core:
        core.cuda.failure=True
        core._native_languages=['en-US']
        monkeypatch.setattr(core.native,'recognize_bgra',lambda *_:{'lines':[],'ocr_ms':1})
        for color in ('white','gray'):
            result=core.recognize_image(Image.new('RGB',(80,40),color),'en')
            assert result['cuda_status']=='failed'
        assert core.cuda.calls==1 and core.cuda.closes==1


@pytest.mark.parametrize('options',[{'cuda_quality':True},{'cuda_quality':-1},{'cuda_quality':101},
                                   {'cuda_memory_mb':128},{'cuda_memory_mb':16385},{'cuda_enabled':1}])
def test_bad_gpu_settings_rejected_before_resource_allocation(options):
    with pytest.raises(ValueError):OcrCore(**options)


def test_vision_review_only_uncertain_cuda_rows_and_never_assumes_windows_confidence():
    rows=[{'text':'Start','confidence':99},{'text':'Question','confidence':82},
          {'text':'Unknown'},{'text':'Anchor','confidence':99,'_vision_only':True}]
    trusted,review=VisionCore._cuda_review_partition({'engine':'rapidocr-cuda','lines':rows})
    assert [r['text'] for r in trusted]==['Start']
    assert len(review)==3
    trusted[0]['text']='mutated'
    assert rows[0]['text']=='Start'
    assert VisionCore._cuda_review_partition({'engine':'windows','lines':rows})==([],rows)
