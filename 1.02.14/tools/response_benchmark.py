# SPDX-License-Identifier: MIT
"""Offline, comparable OCR and pipeline latency benchmark; never loads a key.

Run with --root pointing at either release, the same --fixtures directory and
--output. Real Tesseract OCR; simulated 80 ms provider first token. The two
measurements are deliberately separate, not a claimed end-to-end API result.
"""
import argparse
import inspect
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import threading
import time


def summary(values):
    ordered=sorted(values)
    return dict(n=len(values),p50_ms=round(statistics.median(values),3),
                p95_ms=round(ordered[max(0,math.ceil(len(values)*.95)-1)],3),
                samples_ms=[round(v,3) for v in values])


def rss(pid):
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(key,ctypes.c_size_t) for key in
            ('peak','working','pool_peak','pool','nonpool_peak','nonpool','page','page_peak')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return 0
    try:
        value=Counters();value.cb=ctypes.sizeof(value)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):return 0
        return value.working
    finally:kernel.CloseHandle(handle)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--iterations',type=int,default=8)
    args=parser.parse_args();sys.path.insert(0,str(args.root.resolve()))
    from PIL import Image
    from nkc_galgame_translator.ocr import OcrCore
    from nkc_galgame_translator.pipeline import Pipeline
    from nkc_galgame_translator.tuning import TUNING_DEFAULTS
    import os
    report=dict(version=args.root.resolve().name,network_used=False,credentials_loaded=False,
                timestamp=time.strftime('%Y-%m-%dT%H:%M:%S%z'),ocr={},pipeline={})
    for name in ('spacerogue-game.png','status.png','cargo.png'):
        path=args.fixtures/name
        if not path.is_file():continue
        options={'refine_workers':TUNING_DEFAULTS['ocr_refine_workers']} if 'refine_workers' in inspect.signature(OcrCore).parameters else {}
        with Image.open(path) as original, OcrCore(args.root/'native/bin/nkc_galgame_translator_core.dll',mode='pixel',**options) as core:
            frame=original.convert('RGB');samples=[];digests=[];working=[];all_lines=[]
            for iteration in range(args.iterations+1):
                # A changing corner pixel simulates animation without changing text.
                # Prevent a whole-image result cache from masquerading as OCR speed.
                frame.putpixel((0,0),(iteration%256,0,0))
                started=time.perf_counter();result=core.recognize_image(frame,'en')
                duration=(time.perf_counter()-started)*1000
                lines=[{k:line[k] for k in ('text','x','y','w','h')} for line in result['lines']]
                digests.append(hashlib.sha256(json.dumps(lines,sort_keys=True).encode()).hexdigest())
                all_lines.append(lines)
                if iteration==0:cold=duration
                else:samples.append(duration)
                working.append((rss(os.getpid())+rss(core.portable._process.pid))/1048576)
            frame.close()
        report['ocr'][name]=dict(cold_ms=round(cold,3),warm=summary(samples),
            sampled_peak_combined_working_set_mib=round(max(working),2),
            output_hashes=digests,outputs=all_lines,fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    # Model a frame becoming visible at uniformly distributed capture phases.
    class Core:
        def reset(self):pass
        def hide_overlay(self):pass
        def capture_ocr(self,*_,**kwargs):
            visible=time.perf_counter()>=self.visible_at
            changed=visible and not self.seen
            self.seen|=visible
            return dict(changed=changed,lines=[dict(text='Welcome aboard the ship.',x=10,y=10,w=300,h=24)] if changed else [],ocr_ms=0,capture_ms=0)
    class Engine:
        def translate(self,game,source,target,text,on_chunk,context,**options):
            time.sleep(.08);on_chunk('\u6b22\u8fce\u767b\u8239\u3002');return '\u6b22\u8fce\u767b\u8239\u3002'
    values=[]
    for n in range(12):
        event=threading.Event();first=[];core=Core();core.seen=False
        interval=TUNING_DEFAULTS['capture_interval_ms']/1000
        core.visible_at=time.perf_counter()+.015+interval*(n+.5)/12
        def emit(message):
            if message[0]=='translation' and not first:
                first.append((time.perf_counter()-core.visible_at)*1000);event.set()
        pipeline=Pipeline(core,Engine(),emit,interval=interval,
            settle=TUNING_DEFAULTS['settle_ms']/1000,show_source_label=False,show_translation_brackets=False)
        pipeline.start(lambda:(0,0,640,480),'benchmark','en','zh-Hans')
        try:
            if not event.wait(4):raise RuntimeError('Pipeline benchmark timed out')
            values.append(first[0])
        finally:pipeline.stop();pipeline.join()
    report['pipeline']=dict(first_translation_callback=summary(values),simulated_provider_ms=80,
        capture_interval_ms=TUNING_DEFAULTS['capture_interval_ms'],settle_ms=TUNING_DEFAULTS['settle_ms'],
        limitation='Synthetic zero-cost OCR; excludes Tk/native rendering and real provider latency.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:({name:{kk:vv for kk,vv in row.items() if kk not in ('outputs','output_hashes')} for name,row in v.items()} if k=='ocr' else v) for k,v in report.items()},ensure_ascii=False))


if __name__=='__main__':main()
