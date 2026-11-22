# SPDX-License-Identifier: MIT
"""Raw OCR rows must reach paragraph grouping before the object count limit."""
import threading
import time

from nkc_galgame_translator.pipeline import Pipeline


class Capture:
    def __init__(self):
        self.dirty=True
        self.lines=[{'text':f'Alpha line {i}','x':20,'y':30+i*20,'w':220,'h':16,
                     'bg':[0,0,0],'fg':[255,255,255]} for i in range(10)]
        self.lines += [{'text':f'Bottom line {i}','x':20,'y':350+i*20,'w':280,'h':16,
                        'bg':[0,0,0],'fg':[255,255,255]} for i in range(5)]
    def reset(self):self.dirty=True
    def hide_overlay(self):pass
    def capture_ocr(self,*args,**kwargs):
        changed,self.dirty=self.dirty,False
        return {'changed':changed,'lines':[dict(line) for line in self.lines],
                'capture_ms':.1,'ocr_ms':.2}


class Translate:
    def __init__(self):self.calls=[];self.lock=threading.Lock()
    def translate(self,game,source,target,text,chunk,context):
        with self.lock:self.calls.append(text)
        return text


def test_two_object_limit_retains_both_complete_ten_and_five_line_paragraphs():
    core=Capture();engine=Translate();events=[]
    pipeline=Pipeline(core,engine,events.append,interval=.005,settle=0,
                      merge_lines=True,max_objects=2,translation_workers=2)
    try:
        pipeline.start(lambda:(0,0,800,600),'game','en','zh-Hans')
        deadline=time.monotonic()+3
        while len([e for e in events if e[0]=='translation' and e[2][3]])<2 and time.monotonic()<deadline:
            time.sleep(.005)
        assert sorted(engine.calls)==sorted([
            '\n'.join(f'Alpha line {i}' for i in range(10)),
            '\n'.join(f'Bottom line {i}' for i in range(5))])
        assert not [e for e in events if e[0]=='error']
    finally:
        pipeline.stop();pipeline.join(3);pipeline.pool.shutdown(wait=True,cancel_futures=True)
