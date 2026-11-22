"""Real capture/OCR/provider/native-paint probe over a labeled screenshot replay.

The local fixture window is not a running game. Timing starts after mapping
the source pixels. Provider timing is observational, not a controlled service
benchmark. Credentials are read from an explicitly supplied private config.
"""
import argparse,json,queue,sys,time,os,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
p.add_argument('--config',type=Path,required=True);p.add_argument('--image',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--static-source',action='store_true',help='Exclude capture; recognize exact same source pixels. Does not claim monitor visibility.')
p.add_argument('--render-origin',type=int,nargs=2,help='On-desktop diagnostic overlay origin; never activates or inputs into another app.')
p.add_argument('--dry-run',action='store_true',help='Synthetic translations; no provider request.')
a=p.parse_args()
a.root=a.root.resolve()
sys.path.insert(0,str(a.root.resolve()))
from nkc_galgame_translator.windows import enable_dpi,client_rect
enable_dpi()
import tkinter as tk
from PIL import Image,ImageTk
from nkc_galgame_translator.config_store import ConfigStore
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.tuning import TUNING_DEFAULTS
cfg=ConfigStore(a.config).load() if not a.dry_run else {'api_key':'synthetic-test-only','model':'deepseek-flash','base_url':'https://api.deepseek.com'}
assert cfg.get('api_key')
cfg.update(TUNING_DEFAULTS,max_requests=4,unlimited_requests=False,max_retries=0,
    offline_only=False,aggressive_mode=True,context_web_search=False,request_timeout=45)
a.output.parent.mkdir(parents=True,exist_ok=True)
assert not a.output.exists() and not a.output.with_suffix('.sqlite3').exists()
app=tk.Tk();app.title('Nishokuchou latency test - original screenshot replay, NOT a game')
im=Image.open(a.image).convert('RGB')
if a.static_source:
    app.withdraw();app.update()
else:
    photo=ImageTk.PhotoImage(im)
    tk.Label(app,image=photo,borderwidth=0,highlightthickness=0).pack()
    app.geometry('+20+20');app.resizable(False,False);app.update();app.focus_force();app.update()
hwnd=int(app.frame(),16);events=queue.SimpleQueue();state=OverlayState()
core=OcrCore(a.root/'native/bin/nkc_galgame_translator_core.dll',mode='pixel')
engine=TranslationEngine(cfg,a.output.with_suffix('.sqlite3'))
if a.static_source:
    # Test adapter only: production OCR code for each imported release is
    # unchanged. One exact frame, then unchanged observations for settling.
    seen=False
    def captured_source(x,y,w,h,language='en'):
        global seen
        if seen:return {'changed':False,'lines':[],'capture_ms':0,'ocr_ms':0}
        seen=True
        result=core.recognize_image(im,language)
        for line in result['lines']:
            line['x']+=x;line['y']+=y
            if '_source_ink' in line:
                ix,iy,iw,ih=line['_source_ink'];line['_source_ink']=[ix+x,iy+y,iw,ih]
        return {**result,'changed':True,'capture_ms':0}
    core.capture_ocr=captured_source
else:
    core.set_target(hwnd,os.getpid())
core.set_overlay_font('Microsoft YaHei UI')
if a.dry_run:
    def synthetic(scope,masked,context,on_chunk,**kwargs):
        text='\u8fd9\u662f\u6d4b\u8bd5\u8bd1\u6587\u3002'*4
        if on_chunk:on_chunk(text)
        return text
    engine._request=synthetic
if hasattr(core,'set_overlay_options'):core.set_overlay_options(capture_translations=True)
record={'version':a.root.name,'model':cfg['model'],'kind':'source-fixture window + actual WGC/OCR/API/native paint',
    'real_running_game':False,'network_used':not a.dry_run,'source_file':a.image.name,
    'timing_start':'mapped original pixels immediately before pipeline.start',
    'capture_interval_ms':cfg['capture_interval_ms'],'settle_ms':cfg['settle_ms'],
    'network_context_enabled':False,'completed':[],'errors':[],'ocr_samples_ms':[],
    'first_callback_ms':None,'first_native_paint_ms':None,'complete_ms':None}
record['native_dll_sha256']=hashlib.sha256((a.root/'native/bin/nkc_galgame_translator_core.dll').read_bytes()).hexdigest()
record['source_sha256']=hashlib.sha256(a.image.read_bytes()).hexdigest()
record['measured_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
if a.static_source:
    record.update(kind='exact source pixels -> release OCR/pipeline -> real provider -> diagnostic native GDI paint',
                  capture_included=False,monitor_visibility_measured=False,
                  timing_start='immediately before pipeline.start; exact source image already loaded')
else:
    record.update(kind='screenshot replay -> release-specific capture/OCR -> real provider -> native GDI paint',
                  capture_included=True,monitor_visibility_measured=False)
pipe=Pipeline(core,engine,events.put,interval=cfg['capture_interval_ms']/1000,
    settle=cfg['settle_ms']/1000,translation_workers=cfg['translation_workers'],
    max_missing=cfg['track_missing_frames'],show_source_label=False,show_translation_brackets=False)
start=time.perf_counter();done={};end=False
provider=(lambda:(*(a.render_origin or [-20000,-20000]),*im.size)) if a.static_source else (lambda:client_rect(hwnd))
pipe.start(provider,'Space Rogue fixed comparison','en','zh-Hans',
    'Science fiction role-playing game. Translate the entire visible source faithfully.')
def tick():
    global end
    redraw=False
    while True:
        try:kind,generation,payload=events.get_nowait()
        except queue.Empty:break
        elapsed=round((time.perf_counter()-start)*1000,3)
        if kind=='clear':state.clear();redraw=True
        elif kind=='objects':
            redraw=state.apply_objects(payload) or redraw
            record['expected_objects']=len([obj for obj in payload if not obj['line'].get('_preserve_source')])
        elif kind=='translation':
            identity,line,original,final=payload
            if line.get('text') and record['first_callback_ms'] is None:record['first_callback_ms']=elapsed
            redraw=state.apply_translation(identity,line) or redraw
            if final:
                done[identity]={'source':original,'translation':line['text'],'complete_callback_ms':elapsed}
                if len(done)>=record.get('expected_objects',2):record.setdefault('all_translations_ready_ms',elapsed)
        elif kind=='timing':
            record.setdefault('first_ocr_ready_ms',elapsed)
            if payload.get('ocr_ms'):record['ocr_samples_ms'].append(payload['ocr_ms'])
        elif kind in ('error','line_error'):record['errors'].append(str(payload)[:500])
    if redraw:core.show_overlay(list(state.rendered.values()))
    snap=core.native.overlay_snapshot()
    record['overlay']=snap
    painted=[r for r in snap['regions'] if r['text_units'] and r['fits'] and ('paint' not in r or r['paint'].get('commits',0)>0) and not r.get('background_suppressed')]
    if painted and record['first_native_paint_ms'] is None:
        record['first_native_paint_ms']=round((time.perf_counter()-start)*1000,3)
    finals=[r for r in painted if r.get('final')]
    expected=record.get('expected_objects',2)
    if expected and len(done)>=expected and len(finals)>=expected:
        record['complete_ms']=round((time.perf_counter()-start)*1000,3);record['overlay']=snap;end=True
    if record['errors'] or time.perf_counter()-start>(10 if a.dry_run else 65):end=True
    if end:app.quit()
    else:app.after(40 if a.root.name=='0.01.15' else 16,tick)
app.after(10,tick)
try:app.mainloop()
finally:
    pipe.stop();pipe.join(3);record['completed']=list(done.values());record['stats']=engine.get_stats()
    record['success']=bool(record.get('expected_objects')) and len(done)>=record['expected_objects'] and record['complete_ms'] is not None and not record['errors']
    record['limitation']='Native paint completion is observed, not monitor presentation. Sequential live API samples include network/provider variance; no claim of provider acceleration.'
    engine.close();core.close();app.destroy()
    a.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:record.get(k) for k in ('version','success','first_ocr_ready_ms','first_callback_ms','first_native_paint_ms','complete_ms','errors')},ensure_ascii=False))
