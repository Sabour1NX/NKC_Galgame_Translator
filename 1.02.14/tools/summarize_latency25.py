"""Summarize paired live-provider measurements without inventing endpoints."""
from pathlib import Path
import hashlib,json,statistics

ROOT=Path(__file__).resolve().parents[1]
records=[]
for pair in range(1,4):
    for version in ('0.01.15','0.01.25'):
        path=ROOT/f'reports/latency-{version}-pair{pair}.json'
        item=json.loads(path.read_text(encoding='utf-8'))
        assert item['success'] and item['network_used'] and not item['capture_included']
        assert item['stats']['api_calls']==2 and len(item['completed'])==2
        records.append({'pair':pair,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            **{key:item[key] for key in ('version','model','measured_at','source_sha256','native_dll_sha256',
                 'capture_interval_ms','settle_ms','first_ocr_ready_ms','first_callback_ms','first_native_paint_ms','complete_ms')},
            'source_characters':sum(len(x['source']) for x in item['completed']),
            'translation_characters':sum(len(x['translation']) for x in item['completed']),
            'api_calls':item['stats']['api_calls'],'prompt_tokens':item['stats']['prompt_tokens'],
            'completion_tokens':item['stats']['completion_tokens']})
assert len({r['source_sha256'] for r in records})==1
assert len({r['model'] for r in records})==1
summary={}
for version in ('0.01.15','0.01.25'):
    items=[r for r in records if r['version']==version]
    summary[version]={'n':len(items),'api_calls':sum(r['api_calls'] for r in items)}
    for key in ('first_ocr_ready_ms','first_callback_ms','first_native_paint_ms','complete_ms'):
        values=[r[key] for r in items]
        summary[version][key]={'median':statistics.median(values),'minimum':min(values),'maximum':max(values),'samples':values}
changes={}
for key in ('first_native_paint_ms','complete_ms'):
    before=summary['0.01.15'][key]['median'];after=summary['0.01.25'][key]['median']
    changes[key]={'median_ms_saved':round(before-after,3),'observed_median_time_reduction_percent':round((before-after)/before*100,3)}
report={'schema':'nkc-observed-paired-latency-v1','baseline':'0.01.15','current':'0.01.25',
    'scene':'Space Rogue original storyline screenshot replay; not a running game',
    'measured_path':'exact source image available -> version OCR -> tracking/settling -> actual DeepSeek streamed translation -> native GDI paint completed',
    'excluded':['screen capture','background reconstruction from captured frames','foreground-window behavior','OS compositor presentation','monitor scanout','network context subtask'],
    'method':'Three sequential old/new pairs on the same machine and image; fresh process and empty database for every sample; versions use their own scheduling defaults; same official provider and model; context web search disabled in both.',
    'not_a_speed_guarantee':'n=3 per version; network/provider variation and changed OCR/output text are uncontrolled. Pair 1 current version is slower. Never label these values game FPS, pure OCR time, or measured screen-to-monitor latency.',
    'excluded_failed_capture_probe':'e2e-baseline15-a.json has no confirmed native paint and is not a successful end-to-end sample. .15 uses desktop capture, not WGC.',
    'summary':summary,'observed_changes':changes,'samples':records}
(ROOT/'reports/latency-comparison25.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# \u4e8c\u8272\u8776 0.01.15 / 0.01.25 \u5b9e\u6d4b\u5ef6\u8fdf\u8fb9\u754c','',
    '**\u672c\u7ec4\u4e0d\u662f\u5b8c\u6574\u6e38\u620f\u7aef\u5230\u7aef\u6d4b\u91cf\u3002** \u539f\u59cb\u622a\u56fe\u5df2\u7ecf\u5728\u5185\u5b58\u4e2d\uff0c\u4ece\u7248\u672c\u81ea\u8eab\u7684 OCR\u3001\u7a33\u5b9a\u7b49\u5f85\u3001\u771f\u5b9e DeepSeek \u7ffb\u8bd1\u5230\u539f\u751f GDI \u5b8c\u6210\u7ed8\u5236\u8ba1\u65f6\uff1b\u4e0d\u542b\u5c4f\u5e55\u91c7\u96c6\u3001\u57fa\u4e8e\u91c7\u96c6\u5e27\u7684\u80cc\u666f\u4fee\u590d\u3001\u7cfb\u7edf\u5408\u6210\u3001\u663e\u793a\u5668\u626b\u63cf\u53ca\u8054\u7f51\u80cc\u666f\u7406\u89e3\u3002',
    '', '| \u6307\u6807\uff08\u4e2d\u4f4d\u6570 / \u6bcf\u7248 3 \u6b21\uff09 | 0.01.15 | 0.01.25 | \u672c\u7ec4\u89c2\u6d4b\u8017\u65f6\u51cf\u5c11 |',
    '|---|---:|---:|---:|']
