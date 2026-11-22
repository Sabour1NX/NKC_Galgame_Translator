# SPDX-License-Identifier: MIT
"""Offline, uncached CUDA inference benchmark; supplied private fixtures only."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import threading
import time
import unicodedata

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nkc_galgame_translator.cuda_ocr import CudaOcr
from PIL import Image


def normalize(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text).translate(str.maketrans({'“':'"','”':'"','’':"'",'‘':"'"})))


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def accuracy(lines,zones):
    result=[]
    for zone in zones:
        left,top,right,bottom=zone['box']
        matching=[line for line in lines if left<=line['x']+line['w']/2<right and top<=line['y']+line['h']/2<bottom]
        actual='\n'.join(line['text'] for line in sorted(matching,key=lambda v:(v['y'],v['x'])))
        expected=zone.get('text',zone.get('expected'))
        result.append({'box':zone['box'],'expected':expected,'actual':actual,'characters':len(normalize(expected)),
                       'edit_distance':distance(normalize(expected),normalize(actual))})
    chars=sum(x['characters'] for x in result);errors=sum(x['edit_distance'] for x in result)
    return {'characters':chars,'edits':errors,'character_accuracy_percent':round(100*(1-errors/chars),3),'zones':result}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--rounds',type=int,default=5)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];base=args.baseline.resolve()
    truth=json.loads((base/'reports/accuracy-truth.json').read_text(encoding='utf-8'))
    needy=json.loads((base/'reports/needy-local25.json').read_text(encoding='utf-8'))
    truth['needy-caution-full.png']=needy['scenes']['needy-caution-full.png']['accuracy']
    names=['needy-window-original25.png',*truth]
    records={'version':'0.01.27','offline':True,'api_calls':0,'cache_used':False,'rounds':args.rounds,
        'scope':'Fixed original screenshots to raw CUDA OCR output. No capture, AI, translation or overlay. Accuracy uses manual truth zones and NFKC whitespace-normalized Levenshtein distance.',
        'memory_note':'nvidia-smi samples total desktop GPU memory, not process memory. Arena budget is not a hard VRAM cap.',
        'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],text=True).strip(),
        'quality_runs':[]}
    for quality in (0,75,100):
        samples=[];stop=threading.Event()
        def poll():
            while not stop.is_set():
                try:samples.append({'time':time.time(),'mib':int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())})
                except (OSError,ValueError,subprocess.SubprocessError):pass
                stop.wait(.25)
        thread=threading.Thread(target=poll,daemon=True);thread.start()
        run={'quality':quality,'memory_mb':1024,'scenes':{}}
        try:
            with CudaOcr(root,quality=quality) as core:
                for name in names:
                    path=base/'reports/ocr-private'/name
                    with Image.open(path) as source:
                        image=source.convert('RGB');initial=core.recognize(image,'ja' if name.startswith('needy') else 'en')
                        times=[]
                        for _ in range(args.rounds):
                            out=core.recognize(image,'ja' if name.startswith('needy') else 'en')
                            times.append({'ocr_ms':out['ocr_ms'],'client_ms':out['client_ms']})
                        run['scenes'][name]={'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'image_size':image.size,
                            'first_call_client_ms':initial['client_ms'],'first_call_ocr_ms':initial['ocr_ms'],
                            'warm_samples':times,'warm_median_ocr_ms':statistics.median(t['ocr_ms'] for t in times),
                            'warm_median_client_ms':statistics.median(t['client_ms'] for t in times),'cuda':out['cuda'],'lines':out['lines']}
                        if name in truth:run['scenes'][name]['accuracy']=accuracy(out['lines'],truth[name])
                        print(json.dumps({'quality':quality,'scene':name,'warm_ms':run['scenes'][name]['warm_median_client_ms'],
                            'accuracy':run['scenes'][name].get('accuracy',{}).get('character_accuracy_percent')}),flush=True)
        finally:
            stop.set();thread.join(timeout=3)
        run['gpu_total_memory_samples']=samples
        records['quality_runs'].append(run)
        args.output.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__':raise SystemExit(main())
