# SPDX-License-Identifier: MIT
"""Optional GPU OCR client. No deep-learning packages are loaded in the GUI.

The helper is a separate, bounded image/JSON process. Installed files are not
proof of working CUDA: the helper verifies sessions AND actual CUDA kernels.
"""
from pathlib import Path
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

MAX_RESPONSE=1048576


class CudaOcrError(RuntimeError):
    def __init__(self,code,message=None):
        self.code=code
        super().__init__(message or 'CUDA OCR unavailable ('+code+'); use Windows/Tesseract OCR.')


def check_options(memory_mb,quality):
    if type(memory_mb) is not int or not 256<=memory_mb<=16384:raise ValueError('CUDA memory budget must be 256–16384 MiB')
    if type(quality) is not int or not 0<=quality<=100:raise ValueError('CUDA quality must be an integer from 0 to 100')


def validate_cuda_response(value,width,height):
    if not isinstance(value,dict):raise CudaOcrError('invalid_response')
    if 'error' in value:raise CudaOcrError(value['error'] if isinstance(value['error'],str) and value['error'] in {'cuda_unavailable','cuda_memory','dependency_missing','model_invalid','input_invalid','recognition_failed','cancelled'} else 'recognition_failed')
    elapsed=value.get('ocr_ms');lines=value.get('lines');info=value.get('cuda')
    if (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=120000 or
        not isinstance(lines,list) or len(lines)>512 or not isinstance(info,dict) or
        info.get('provider')!='CUDAExecutionProvider' or info.get('kernels_verified') is not True):
        raise CudaOcrError('invalid_response')
    total=0
    for line in lines:
        if not isinstance(line,dict):raise CudaOcrError('invalid_response')
        text=line.get('text');score=line.get('confidence')
        if not isinstance(text,str) or len(text)>16000 or '\x00' in text or any(0xd800<=ord(c)<=0xdfff for c in text):raise CudaOcrError('invalid_response')
        total+=len(text)
        if total>64000:raise CudaOcrError('invalid_response')
        if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=100:raise CudaOcrError('invalid_response')
        if any(type(line.get(k)) is not int for k in ('x','y','w','h')):raise CudaOcrError('invalid_response')
        if not(0<=line['x']<line['x']+line['w']<=width and 0<=line['y']<line['y']+line['h']<=height):raise CudaOcrError('invalid_response')
    return value


