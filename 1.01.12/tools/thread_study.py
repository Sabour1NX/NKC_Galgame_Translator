# SPDX-License-Identifier: MIT
"""Isolate regional OCR worker limits; clear crop cache for real refinement."""
import argparse,sys,json,time,os,hashlib
from pathlib import Path
from response_benchmark import rss,summary
p=argparse.ArgumentParser();p.add_argument('--workers',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1];a.output=a.output.resolve();sys.path.insert(0,str(r/'vendor/ocr'));os.environ['OMP_THREAD_LIMIT']='1'
import tesserocr
from PIL import Image
from ocr_helper import RegionalRefiner,ParallelDiscovery,recognize
os.chdir(r/'models/tessdata')
result={'workers':a.workers,'scenes':{},'scope':'Direct pixel OCR helper only; no IPC, UI, network or geometry postprocessing. Warm engines, crop cache cleared each call; whole-frame discovery unchanged. All process RSS is sampled, not peak memory.'}
with tesserocr.PyTessBaseAPI(path='.',lang='eng',psm=tesserocr.PSM.AUTO,oem=tesserocr.OEM.LSTM_ONLY) as engine:
 refiner=RegionalRefiner(tesserocr,a.workers);discovery=ParallelDiscovery(tesserocr)
 try:
  for name in ('spacerogue-game.png','status.png','cargo.png'):
   with Image.open(r/'reports/ocr-private'/name) as source:
    image=source.convert('RGB');times=[];cpu=[];memory=[];digests=[];counts=[]
    for i in range(7):
     refiner._cache.clear();start=time.perf_counter();c=time.process_time()
     lines=recognize(engine,tesserocr,image,'eng','pixel',refiner,discovery)
     duration=(time.perf_counter()-start)*1000;cost=(time.process_time()-c)*1000
     stable=[{k:line[k] for k in ('text','x','y','w','h')} for line in lines]
     digests.append(hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest());counts.append(len(lines))
     if i:times.append(duration);cpu.append(cost);memory.append(rss(os.getpid())/1048576)
    result['scenes'][name]={'wall':summary(times),'cpu':summary(cpu),'sampled_working_mib':round(max(memory),2),'output_hashes':digests,'line_counts':counts}
    image.close()
 finally:refiner.close();discovery.close()
a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
