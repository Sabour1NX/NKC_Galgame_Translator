from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from nkc_galgame_translator.cuda_ocr import CudaOcr, CudaOcrError, check_options, validate_cuda_response

spec=importlib.util.spec_from_file_location('cuda_helper_test',Path(__file__).resolve().parents[1]/'tools/cuda_ocr_helper.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def response():
    return {'ocr_ms':1.1,'lines':[{'text':'Welcome \u65e5\u672c\u8a9e','x':1,'y':2,'w':20,'h':10,'confidence':98.1}],
        'cuda':{'provider':'CUDAExecutionProvider','kernels_verified':True}}


@pytest.mark.parametrize('quality,side',[(0,768),(25,1056),(50,1344),(75,1632),(100,1920)])
def test_quality_linear_quantized(quality,side):
    p=helper.quality_parameters(quality,1024)
    assert p['det_limit_side']==side
    assert p['det_arena_bytes']+p['rec_arena_bytes']==1024*1024*1024
    assert p['rec_batch_size']==4 and p['limit_type']=='max'


def test_slider_has_many_actual_steps():
    sides=[helper.quality_parameters(q,1024)['det_limit_side'] for q in range(101)]
    assert sides==sorted(sides) and len(set(sides))==37


@pytest.mark.parametrize('memory,quality',[(255,75),(16385,75),(True,75),(1024,-1),(1024,101),(1024,75.1),(1024,True)])
def test_reject_bad_settings(memory,quality):
    with pytest.raises(ValueError):check_options(memory,quality)
    with pytest.raises(ValueError):helper.quality_parameters(quality,memory)


@pytest.mark.parametrize('field,value',[('x',-1),('y',-1),('w',0),('h',0),('w',1000),('x',True),('confidence',float('nan')),('confidence',101),('text','x\x00y'),('text','x\ud800'),('text','x'*16001)])
def test_reject_malformed_geometry_and_text(field,value):
    r=response();r['lines'][0][field]=value
    with pytest.raises(CudaOcrError):validate_cuda_response(r,100,100)


@pytest.mark.parametrize('elapsed',[True,float('inf'),float('nan'),-1,120001,'1'])
def test_reject_invalid_timing(elapsed):
    r=response();r['ocr_ms']=elapsed
    with pytest.raises(CudaOcrError):validate_cuda_response(r,100,100)


@pytest.mark.parametrize('info',[{},None,{'provider':'CPUExecutionProvider','kernels_verified':True},
    {'provider':'CUDAExecutionProvider','kernels_verified':False}])
def test_cpu_fallback_never_reported_as_cuda(info):
    r=response();r['cuda']=info
    with pytest.raises(CudaOcrError):validate_cuda_response(r,100,100)


@pytest.mark.parametrize('error',['cuda_unavailable','cuda_memory','cancelled','model_invalid',[],{}])
def test_sanitized_error(error):
    with pytest.raises(CudaOcrError) as exc:validate_cuda_response({'error':error},10,10)
    assert exc.value.code==(error if isinstance(error,str) else 'recognition_failed')


def test_valid_unicode_result():
    r=response();assert validate_cuda_response(r,100,100) is r


def test_oversized_line_list_rejected():
    r=response();r['lines']*=513
    with pytest.raises(CudaOcrError):validate_cuda_response(r,100,100)


def test_helper_clips_boxes_and_converts_confidence():
    lines=helper.bounded_lines([[[-2,1],[20,1],[20,10],[-2,10]]],['\u65e5\u672c\u8a9e'],[.95],15,20)
    assert lines==[{'text':'\u65e5\u672c\u8a9e','x':0,'y':1,'w':15,'h':9,'confidence':95}]


def test_helper_skips_nonfinite_geometry():
    assert helper.bounded_lines([[[float('nan'),1],[20,1],[20,10],[0,10]]],['bad'],[.9],40,40)==[]


def test_model_digest_and_traversal(tmp_path):
    data=b'fixed-model';name='model.onnx';(tmp_path/name).write_bytes(data)
    item={'file':name,'sha256':hashlib.sha256(data).hexdigest()}
    manifest={'models':{'det':item,'rec':item}}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    assert helper.checked_models(tmp_path)['det']==str(tmp_path/name)
    (tmp_path/name).write_bytes(b'corrupt')
    with pytest.raises(ValueError):helper.checked_models(tmp_path)
    item['file']='../outside.onnx'
    (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError):helper.checked_models(tmp_path)


def test_missing_components_never_download(tmp_path):
    core=CudaOcr(tmp_path)
    assert not core.available()
    with pytest.raises(CudaOcrError,match='dependency_missing'):core.warmup()
    assert not (tmp_path/'vendor').exists()


def test_cancel_does_not_wait_for_recognition_lock(tmp_path):
    core=CudaOcr(tmp_path);entered=threading.Event();release=threading.Event()
    def hold():
        with core._lock:entered.set();release.wait(5)
    thread=threading.Thread(target=hold);thread.start();assert entered.wait(1)
    start=time.perf_counter();core.cancel();elapsed=time.perf_counter()-start
    release.set();thread.join(1)
    assert elapsed<.2 and core._cancelled.is_set()
    with pytest.raises(CudaOcrError,match='cancelled'):core.warmup()


def test_public_import_has_no_gpu_dependency():
    import subprocess
    code="import sys; from nkc_galgame_translator.cuda_ocr import CudaOcr; assert not any(x in sys.modules for x in ['numpy','onnxruntime','rapidocr','cv2'])"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True)
    assert result.returncode==0,result.stderr
