# SPDX-License-Identifier: MIT
"""Offline integrated multi-object scheduling check; simulated network, no game UI."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import threading
import time
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.presentation import OverlayState

ROOT=Path(__file__).resolve().parents[1]

class FrameSource:
    def __init__(self,lines):
        self.lines=lines;self.version=1;self.seen=-1;self.lock=threading.Lock()
    def set(self,lines):
        with self.lock:self.lines=lines;self.version+=1
    def reset(self):self.seen=-1
    def capture_ocr(self,*_,**__):
        with self.lock:
            changed=self.seen!=self.version;self.seen=self.version
            return {'changed':changed,'lines':[dict(x) for x in self.lines] if changed else [],'capture_ms':0,'ocr_ms':0}
    def hide_overlay(self):pass

class DelayedEngine:
    def __init__(self):
        self.lock=threading.Lock();self.active=0;self.max_active=0;self.calls=[]
    def translate(self,game,source,target,text,on_chunk=None,context=''):
        with self.lock:self.calls.append(text);self.active+=1;self.max_active=max(self.max_active,self.active)
        try:
            if on_chunk:on_chunk('\u8bd1\u6587\uff1a')
            time.sleep(.12)
            value='\u8bd1\u6587\uff1a'+text
            if on_chunk:on_chunk(value)
            return value
        finally:
            with self.lock:self.active-=1

def main():
    lines=[{'text':f'Object {i}','x':20,'y':i*80+20,'w':150,'h':24,'bg':[20,20,20],'fg':[240,240,240]} for i in range(6)]
    core=FrameSource(lines);engine=DelayedEngine();state=OverlayState();lock=threading.Lock();all_events=[]
    def emit(event):
        kind,session,payload=event
        with lock:
            all_events.append((kind,session))
            if kind=='clear':state.clear()
            elif kind=='objects':state.apply_objects(payload)
            elif kind=='translation':identity,line,_,_=payload;state.apply_translation(identity,line)
    pipeline=Pipeline(core,engine,emit,interval=.01,settle=.02,merge_lines=False,translation_workers=4,tracking_workers=2)
    start=time.perf_counter();pipeline.start(lambda:(0,0,800,600),'fixture','en','zh-Hans')
    def wait_until(predicate,timeout=5):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            with lock:
                if predicate():return
            time.sleep(.005)
        raise AssertionError('Multi-object integration timeout')
    try:
        wait_until(lambda:len(state.rendered)==6 and all(x['final'] for x in state.rendered.values()))
        initial_ms=(time.perf_counter()-start)*1000
        with lock:
            initial_ids={v['line']['text']:k for k,v in state.objects.items()}
            preserved={k:dict(v) for k,v in state.rendered.items()}
            old_event_count=len(all_events)
        assert engine.max_active==4,engine.max_active
        moved=[{**line,'x':line['x']+18} for line in reversed(lines)]
        core.set(moved)
        wait_until(lambda:len(state.objects)==6 and all(x['line']['x']==38 for x in state.objects.values()))
        with lock:
            assert {v['line']['text']:k for k,v in state.objects.items()}==initial_ids
            assert all(state.rendered[k]['text']==v['text'] for k,v in preserved.items())
        time.sleep(.08)
        assert len(engine.calls)==6,engine.calls
        changed=[{**line,'text':'Continue game'} if line['text']=='Object 2' else dict(line) for line in moved]
        core.set(changed)
        identity=initial_ids['Object 2']
        wait_until(lambda:state.rendered.get(identity,{}).get('text')=='[\u82f1\u8bed\uff1a\u8bd1\u6587\uff1aContinue game]' and state.rendered[identity]['final'])
        assert len(engine.calls)==7,engine.calls
        with lock:
            assert state.objects[identity]['revision']==2
            assert all(state.rendered[k]['text']==v['text'] for k,v in preserved.items() if k!=identity)
            assert not any(kind=='clear' for kind,_ in all_events[old_event_count:])
        result={'version':'0.01.08','status':'passed','network_used':False,'game_ui_used':False,
            'input_objects':6,'tracking_workers':2,'translation_workers':4,
            'observed_max_parallel_translations':engine.max_active,'simulated_delay_per_request_ms':120,
            'initial_batch_ms':round(initial_ms,3),'calls_after_geometry_move':6,
            'calls_after_one_text_change':len(engine.calls),'unchanged_objects_preserved':5,
            'stable_ids_on_reordered_moving_boxes':True,'global_clear_on_single_change':False,
            'pipeline_stats':pipeline.get_stats(),
            'scope':'Integrated scheduling test with fake OCR and simulated network; not an OCR/API/game latency benchmark.'}
    finally:
        pipeline.stop();assert pipeline.join(3),'Pipeline threads did not stop'
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/multiobject-benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