for key,label in [('first_native_paint_ms','\u9996\u4e2a\u8bd1\u6587\u7247\u6bb5\u539f\u751f\u7ed8\u5236\u5b8c\u6210'),('complete_ms','\u4e24\u4e2a\u6587\u672c\u6846\u6700\u7ec8\u8bd1\u6587\u7ed8\u5236\u5b8c\u6210')]:
    old=summary['0.01.15'][key]['median']/1000;new=summary['0.01.25'][key]['median']/1000
    lines.append(f"| {label} | {old:.3f} s | {new:.3f} s | {changes[key]['observed_median_time_reduction_percent']:.1f}% |")
lines+=['','| \u914d\u5bf9 | .15 \u9996\u7ed8 / \u5b8c\u6574 (s) | .25 \u9996\u7ed8 / \u5b8c\u6574 (s) |','|---|---:|---:|']
for i in range(3):
    old,new=records[i*2:i*2+2]
    lines.append(f"| {i+1} | {old['first_native_paint_ms']/1000:.3f} / {old['complete_ms']/1000:.3f} | {new['first_native_paint_ms']/1000:.3f} / {new['complete_ms']/1000:.3f} |")
lines+=['', '\u7b2c\u4e00\u7ec4\u65b0\u7248\u66f4\u6162\uff0c\u4fdd\u7559\u8be5\u7ed3\u679c\u3002\u6837\u672c\u5c11\u4e14\u7f51\u7edc\u3001\u670d\u52a1\u7aef\u8c03\u5ea6\u3001\u5b9e\u9645\u8bc6\u522b\u53ca\u751f\u6210\u6587\u5b57\u4e0d\u540c\uff0c\u8fd9\u4e9b\u767e\u5206\u6bd4\u53ea\u662f\u672c\u6b21\u6837\u672c\u7684\u4e2d\u4f4d\u6570\u5dee\u5f02\uff0c\u4e0d\u662f\u666e\u904d\u63d0\u901f\u4fdd\u8bc1\u3002',
    '', '\u65e7\u7248\u5b8c\u6574\u7b49\u5f85\u786e\u5b9e\u8fbe\u5230 2 \u79d2\u4ee5\u4e0a\uff0c\u4e0d\u80fd\u7528 150 ms \u7684 OCR \u56fe\u8868\u4e0a\u9650\u4ee3\u8868\u5168\u90e8\u7b49\u5f85\u3002\u5efa\u8bae\u628a\u9759\u6001 OCR \u548c\u771f\u5b9e\u5728\u7ebf\u7ffb\u8bd1\u5ef6\u8fdf\u5206\u5f00\u753b\uff0c\u5728\u7ebf\u7ec4\u7eb5\u8f74\u81f3\u5c11\u8986\u76d6\u672c\u7ec4\u6700\u5927 2.495 \u79d2\uff0c\u53ef\u53d6 3 \u79d2\uff0c\u7981\u6b62\u6cbf\u7528\u56fa\u5b9a 150 ms\u3002',
    '', '\u672c\u7ec4\u5171 12 \u6b21\u5b9e\u9645\u6587\u672c API \u8bf7\u6c42\uff0c\u516d\u6b21\u6d4b\u91cf\u5168\u90e8\u6210\u529f\uff1b\u6bcf\u6b21\u4f7f\u7528\u7a7a\u6570\u636e\u5e93\u4e0e\u65b0\u8fdb\u7a0b\uff0c\u540c\u4e00\u539f\u56fe\u548c\u5b98\u65b9 deepseek-flash \u6a21\u578b\u3002\u539f\u59cb\u6837\u672c\u3001\u65f6\u95f4\u3001\u6e90\u56fe SHA-256 \u548c\u539f\u751f DLL SHA-256 \u5747\u5728 latency-comparison25.json\u3002',
    '', '\u6b64\u524d e2e-baseline15-a.json \u6ca1\u6709\u786e\u8ba4\u539f\u751f\u7ed8\u5236\u5b8c\u6210\uff0c\u4e0d\u7b97\u6210\u529f\u7aef\u5230\u7aef\u6837\u672c\uff1b\u5176\u4e2d\u65e7\u7248\u91c7\u96c6\u4e5f\u4e0d\u80fd\u6807\u6210 WGC\u3002\u5f53\u524d\u9759\u6001\u6e90\u8bca\u65ad\u7ed8\u5236\u7a97\u53e3\u5c5e\u4e8e\u6d4b\u8bd5\u81ea\u8eab\uff0c\u4e0d\u5bf9\u6e38\u620f\u53d1\u9001\u8f93\u5165\u3002']
(ROOT/'reports/LATENCY_MEASUREMENT25.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'summary':summary,'changes':changes,'api_calls':sum(r['api_calls'] for r in records)},ensure_ascii=False))
