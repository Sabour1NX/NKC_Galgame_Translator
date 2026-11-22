# SPDX-License-Identifier: MIT
"""Independent local BMP -> text/geometry utility; no application imports.

CUDA providers must execute real profiled kernels for both OCR sessions. CPU
shape operators are allowed, but full silent CPU fallback is rejected. No
network downloads occur here; setup is a separate explicit operation.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import math
import os
import sys
import time

MAX_REQUEST=16384
MAX_RESPONSE=1048576


def quality_parameters(quality,memory_mb):
    if type(quality) is not int or not 0<=quality<=100:raise ValueError('Invalid quality')
    if type(memory_mb) is not int or not 256<=memory_mb<=16384:raise ValueError('Invalid memory budget')
    # Continuous target with the detector's required 32-pixel quantization.
    side=32*int((768+1152*quality/100)/32+.5)
    total=memory_mb*1024*1024;det=int(total*.6);rec=total-det
    return {'quality':quality,'det_limit_side':side,'limit_type':'max','rec_batch_size':8 if memory_mb>=3072 else 4,
            'det_arena_bytes':det,'rec_arena_bytes':rec,'memory_mb':memory_mb}


def bounded_lines(boxes,txts,scores,width,height):
    if boxes is None or txts is None or scores is None:return []
    lines=[];total=0
    for box,text,score in zip(boxes,txts,scores):
        if len(lines)>=512:break
        text=str(text).strip();score=float(score)*100
        if not text or len(text)>16000 or not math.isfinite(score) or not 0<=score<=100:continue
        if '\x00' in text or any(0xd800<=ord(c)<=0xdfff for c in text):continue
        points=[[float(v) for v in point] for point in box]
        if len(points)!=4 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):continue
        left=max(0,int(math.floor(min(p[0] for p in points))));right=min(width,int(math.ceil(max(p[0] for p in points))))
        top=max(0,int(math.floor(min(p[1] for p in points))));bottom=min(height,int(math.ceil(max(p[1] for p in points))))
        if left>=right or top>=bottom:continue
        total+=len(text)
        if total>64000:break
        lines.append({'text':text,'x':left,'y':top,'w':right-left,'h':bottom-top,'confidence':score})
    return lines


def checked_models(directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    result={}
    for task in ('det','rec'):
        item=manifest['models'][task];name=item['file']
        if not isinstance(name,str) or Path(name).name!=name:raise ValueError('model_invalid')
        path=directory/name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('model_invalid')
        result[task]=str(path)
    return result


class ArenaRun:
    """Release idle CUDA allocations after a burst of larger model inputs."""

    def __init__(self, run, options):
        self.run = run
        self.options = options
        self.peak = 0
        self.small_runs = 0
        self.since_trim = 0
        self.low = None
        self.last_trim = None
        self.trims = 0
        self.pressure = False

    def __call__(self, outputs, inputs):
        size = sum(value.nbytes for value in inputs.values())
        now = time.monotonic()
        self.peak = max(self.peak, size)
        self.low = size if self.low is None else min(self.low, size)
        self.small_runs = self.small_runs + 1 if 2 * size <= self.peak else 0
        self.since_trim += 1
        cooled = self.last_trim is None or now - self.last_trim >= 12
        varied = self.since_trim >= 128 and self.peak > self.low * 1.25
        trim = self.pressure or (cooled and (self.small_runs >= 3 or varied))
        try:
            if not trim:
                return self.run(outputs, inputs)
            result = self.run(outputs, inputs, self.options)
        except Exception as exc:
            if any(word in str(exc).lower() for word in ('out of memory', 'allocate', 'allocfailed')):
                self.pressure = True
            raise
        self.trims += 1
        self.last_trim = now
        self.peak = self.low = size
        self.since_trim = self.small_runs = 0
        self.pressure = False
        return result


class Engine:
    def __init__(self,packages,models,input_root,quality,memory_mb):
        self.parameters=quality_parameters(quality,memory_mb)
        sys.path.insert(0,str(packages))
        import numpy as np
        import onnxruntime as ort
        ort.set_default_logger_severity(4)
        # Retain handles. DLL search is only augmented inside this child process.
        self.dll_dirs=[]
        for directory in packages.glob('nvidia/**/bin'):
            if directory.is_dir():self.dll_dirs.append(os.add_dll_directory(str(directory)))
        for directory in packages.glob('nvidia/**/lib'):
            if directory.is_dir():self.dll_dirs.append(os.add_dll_directory(str(directory)))
        ort.preload_dlls(directory='')
        if 'CUDAExecutionProvider' not in ort.get_available_providers():raise RuntimeError('cuda_unavailable')
        paths=checked_models(models)
        from rapidocr import RapidOCR, OCRVersion, ModelType
        from rapidocr.utils.download_file import DownloadFile
        from rapidocr.inference_engine.onnxruntime.main import OrtInferSession
        def no_download(*args,**kwargs):raise RuntimeError('model_invalid')
        DownloadFile.run=no_download
        original=OrtInferSession._init_sess_opts
        profile_count=0
        def options(cfg):
            nonlocal profile_count
            profile_count+=1
            opt=original(cfg);opt.enable_profiling=True
            opt.profile_file_prefix=str(input_root/('cuda-profile-'+str(profile_count)))
            return opt
        OrtInferSession._init_sess_opts=staticmethod(options)
        parameters={
            'Global.log_level':'critical','Global.use_cls':False,'Global.max_side_len':4096,
            'Global.min_side_len':1,'Global.use_vertical_padding':False,'Global.text_score':.5,
            'Global.font_path':str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'),
            'Det.model_path':paths['det'],'Rec.model_path':paths['rec'],
            'Det.ocr_version':OCRVersion.PPOCRV6,'Rec.ocr_version':OCRVersion.PPOCRV6,
            'Det.model_type':ModelType.SMALL,'Rec.model_type':ModelType.SMALL,
            'Det.limit_type':'max','Det.limit_side_len':self.parameters['det_limit_side'],
            'Rec.rec_batch_num':self.parameters['rec_batch_size'],'EngineConfig.onnxruntime.use_cuda':True,
            'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,
            'EngineConfig.onnxruntime.cuda_ep_cfg':{'device_id':0,'gpu_mem_limit':self.parameters['det_arena_bytes'],
                'arena_extend_strategy':'kSameAsRequested','cudnn_conv_algo_search':'HEURISTIC',
                'cudnn_conv_use_max_workspace':'0','do_copy_in_default_stream':True}}
        self.ocr=RapidOCR(params=parameters)
        self.ocr._load_det_model()
        self.ocr.cfg.EngineConfig.onnxruntime.cuda_ep_cfg.gpu_mem_limit=self.parameters['rec_arena_bytes']
        self.ocr._load_rec_model()
        self.kernel_counts={}
        self.provider_limits={}
        self.arena_runs={}
        trim_options=ort.RunOptions()
        trim_options.add_run_config_entry('memory.enable_memory_arena_shrinkage','gpu:0')
        for name,component,shape in [('det',self.ocr.text_det,(1,3,64,64)),('rec',self.ocr.text_rec,(1,3,48,320))]:
            session=component.session.session
            if not session.get_providers() or session.get_providers()[0]!='CUDAExecutionProvider':raise RuntimeError('cuda_unavailable')
            options=session.get_provider_options().get('CUDAExecutionProvider',{})
            limit=int(options.get('gpu_mem_limit',0))
            if limit!=self.parameters[name+'_arena_bytes']:raise RuntimeError('cuda_unavailable')
            self.provider_limits[name]=limit
            session.disable_fallback()
            session.run(None,{session.get_inputs()[0].name:np.zeros(shape,dtype=np.float32)})
            profile=Path(session.end_profiling())
            if not profile.is_relative_to(input_root) or profile.stat().st_size>32*1024*1024:raise RuntimeError('cuda_unavailable')
            events=json.loads(profile.read_text(encoding='utf-8'))
            self.kernel_counts[name]=sum(e.get('args',{}).get('provider')=='CUDAExecutionProvider' for e in events)
            if not self.kernel_counts[name]:raise RuntimeError('cuda_unavailable')
            profile.unlink()
            managed=ArenaRun(session.run,trim_options)
            self.arena_runs[name]=managed
            session.run=managed
        self.np=np;self.ort_version=ort.__version__

    def recognize(self,image):
        started=time.perf_counter()
        # RapidOCR ndarray input is BGR, while the producer's image is RGB.
        result=self.ocr(self.np.array(image)[:,:,::-1].copy(),use_cls=False)
        lines=bounded_lines(result.boxes,result.txts,result.scores,image.width,image.height)
        return {'lines':lines,'ocr_ms':(time.perf_counter()-started)*1000,'engine':'rapidocr-cuda','cuda':self.info()}

    def info(self):
        return {'provider':'CUDAExecutionProvider','kernels_verified':True,'kernel_counts':self.kernel_counts,
                        'provider_arena_bytes':self.provider_limits,
                        'ort_version':self.ort_version,'model':'PP-OCRv6-small','arena_budget_only':True,
                        'arena_trims':{name:run.trims for name,run in self.arena_runs.items()},**self.parameters}


def main():
    # -I intentionally ignores PYTHONIOENCODING. The wire format is always UTF-8.
    sys.stdin.reconfigure(encoding='utf-8',errors='strict')
    sys.stdout.reconfigure(encoding='utf-8',errors='strict')
    parser=argparse.ArgumentParser();parser.add_argument('--packages',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True);parser.add_argument('--input-root',type=Path,required=True)
    parser.add_argument('--quality',type=int,default=75);parser.add_argument('--memory-mb',type=int,default=1024)
    args=parser.parse_args();quality_parameters(args.quality,args.memory_mb)
    args.input_root=args.input_root.resolve();args.packages=args.packages.resolve();args.models=args.models.resolve()
    # Select the pinned helper dependency set before the BMP reader imports PIL.
    sys.path.insert(0,str(args.packages))
    sys.path.insert(0,str(Path(__file__).parent))
    from ocr_helper import load_image
    engine=None
    while True:
        raw=sys.stdin.readline(MAX_REQUEST+1)
        if not raw:break
        if len(raw)>MAX_REQUEST or not raw.endswith('\n'):break
        try:
            request=json.loads(raw)
            if request=={'quit':True}:break
            if request=={'warmup':True}:
                with contextlib.redirect_stdout(sys.stderr):
                    if engine is None:engine=Engine(args.packages,args.models,args.input_root,args.quality,args.memory_mb)
                    response={'lines':[],'ocr_ms':0,'engine':'rapidocr-cuda','cuda':engine.info()}
            else:
                if not isinstance(request,dict) or set(request)!={'image_path','language'}:raise ValueError('input_invalid')
                language=request['language']
                if not isinstance(language,str) or language.lower().split('-')[0] not in {'en','ja','zh','eng','jpn','chi_sim'}:raise ValueError('input_invalid')
                with load_image(request['image_path'],args.input_root) as image:
                    with contextlib.redirect_stdout(sys.stderr):
                        if engine is None:engine=Engine(args.packages,args.models,args.input_root,args.quality,args.memory_mb)
                        response=engine.recognize(image)
        except Exception as exc:
            text=str(exc)
            code=next((c for c in ('cuda_unavailable','model_invalid','input_invalid') if c in text),None)
            if not code:code='dependency_missing' if isinstance(exc,ImportError) else 'cuda_memory' if any(t in text.lower() for t in ('out of memory','allocate','allocfailed')) else 'recognition_failed'
            print(json.dumps({'error':code}),flush=True)
            if code=='cuda_memory' and engine is not None:
                continue
            break
        encoded=json.dumps(response,ensure_ascii=False,allow_nan=False)
        if len(encoded.encode('utf-8'))>MAX_RESPONSE:encoded=json.dumps({'error':'recognition_failed'})
        print(encoded,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
