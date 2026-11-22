"""Offline paired benchmark. Private fixtures/truth are supplied explicitly."""
import argparse,json,sys,time,statistics,math,re,unicodedata,inspect
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--truth',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();sys.path.insert(0,str(args.root.resolve()))
from PIL import Image
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.tuning import TUNING_DEFAULTS
from response_benchmark import rss,summary
import os

def normalize(s):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',s).translate(str.maketrans({'“':'"','”':'"','’':"'",'‘':"'"})))

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]

truth=json.loads(args.truth.read_text(encoding='utf-8'));result={'version':args.root.resolve().name,'network_used':False,'scenes':{},'accuracy':{}}
total_errors=total_chars=0
for filename,zones in truth.items():
    options={'refine_workers':4} if 'refine_workers' in inspect.signature(OcrCore).parameters else {}
    with Image.open(args.truth.parent/'ocr-private'/filename) as source,OcrCore(args.root/'native/bin/nkc_galgame_translator_core.dll',mode='pixel',**options) as core:
        rgb=source.convert('RGB');first=time.perf_counter();initial=core.recognize_image(rgb,'en');first=(time.perf_counter()-first)*1000
        repeats=[];changes=[];memory=[]
        alternate=rgb.copy();alternate.putpixel((0,0),(127,0,0))
        for _ in range(12):
            # A -> B -> A, not repeated static-frame capture (native hashing
            # already skips static frames in both versions).
            core.recognize_image(alternate,'en')
            t=time.perf_counter();observed=core.recognize_image(rgb,'en');repeats.append((time.perf_counter()-t)*1000)
            assert observed['lines']==initial['lines']
            memory.append((rss(os.getpid())+rss(core.portable._process.pid))/1048576)
        alternate.close()
        for n in range(8):
            with rgb.copy() as changed:
                changed.putpixel((0,0),(n+1,0,0));t=time.perf_counter();observed=core.recognize_image(changed,'en');changes.append((time.perf_counter()-t)*1000)
        records=[]
        for zone in zones:
            left,top,right,bottom=zone['box']
            matching=[line for line in initial['lines'] if left<=line['x']+line['w']/2<right and top<=line['y']+line['h']/2<bottom]
            text='\n'.join(line['text'] for line in sorted(matching,key=lambda v:(v['y'],v['x'])))
            expected=normalize(zone['text']);actual=normalize(text);errors=distance(expected,actual)
            total_errors+=errors;total_chars+=len(expected)
            records.append(dict(expected=zone['text'],actual=text,edit_distance=errors,characters=len(expected)))
        result['scenes'][filename]=dict(first_process_call_ms=first,revisited=summary(repeats),changed_frame=summary(changes),
            working_set_mib=round(max(memory),2),accuracy=records,lines=initial['lines'])
result['accuracy']=dict(characters=total_chars,edits=total_errors,character_accuracy_percent=round(100*(1-total_errors/total_chars),3),
    definition='100*(1-Levenshtein distance/reference characters); whitespace removed, Unicode normalized and curly quotes mapped; case-sensitive.',
    scope='Three screenshots of one game; manually transcribed readable text zones. Not translation semantic accuracy or general-game accuracy.')
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'version':result['version'],'accuracy':result['accuracy'],'scenes':{k:{x:v[x] for x in ('first_process_call_ms','revisited','changed_frame','working_set_mib')} for k,v in result['scenes'].items()}},ensure_ascii=False))
