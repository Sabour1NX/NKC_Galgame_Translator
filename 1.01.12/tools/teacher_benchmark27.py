# SPDX-License-Identifier: MIT
"""Reproducible release 0.01.15 / 0.01.27 offline comparison.

Each worker imports the selected release's unchanged implementation in an
isolated process. This script never captures the desktop or calls an API.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text).translate(str.maketrans({'“':'"','”':'"','’':"'",'‘':"'"})))


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def score(lines,zones):
    rows=[]
    for zone in zones:
        left,top,right,bottom=zone['box']
        selected=[v for v in lines if left<=v['x']+v['w']/2<right and top<=v['y']+v['h']/2<bottom]
        actual='\n'.join(v['text'] for v in sorted(selected,key=lambda v:(v['y'],v['x'])))
        expected=zone.get('text',zone.get('expected'))
        rows.append({'box':zone['box'],'expected':expected,'actual':actual,'characters':len(normalize(expected)),
                     'edit_distance':distance(normalize(expected),normalize(actual))})
    chars=sum(v['characters'] for v in rows);edits=sum(v['edit_distance'] for v in rows)
    return {'characters':chars,'edits':edits,'character_accuracy_percent':100*(1-edits/chars),'zones':rows}


def load_truth(fixtures):
    truth=json.loads((fixtures/'accuracy-truth.json').read_text(encoding='utf-8'))
    source=json.loads((fixtures/'needy-local25.json').read_text(encoding='utf-8'))
    truth['needy-caution-full.png']=source['scenes']['needy-caution-full.png']['accuracy']
    return truth


def record_call(core,image,language,zones,original_lines):
    started=time.perf_counter();result=core.recognize_image(image,language);elapsed=1000*(time.perf_counter()-started)
    lines=result.get('lines',[])
    return {'elapsed_ms':elapsed,'engine':result.get('engine','windows-native-ocr'),'frame_cache_hit':result.get('frame_cache_hit',False),
        'reported_ocr_ms':result.get('ocr_ms'),'cuda_status':result.get('cuda_status'),'cuda':result.get('cuda'),
        'ocr_stages':result.get('ocr_stages'),'image_rgb_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
        'same_text_and_geometry_as_original':[(x['text'],x['x'],x['y'],x['w'],x['h']) for x in lines]==original_lines,
        'accuracy':score(lines,zones),'lines':lines}


def worker(args):
    root=args.root.resolve();sys.path.insert(0,str(root))
    from PIL import Image
    from nkc_galgame_translator.ocr import OcrCore
    truth=load_truth(args.fixtures);zones=truth[args.scene]
    image_path=args.fixtures/'ocr-private'/args.scene
    hashes={name:sha(root/name) for name in ['nkc_galgame_translator/ocr.py','tools/ocr_helper.py','native/bin/nkc_galgame_translator_core.dll']}
    cuda='cuda_enabled' in inspect.signature(OcrCore).parameters
    if cuda:hashes.update({name:sha(root/name) for name in ['nkc_galgame_translator/cuda_ocr.py','tools/cuda_ocr_helper.py']})
    options={'mode':args.mode,'min_confidence':55}
    if cuda:options.update(refine_workers=4,cuda_enabled=not args.disable_cuda,cuda_memory_mb=1024,cuda_quality=75)
    result={'version':root.name,'round':args.round,'scene':args.scene,'image_sha256':sha(image_path),
        'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'source_root':str(root),'implementation_hashes':hashes,
        'options':options,'python':sys.version,'python_executable':sys.executable,'network_used':False,'api_calls':0,
        'success':False,'warm_revisit':[],'warm_changed_background':[]}
    deps={}
    for folder in [root/'vendor/ocr',root/'vendor/cuda']:
        if folder.exists():
            deps.update({d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(folder)])})
    result['dependencies']=deps
    try:
        with Image.open(image_path) as opened:
            image=opened.convert('RGB');language='ja' if args.scene.startswith('needy') else 'en'
            result['image_size']=image.size;result['language']=language
            started=time.perf_counter()
            with OcrCore(root/'native/bin/nkc_galgame_translator_core.dll',**options) as core:
                initialized=time.perf_counter();result['native_languages']=core._native_languages
                initial=record_call(core,image,language,zones,[])
                result['cold']={**initial,'constructor_ms':1000*(initialized-started),
                    'constructor_plus_first_ocr_ms':1000*(initialized-started)+initial['elapsed_ms']}
                expected=[(x['text'],x['x'],x['y'],x['w'],x['h']) for x in initial['lines']]
                for n in range(args.warm_rounds):
                    result['warm_revisit'].append(record_call(core,image,language,zones,expected))
                used=set()
                for n in range(args.warm_rounds):
                    with image.copy() as changed:
                        color=((37*(n+1))%255,(71*(n+1))%255,(113*(n+1))%255)
                        if color==image.getpixel((0,0)):color=(color[0]^1,color[1],color[2])
                        changed.putpixel((0,0),color)
                        sample=record_call(core,changed,language,zones,expected)
                        sample['changed_pixel']={'x':0,'y':0,'rgb':color}
                        if sample['frame_cache_hit'] or sample['image_rgb_sha256'] in used:raise AssertionError('Changed frame unexpectedly reused a whole-frame cache entry')
                        used.add(sample['image_rgb_sha256']);result['warm_changed_background'].append(sample)
                result['success']=True
    except Exception as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)[:300]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'version':root.name,'scene':args.scene,'round':args.round,'success':result['success'],
        'cold_ms':result.get('cold',{}).get('constructor_plus_first_ocr_ms'),
        'accuracy':result.get('cold',{}).get('accuracy',{}).get('character_accuracy_percent')}),flush=True)
    return 0 if result['success'] else 1


def distribution(values):
    return {'n':len(values),'median_ms':statistics.median(values),'min_ms':min(values),'max_ms':max(values),'samples_ms':values}


def hardware_snapshot():
    hardware={'os':platform.platform(),'cpu':platform.processor(),'python':sys.version,
        'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],text=True).strip()}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            hardware['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    except OSError:pass
    return hardware


def summarize(records,output,hardware):
    report={'schema':1,'comparison':['0.01.15','0.01.27'],'measured_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'hardware':hardware,'network_used':False,'api_calls':0,
        'definitions':{
            'accuracy':'100*(1 - Levenshtein edits / manually labelled source characters). NFKC, whitespace removed, curly quotes normalized, case sensitive; text selected by box centre then y,x sorting.',
            'cold':'Fresh OcrCore instance through first result, including native setup and lazy helper/model initialization. Excludes Python process startup and source file loading. OS file cache is not flushed.',
            'warm_revisit':'Identical already recognized frame. 0.01.27 whole-frame cache is eligible; 0.01.15 has no such cache. Not fresh text recognition.',
            'warm_changed_background':'Unique one-pixel background change, original text unchanged. Whole-frame cache misses are asserted; existing subregion caches remain eligible. Not a claim about unseen text.',
            'timing_scope':'Local image -> release OcrCore result, including IPC and region refinement. No capture, AI transcription, translation API, streaming overlay or display presentation.',
            'pairing':'Release order alternates each round. Each scene/version gets a fresh worker process; all requested rounds and repetitions are preserved in raw records and sample counts.',
            'routes':'Actual auto mode: 0.01.15 legacy CPU/native/portable routing; 0.01.27 optional CUDA on, q75, 1024MiB arena budget, with measured pixel-frame priority. These are system-level comparisons, not equal-hardware-algorithm microbenchmarks.'},
        'source_images':{},'controls_file':'controls.json',
        'scope_note':'Default auto routing is primary. Explicit legacy pixel and CUDA-disabled controls remain separate; no exhaustive best-parameter search.',
        'raw_files':[],'versions':{},'failures':[]}
    for path,record in records:
        report['raw_files'].append(str(path.relative_to(output)))
        if not record['success']:report['failures'].append({'path':str(path),'error':record.get('error')});continue
        group=report['versions'].setdefault(record['version'],{'scenes':{}})['scenes'].setdefault(record['scene'],[])
        group.append(record)
        report['source_images'][record['scene']]='fixtures/'+record['scene']
    for version,value in report['versions'].items():
        totals={}
        for scene,rows in list(value['scenes'].items()):
            first=rows[0]['cold'];scores=[r['cold']['accuracy'] for r in rows]
            value['scenes'][scene]={'image_sha256':rows[0]['image_sha256'],'image_size':rows[0]['image_size'],
                'engine':first['engine'],'cuda_status':first['cuda_status'],'cuda':first['cuda'],'options':rows[0]['options'],
                'accuracy':scores[0],'accuracy_consistent_across_cold_runs':all(s==scores[0] for s in scores),
                'cold_constructor_plus_first':distribution([r['cold']['constructor_ms']+r['cold']['elapsed_ms'] for r in rows]),
                'cold_first_ocr_call':distribution([r['cold']['elapsed_ms'] for r in rows]),
                'warm_revisit':distribution([s['elapsed_ms'] for r in rows for s in r['warm_revisit']]),
                'warm_changed_background':distribution([s['elapsed_ms'] for r in rows for s in r['warm_changed_background']]),
                'revisit_frame_cache_hits':sum(s['frame_cache_hit'] for r in rows for s in r['warm_revisit']),
                'changed_frame_cache_hits':sum(s['frame_cache_hit'] for r in rows for s in r['warm_changed_background']),
                'changed_text_geometry_identical':all(s['same_text_and_geometry_as_original'] for r in rows for s in r['warm_changed_background']),
                'lines':first['lines']}
            bucket='needy' if scene.startswith('needy') else 'space_rogue'
            t=totals.setdefault(bucket,{'characters':0,'edits':0});t['characters']+=scores[0]['characters'];t['edits']+=scores[0]['edits']
        for total in totals.values():total['character_accuracy_percent']=100*(1-total['edits']/total['characters'])
        value['accuracy_by_game']=totals
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def controls(args):
    """Explicit legacy tuning and CUDA-disabled controls; never replace defaults."""
    output=args.output_dir.resolve();(output/'raw-controls').mkdir(parents=True,exist_ok=True)
    recipes=[(args.baseline_root,'pixel',False,name) for name in load_truth(args.fixtures)]
    recipes.extend([(args.baseline_root,'native',False,'needy-caution-full.png'),
                    (args.current_root,'auto',True,'needy-caution-full.png')])
    result={'purpose':'Additional explicit settings controls, separate from default product routing. No exhaustive best-parameter search.',
            'network_used':False,'api_calls':0,'controls':[]}
    for root,mode,disable_cuda,scene in recipes:
        root=root.resolve();identity=f'{root.name}-{mode}-{Path(scene).stem}'
        path=output/'raw-controls'/f'{identity}.json'
        if path.exists():raise RuntimeError('Refusing to overwrite control: '+str(path))
        command=[sys.executable,str(Path(__file__).resolve()),'--worker','--root',str(root),'--mode',mode,
                 '--fixtures',str(args.fixtures),'--output',str(path),'--scene',scene,'--round','1',
                 '--warm-rounds',str(args.warm_rounds)]
        if disable_cuda:command.append('--disable-cuda')
        run=subprocess.run(command,cwd=root,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=240,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        path.with_suffix('.stderr.log').write_text(run.stderr,encoding='utf-8');print(run.stdout.strip(),flush=True)
        raw=json.loads(path.read_text(encoding='utf-8'));entry={'id':identity,'raw_file':str(path.relative_to(output)),
            'version':root.name,'scene':scene,'options':raw['options'],'success':raw['success'],'error':raw.get('error')}
        if raw['success']:
            entry.update(engine=raw['cold']['engine'],accuracy=raw['cold']['accuracy'],
                cold_constructor_plus_first_ms=raw['cold']['constructor_ms']+raw['cold']['elapsed_ms'],
                warm_revisit=distribution([x['elapsed_ms'] for x in raw['warm_revisit']]),
                warm_changed_background=distribution([x['elapsed_ms'] for x in raw['warm_changed_background']]),
                changed_frame_cache_hits=sum(x['frame_cache_hit'] for x in raw['warm_changed_background']),
                changed_text_geometry_identical=all(x['same_text_and_geometry_as_original'] for x in raw['warm_changed_background']))
        result['controls'].append(entry)
        legacy=[v for v in result['controls'] if v['version']=='0.01.15' and v['options']['mode']=='pixel'
                and not v['scene'].startswith('needy') and v['success']]
        if len(legacy)==3:
            chars=sum(v['accuracy']['characters'] for v in legacy);edits=sum(v['accuracy']['edits'] for v in legacy)
            result['legacy_pixel_space_rogue_total']={'characters':chars,'edits':edits,'character_accuracy_percent':100*(1-edits/chars)}
        (output/'controls.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


def e2e(args):
    """Opt-in bounded live-provider probe with no visible window or overlay."""
    current=args.current_root.resolve();output=args.output_dir.resolve();directory=output/'e2e-final'
    directory.mkdir(parents=True,exist_ok=True)
    if not args.config or not (args.config/'config/local.json').is_file():
        raise ValueError('--config must name the private application ROOT containing config/local.json')
    if not 1<=args.pairs<=3:raise ValueError('Live probe is limited to at most three pairs')
    sys.path.insert(0,str(current))
    from nkc_galgame_translator.config_store import ConfigStore
    config=ConfigStore(args.config.resolve()).load()
    if config.get('base_url','').rstrip('/') not in {'https://api.deepseek.com','https://api.deepseek.com/v1'}:
        raise ValueError('The benchmark only permits the configured official DeepSeek endpoint')
    if not config.get('api_key'):raise ValueError('No saved API credential')
    # The credential is never serialized or passed in a command-line argument.
    del config
    base_probe=current/'tools/end_to_end_probe.py';probe=directory/'bounded_probe27.py'
    source_original=args.fixtures/'ocr-private/spacerogue-game.png';source=directory/'e2e-original-frame.png'
    shutil.copy2(source_original,source)
    source_code=base_probe.read_text(encoding='utf-8')
    if source_code.count('max_requests=4')!=1:raise ValueError('Unexpected probe request-limit declaration')
    # This changes only the diagnostic harness's request budget. The release
    # OCR, pipeline, translation and native implementations remain untouched.
    source_code=source_code.replace('max_requests=4','max_requests=1')
    edits={
        'if redraw:core.show_overlay(list(state.rendered.values()))':'if redraw:pass  # Headless callback benchmark: never display an overlay.',
        'result=core.recognize_image(im,language)':"result=core.recognize_image(im,language)\n        # Keep full-frame OCR input; select the declared dialogue area only for translation.\n        result={**result,'lines':[v for v in result['lines'] if 0<=v['x']+v['w']/2<450 and 70<=v['y']+v['h']/2<440]}",
        'if expected and len(done)>=expected and len(finals)>=expected:':'if expected and len(done)>=expected:',
        "'exact source pixels -> release OCR/pipeline -> real provider -> diagnostic native GDI paint'":"'exact source pixels -> release OCR/pipeline -> real provider -> UI event queue; no capture or paint'",
        "record['limitation']='Native paint completion is observed, not monitor presentation. Sequential live API samples include network/provider variance; no claim of provider acceleration.'":"record['limitation']='Only translation callbacks observed in the UI event queue; no capture, native paint, DWM or monitor presentation is measured. Live API variance is uncontrolled.'\n    record['native_paint_measured']=False\n    record['complete_callback_ms']=record['complete_ms']",
    }
    for old,new in edits.items():
        if source_code.count(old)!=1:raise ValueError('Unexpected headless probe adapter boundary')
        source_code=source_code.replace(old,new)
    probe.write_text(source_code,encoding='utf-8')
    report={'comparison':['0.01.15','0.01.27'],'network_used':True,'real_running_game':False,
        'scope':'Complete exact source screenshot -> actual release pixel OCR -> declared left-dialogue region selection in the test source adapter -> actual tracking/real streaming API -> translation callbacks observed in the UI event queue. No capture, painting, network context, AI vision or DWM/monitor presentation timing.',
        'model':'from explicitly supplied private configuration; per-run record preserves model name',
        'per_run_request_limit':1,'maximum_pairs':3,'context_search':False,
        'timing_start':'immediately before pipeline.start','native_paint_measured':False,
        'complete_ms_definition':'Last final translation callback consumed from the UI event queue; not rendering or screen presentation.',
        'limitations':['Live-provider/network variation is uncontrolled. Three pairs are descriptive, not a statistically established service speedup.',
                      'Default release capture polling/stabilization values are retained. A frozen source adapter excludes actual screen capture.',
                      'Release prompts differ; this measures product paths, not identical model payloads. Event-queue observation ticks are 40ms for 0.01.15 and 16ms for 0.01.27.',
                      'No visible window or overlay is shown; first_native_paint_ms remains null.'],
        'source_sha256':sha(source),'source_original_sha256':sha(source_original),'source_crop_box':None,'translation_region':[0,70,450,440],
        'probe_sha256':sha(probe),'base_probe_sha256':sha(base_probe),'preflight':[],
        'samples':[],'versions':{},'failures':[]}
    roots=[args.baseline_root.resolve(),current]
    for root in roots:
        path=directory/f'{root.name}-dry.json'
        if path.exists():raise RuntimeError('Refusing to overwrite preflight evidence')
        command=[sys.executable,str(probe),'--root',str(root),'--config',str(args.config.resolve()),
                 '--image',str(source),'--output',str(path),'--static-source','--dry-run']
        run=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        path.with_suffix('.stderr.log').write_text(run.stderr,encoding='utf-8')
        if not path.exists():raise RuntimeError('Preflight failed without output')
        raw=json.loads(path.read_text(encoding='utf-8'))
        report['preflight'].append({'version':root.name,'raw_file':str(path.relative_to(output)),
                                   'success':raw['success'],'objects':raw.get('expected_objects')})
        if not raw['success'] or raw.get('expected_objects')!=1:
            (output/'e2e-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            raise RuntimeError('Preflight did not yield one completed object; no live API calls were made')
    for pair in range(args.pairs):
        for root in (roots if pair%2==0 else roots[::-1]):
            path=directory/f'{root.name}-pair{pair+1}.json'
            if path.exists():raise RuntimeError('Refusing to overwrite live measurement')
            command=[sys.executable,str(probe),'--root',str(root),'--config',str(args.config.resolve()),
                     '--image',str(source),'--output',str(path),'--static-source']
            run=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=100,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            path.with_suffix('.stderr.log').write_text(run.stderr,encoding='utf-8')
            print(run.stdout.strip(),flush=True)
            if not path.exists():raise RuntimeError('Probe failed before saving a record; inspect its local stderr log')
            raw=json.loads(path.read_text(encoding='utf-8'))
            entry={'pair':pair+1,'version':root.name,'raw_file':str(path.relative_to(output)),
                **{k:raw.get(k) for k in ['success','model','first_ocr_ready_ms','first_callback_ms','first_native_paint_ms','complete_ms','errors','capture_interval_ms','settle_ms']},
                'session_requests':raw.get('stats',{}).get('session_requests'),
                'prompt_tokens':raw.get('stats',{}).get('prompt_tokens'),
                'completion_tokens':raw.get('stats',{}).get('completion_tokens'),
                'observer_tick_ms':40 if root.name=='0.01.15' else 16,
                'source_text_sha256':hashlib.sha256('\n'.join(v['source'] for v in raw['completed']).encode('utf-8')).hexdigest(),
                'implementation_hashes':{name:sha(root/name) for name in ['nkc_galgame_translator/pipeline.py','nkc_galgame_translator/translation.py','nkc_galgame_translator/tuning.py','native/bin/nkc_galgame_translator_core.dll']}}
            report['samples'].append(entry)
            if not entry['success']:report['failures'].append(entry)
            report['total_session_requests']=sum(v['session_requests'] or 0 for v in report['samples'])
            report['source_text_identical_across_samples']=len({v['source_text_sha256'] for v in report['samples']})==1
            for version in ['0.01.15','0.01.27']:
                records=[v for v in report['samples'] if v['version']==version and v['success']]
                if records:report['versions'][version]={k:distribution([r[k] for r in records]) for k in ['first_callback_ms','complete_ms']}
            (output/'e2e-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            if not entry['success']:return 1
    return 0


def refresh_summary(args):
    output=args.output_dir.resolve();records=[]
    for path in sorted((output/'raw').glob('*.json')):
        raw=json.loads(path.read_text(encoding='utf-8'));records.append((path,raw))
        if raw.get('cold'):
            cold=raw['cold'];total=cold['constructor_ms']+cold['elapsed_ms']
            if total!=cold['constructor_plus_first_ocr_ms']:
                cold['harness_wall_including_accuracy_evaluation_ms']=cold['constructor_plus_first_ocr_ms']
                cold['constructor_plus_first_ocr_ms']=total
                raw['timing_reconciliation']='Cold total is the sum of measured constructor and OCR-call durations; grading overhead is retained separately and excluded.'
                path.write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
    hardware=hardware_snapshot()
    if args.load_note:hardware['load_conditions']=args.load_note
    summarize(records,output,hardware)
    (output/'fixtures').mkdir(exist_ok=True)
    truth=load_truth(args.fixtures)
    for name in truth:shutil.copy2(args.fixtures/'ocr-private'/name,output/'fixtures'/name)
    (output/'fixtures/truth.json').write_text(json.dumps(truth,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--root',type=Path)
    parser.add_argument('--controls',action='store_true')
    parser.add_argument('--e2e',action='store_true');parser.add_argument('--config',type=Path,help='Private app root, not a JSON filename')
    parser.add_argument('--summarize-only',action='store_true');parser.add_argument('--load-note',default='')
    parser.add_argument('--mode',choices=['auto','pixel','native'],default='auto')
    parser.add_argument('--disable-cuda',action='store_true')
    parser.add_argument('--baseline-root',type=Path);parser.add_argument('--current-root',type=Path)
    parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--scene');parser.add_argument('--round',type=int,default=0)
    parser.add_argument('--pairs',type=int,default=3);parser.add_argument('--warm-rounds',type=int,default=5)
    args=parser.parse_args();args.fixtures=args.fixtures.resolve()
    if args.worker:return worker(args)
    if args.controls:return controls(args)
    if args.e2e:return e2e(args)
    if args.summarize_only:return refresh_summary(args)
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'fixtures').mkdir(exist_ok=True)
    for scene in load_truth(args.fixtures):shutil.copy2(args.fixtures/'ocr-private'/scene,output/'fixtures'/scene)
    (output/'fixtures/truth.json').write_text(json.dumps(load_truth(args.fixtures),ensure_ascii=False,indent=2),encoding='utf-8')
    hardware=hardware_snapshot()
    if args.load_note:hardware['load_conditions']=args.load_note
    roots=[args.baseline_root.resolve(),args.current_root.resolve()];records=[]
    for round_no in range(args.pairs):
        for scene in load_truth(args.fixtures):
            for root in (roots if round_no%2==0 else roots[::-1]):
                path=output/'raw'/f'{root.name}-{Path(scene).stem}-r{round_no+1}.json'
                if path.exists():raise RuntimeError('Refusing to overwrite measured sample: '+str(path))
                command=[sys.executable,str(Path(__file__).resolve()),'--worker','--root',str(root),
                         '--fixtures',str(args.fixtures),'--output',str(path),'--scene',scene,
                         '--round',str(round_no+1),'--warm-rounds',str(args.warm_rounds)]
                run=subprocess.run(command,cwd=root,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=240,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                (output/'raw'/f'{path.stem}.stderr.log').write_text(run.stderr,encoding='utf-8')
                print(run.stdout.strip(),flush=True)
                record=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'success':False,'error':{'type':'worker_exit','message':str(run.returncode)}}
                records.append((path,record));summarize(records,output,hardware)
    return 0


if __name__=='__main__':raise SystemExit(main())