class CudaOcr:
    def __init__(self,root,memory_mb=1024,quality=75):
        check_options(memory_mb,quality)
        self.root=Path(root).resolve();self.memory_mb=memory_mb;self.quality=quality
        self.packages=self.root/'vendor/cuda';self.models=self.root/'models/cuda'
        self._lock=threading.RLock();self._process=None;self._temp=None
        self._cancelled=threading.Event()
        self._responses=queue.Queue(maxsize=2);self.last_status={'state':'not_started'}

    def _python(self):
        for path in (self.root/'vendor/python/python.exe',self.root/'runtime/python.exe'):
            if path.is_file():return path
        return None

    def available(self):
        return bool(self._python() and (self.root/'tools/cuda_ocr_helper.py').is_file() and
            (self.packages/'onnxruntime').is_dir() and (self.packages/'rapidocr').is_dir() and
            (self.models/'manifest.json').is_file())

    def _start(self):
        if self._cancelled.is_set():raise CudaOcrError('cancelled')
        if self._process and self._process.poll() is None:return
        if self._process or self._temp:self.close()
        if not self.available():raise CudaOcrError('dependency_missing')
        data=self.root/'data';data.mkdir(exist_ok=True)
        self._temp=tempfile.TemporaryDirectory(prefix='cuda-ocr-',dir=data)
        args=[str(self._python()),'-I','-u',str(self.root/'tools/cuda_ocr_helper.py'),
              '--packages',str(self.packages),'--models',str(self.models),'--input-root',self._temp.name,
              '--memory-mb',str(self.memory_mb),'--quality',str(self.quality)]
        env=dict(os.environ)
        for key in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','CUDA_PATH','CUDA_HOME'):env.pop(key,None)
        env.update(PYTHONIOENCODING='utf-8',OMP_NUM_THREADS='2')
        try:
            self._process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',bufsize=1,cwd=self.root,env=env,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            self.close();raise CudaOcrError('dependency_missing') from None
        if self._cancelled.is_set():
            self._process.terminate();raise CudaOcrError('cancelled')
        self._responses=queue.Queue(maxsize=2);process,responses=self._process,self._responses
        def receive():
            try:
                while True:
                    line=process.stdout.readline(MAX_RESPONSE+1)
                    if not line:break
                    if len(line)>MAX_RESPONSE or not line.endswith('\n'):break
                    responses.put(json.loads(line),timeout=1)
            except Exception:pass
            finally:
                try:responses.put_nowait({'error':'recognition_failed'})
                except queue.Full:pass
        threading.Thread(target=receive,daemon=True,name='cuda-ocr-output').start()

    def cancel(self):
        """Nonblocking terminal cancellation; does not wait for the OCR lock.

        The caller joins its worker then calls close(). Create a new CudaOcr to
        restart after cancellation, so stale responses cannot cross lifetimes.
        """
        self._cancelled.set();process=self._process
        if process and process.poll() is None:
            try:process.terminate()
            except OSError:pass
        try:self._responses.put_nowait({'error':'cancelled'})
        except queue.Full:pass

    def warmup(self):
        """Verify local models/CUDA with synthetic tensors; no screen or network."""
        with self._lock:
            started=time.perf_counter()
            try:
                self._start()
                self._process.stdin.write('{"warmup":true}\n');self._process.stdin.flush()
                value=validate_cuda_response(self._responses.get(timeout=90),1,1)
                if self._cancelled.is_set():raise CudaOcrError('cancelled')
            except (queue.Empty,OSError):
                self.close();raise CudaOcrError('cancelled' if self._cancelled.is_set() else 'timeout') from None
            except CudaOcrError:
                self.close()
                if self._cancelled.is_set():raise CudaOcrError('cancelled') from None
                raise
            value['client_ms']=(time.perf_counter()-started)*1000
            self.last_status={'state':'cuda',**value['cuda']}
            return value

    def recognize(self,image,language='en'):
        if not isinstance(language,str) or language.lower().split('-')[0] not in {'en','ja','zh','jpn','eng','chi_sim'}:
            raise ValueError('CUDA OCR currently supports Chinese, English and Japanese')
        if not (1<=image.width<=4096 and 1<=image.height<=4096):raise ValueError('Invalid CUDA OCR image dimensions')
        with self._lock:
            started=time.perf_counter()
            try:
                self._start();path=Path(self._temp.name)/'frame.bmp'
                with image.convert('RGB') as rgb:rgb.save(path,format='BMP')
                self._process.stdin.write(json.dumps({'image_path':str(path),'language':language})+'\n');self._process.stdin.flush()
                response=self._responses.get(timeout=90)
                value=validate_cuda_response(response,image.width,image.height)
                if self._cancelled.is_set():raise CudaOcrError('cancelled')
            except (queue.Empty,OSError):
                self.close();self.last_status={'state':'unavailable','reason':'timeout'};raise CudaOcrError('timeout') from None
            except CudaOcrError as exc:
                # A frame can exceed the arena without invalidating either
                # warmed session. The caller can retry a smaller input.
                if exc.code!='cuda_memory':
                    self.close()
                self.last_status={'state':'unavailable','reason':exc.code}
                if self._cancelled.is_set():raise CudaOcrError('cancelled') from None
                raise
            value['client_ms']=(time.perf_counter()-started)*1000
            self.last_status={'state':'cuda',**value['cuda']}
            return value

    def close(self):
        with self._lock:
            process,self._process=self._process,None
            if process:
                if process.poll() is None:
                    try:process.stdin.write('{"quit":true}\n');process.stdin.flush();process.wait(timeout=1)
                    except (OSError,subprocess.TimeoutExpired):process.kill();process.wait(timeout=3)
                for stream in (process.stdin,process.stdout):
                    if stream:
                        try:stream.close()
                        except OSError:pass
            if self._temp:self._temp.cleanup();self._temp=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
