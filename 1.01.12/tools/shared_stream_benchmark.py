# SPDX-License-Identifier: MIT
"""Deterministic provider schedule, real TranslationEngine single-flight path."""
import argparse,json,sys,tempfile,threading,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from response_benchmark import summary

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.root.resolve()))
from nkc_galgame_translator.translation import TranslationEngine
import httpx

samples=[];owners=[];count=0
with tempfile.TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(lambda _:None)) as client:
    with TranslationEngine({'api_key':'synthetic-test','unlimited_requests':True,'aggressive_mode':False,'smart_mode':False,'warmup_limit':0,'expert_enabled':False,'use_shared_dictionary':False,'auto_promote_short_terms':False},Path(tmp)/'history.db',client=client) as engine:
        for n in range(12):
            entered=threading.Event();start=threading.Event();first=[];owner=[]
            def request(scope,text,context,on_chunk):
                global count
                count+=1;entered.set();assert start.wait(3)
                time.sleep(.08);on_chunk('\u6b22\u8fce');time.sleep(.40);on_chunk('\u6b22\u8fce\u56de\u6765');return '\u6b22\u8fce\u56de\u6765'
            engine._request=request
            with ThreadPoolExecutor(2) as pool:
                def mark(target):
                    return lambda text:target.append((time.perf_counter()-began)*1000) if not target else None
                leader=pool.submit(engine.translate,'g','en','zh-Hans',f'Welcome {n}',mark(owner))
                assert entered.wait(3)
                follower=pool.submit(engine.translate,'g','en','zh-Hans',f'Welcome {n}',mark(first))
                deadline=time.monotonic()+2
                while engine.get_stats()['shared_requests']<n+1 and time.monotonic()<deadline:time.sleep(.002)
                assert engine.get_stats()['shared_requests']==n+1
                began=time.perf_counter();start.set()
                assert leader.result(3)==follower.result(3)=='\u6b22\u8fce\u56de\u6765'
                owners.append(owner[0]);samples.append(first[0])
assert count==12
result=dict(version=a.root.resolve().name,network_used=False,requests=count,iterations=12,owner=summary(owners),follower=summary(samples),
    scope='Mock provider: first partial at 80ms, final 400ms later. Real single-flight engine; excludes network, OCR and rendering.')
a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
