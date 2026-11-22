# SPDX-License-Identifier: MIT
"""Publish a separate, measured CUDA OCR panel; never rewrite old API metrics."""
import base64
import html
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
if (DOCS/'PERFORMANCE_REPORT.json').is_file() and json.loads((DOCS/'PERFORMANCE_REPORT.json').read_text(encoding='utf-8')).get('schema') == 3:
    raise SystemExit('Fresh teacher-review evidence is canonical. Use python -X utf8 tools/build_teacher_review27.py --sync-canonical; historical CUDA panels must not overwrite it.')
raw=json.loads((ROOT/'reports/cuda-benchmark27.json').read_text(encoding='utf-8'))
scene_name='needy-caution-full.png'
rows=[]
for run in raw['quality_runs']:
    scene=run['scenes'][scene_name]
    accuracy=scene['accuracy']
    assert accuracy['characters']==248 and scene['cuda']['kernels_verified'] is True
    rows.append({'quality':run['quality'],'warm_client_ms':round(scene['warm_median_client_ms'],3),
                 'warm_ocr_ms':round(scene['warm_median_ocr_ms'],3),
                 'character_accuracy_percent':accuracy['character_accuracy_percent'],'edits':accuracy['edits'],
                 'image_sha256':scene['image_sha256'],'cuda':scene['cuda']})
assert len(rows)==3 and [r['quality'] for r in rows]==[0,75,100]
assert len({r['image_sha256'] for r in rows})==1
summary={'version':'0.01.27','scope':raw['scope'],'scene':scene_name,'characters':248,
         'rounds':raw['rounds'],'gpu':raw['gpu'],'api_calls':raw['api_calls'],'cache_used':raw['cache_used'],
         'measurements':rows,'source':'reports/cuda-benchmark27.json',
         'limits':'Client timing includes BMP/IPC/helper OCR; excludes capture, translation, overlay and monitor. No monotonic quality or all-game claim.'}
(DOCS/'CUDA_PERFORMANCE_0.01.27.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'path'})
fig,axes=plt.subplots(1,2,figsize=(10,4.2),layout='constrained')
colors=['#c6a79b','#b33431','#dbb7b4'];labels=['0','75 (default)','100']
for ax,field,title,limit,suffix in [(axes[0],'warm_client_ms','Warm client round trip (median, n=5)',300,' ms'),
                                  (axes[1],'character_accuracy_percent','Character transcription: 248 annotated characters',110,'%')]:
    values=[r[field] for r in rows]
    bars=ax.bar(labels,values,color=colors,width=.62)
    ax.set_ylim(0,limit);ax.set_title(title,fontsize=10);ax.set_xlabel('Quality slider (not an accuracy percentage)')
    ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    for bar,value in zip(bars,values):ax.text(bar.get_x()+bar.get_width()/2,value+limit*.018,f'{value:.2f}{suffix}',ha='center',fontsize=10)
fig.suptitle('0.01.27 CUDA OCR · fixed original NEEDY GIRL OVERDOSE image',fontsize=13)
fig.supxlabel('RTX 3070 · 1024 MiB arena budget · no API / capture / translation / overlay',fontsize=9)
figure=DOCS/'cuda-ocr27.svg';fig.savefig(figure);fig.savefig(DOCS/'cuda-ocr27.png',dpi=150);plt.close(fig)
image='data:image/svg+xml;base64,'+base64.b64encode(figure.read_bytes()).decode('ascii')
table_zh='| \u7cfb\u6570 | \u70ed\u8f6e\u5ba2\u6237\u7aef\u4e2d\u4f4d | helper OCR \u4e2d\u4f4d | \u5b57\u7b26\u51c6\u786e\u7387 | \u7f16\u8f91\u5dee\u5f02 |\n|---|---:|---:|---:|---:|\n'
table_en='| Slider | Warm client median | Helper OCR median | Character accuracy | Edit differences |\n|---|---:|---:|---:|---:|\n'
values=''.join(f"| {r['quality']} | {r['warm_client_ms']:.3f} ms | {r['warm_ocr_ms']:.3f} ms | {r['character_accuracy_percent']:.3f}% | {r['edits']} / 248 |\n" for r in rows)
zh='''## 0.01.27 \u72ec\u7acb CUDA OCR \u5b9e\u6d4b

\u672c\u8282\u662f **\u540c\u4e00\u5f20\u539f\u59cb NEEDY GIRL OVERDOSE \u56fa\u5b9a\u56fe\u7247** `needy-caution-full.png`\u30019 \u884c\u6b63\u6587\u3001248 \u4e2a\u624b\u5de5\u6807\u6ce8\u5b57\u7b26\u7684\u672c\u5730\u8bc6\u522b\u5b9e\u9a8c\u3002\u663e\u5361 NVIDIA GeForce RTX 3070\uff088 GiB\uff09\u3001\u9a71\u52a8 617.42\uff0cPP-OCRv6-small\uff0c\u663e\u5b58 arena \u9884\u7b97 1024 MiB\uff0c\u5404\u6863 5 \u6b21\u70ed\u8f6e\uff0c\u65e0\u7f13\u5b58\u3001\u65e0 API\u3002profiling \u9a8c\u8bc1\u4e86\u68c0\u6d4b 190 / \u8bc6\u522b 181 \u4e2a CUDA kernel \u4e8b\u4ef6\uff1b\u4e0d\u662f\u53ea\u68c0\u67e5 provider \u540d\u79f0\u3002

'''+table_zh+values+'''
\u5ba2\u6237\u7aef\u8017\u65f6\u5305\u62ec BMP \u5199\u5165\u3001IPC \u4e0e helper OCR\uff0c**\u4e0d\u542b\u622a\u5c4f\u3001\u8bd1\u6587\u8bf7\u6c42\u3001\u8986\u76d6\u6216\u663e\u793a\u5668\u5448\u73b0**\u3002\u8fd9\u662f\u5c40\u90e8\u6027\u80fd\uff0c\u4e0d\u662f 135–243ms \u5b8c\u6210\u6e38\u620f\u7ffb\u8bd1\u3002\u51b7\u542f\u52a8\u7684\u7ea6 3.23–3.31 \u79d2\u6765\u81ea\u5148\u6267\u884c\u7684\u53e6\u4e00\u5f20\u7a97\u53e3\u539f\u56fe `needy-window-original25.png`\uff0c\u4e0d\u80fd\u5192\u5145\u8868\u5185\u70ed\u8f6e\uff0c\u4e5f\u4e0d\u80fd\u548c\u8be5\u56fe\u672a\u6807\u6ce8\u7684\u51c6\u786e\u7387\u6df7\u7528\u3002

\u540c\u4e00 248 \u5b57\u6750\u6599\u7684 0.01.25 \u7eaf\u672c\u5730\u8bc6\u522b\u4e3a 57.661%\uff0c27 \u9ed8\u8ba4\u6863 98.387%\uff0c\u589e\u52a0 40.726 \u4e2a\u767e\u5206\u70b9\uff1b\u65e7 25 \u4e91\u7aef AI \u6838\u9a8c\u7ed3\u679c 100% \u5c5e\u4e8e\u53e6\u4e00\u6761\u6709\u7f51\u7edc\u8d39\u7528/\u7b49\u5f85\u7684\u8def\u5f84\uff0c\u4e0d\u7528\u4e8e\u5ba3\u79f0\u672c\u5730 CUDA \u8fbe\u5230 100%\u3002\u51c6\u786e\u7387\u6309 NFKC/\u7a7a\u767d\u89c4\u8303\u5316\u540e\u7684\u7f16\u8f91\u8ddd\u79bb\u8ba1\u7b97\uff0c\u53ea\u8bc4\u4ef7\u8f6c\u5f55\uff0c\u4e0d\u8bc4\u4ef7\u4e2d\u6587\u7ffb\u8bd1\u8bed\u4e49\u6216\u5168\u6e38\u620f\u3002

\u63d0\u9ad8\u6ed1\u6761\u4e0d\u4fdd\u8bc1\u51c6\u786e\u7387\u5355\u8c03\u4e0a\u5347\uff1a\u6b64\u56fe 100 \u6863\u4f4e\u4e8e 75 \u6863\u3002\u72ec\u7acb Space Rogue \u539f\u56fe\u5728 GPU 75 \u6863\u4ec5 88.017%\uff0c\u4f4e\u4e8e\u8be5\u50cf\u7d20\u5b57\u4f53\u7684\u4e13\u95e8 CPU \u8def\u5f84\uff0c\u56e0\u6b64\u81ea\u52a8\u6a21\u5f0f\u9047\u5230\u7b26\u5408\u7279\u5f81\u7684\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4f18\u5148 Pixel CPU\u3002\u9884\u7b97\u4e0d\u662f\u6574\u8fdb\u7a0b\u786c\u4e0a\u9650\uff1bnvidia-smi \u91c7\u6837\u662f\u6574\u673a\u684c\u9762\u663e\u5b58\u3002\u6b63\u5f0f\u7aef\u5230\u7aef\u901f\u5ea6\u4ecd\u9700\u53e6\u6d4b\u3002
'''
en='''## 0.01.27 Separate measured CUDA OCR

This is a local OCR experiment on **one original fixed NEEDY GIRL OVERDOSE image**, `needy-caution-full.png`, nine body rows and 248 manually annotated characters. NVIDIA GeForce RTX 3070 (8 GiB), driver 617.42, PP-OCRv6-small, 1024 MiB arena budget, five warm rounds per setting, no cache/API. Profiling verifies 190 detector / 181 recognizer CUDA kernel events, not only provider names.

'''+table_en+values+'''
Client time includes BMP writing, IPC and helper OCR, **excluding capture, translation requests, overlay and monitor presentation**. It is not 135–243ms end-to-end game translation. Approximately 3.23–3.31-second cold starts belong to the other window image run first, `needy-window-original25.png`; do not mix them with this table's warm rounds or attach unsupported accuracy to that image.

On the same 248-character material, 0.01.25 pure local OCR scored 57.661%; the 27 default scores 98.387%, a 40.726-percentage-point increase. The older 25 cloud-AI verified 100% result used a different network/cost/latency path; it is not a claim of 100% local CUDA accuracy. NFKC/whitespace-normalized edit distance measures transcription only, not Chinese translation meaning or all-game accuracy.

Higher settings are not monotonically more accurate: 100 scores below 75 here. A separate original Space Rogue image scores only 88.017% on GPU at 75, below its specialized pixel CPU route, so Auto prioritizes Pixel CPU for detected classic English pixel frames. Arena budget is not a total-process hard cap; nvidia-smi samples desktop-wide memory. End-to-end speed requires separate measurement.
'''
md=MarkdownIt('commonmark',{'html':False}).enable('table')
for english,block in [(False,zh),(True,en)]:
    base=DOCS/'en' if english else DOCS
    standalone=base/'CUDA_PERFORMANCE_0.01.27.md'
    standalone.write_text(block.replace('## ','# ',1)+'\n',encoding='utf-8')
    for name in ('PERFORMANCE_REPORT.md','HIGHLIGHT_FIX_REPORT.md'):
        path=base/name;text=path.read_text(encoding='utf-8')
        text=re.sub('(?ms)^## 0\\.01\\.27 (?:\u72ec\u7acb CUDA OCR \u5b9e\u6d4b|Separate measured CUDA OCR)\\n.*?(?=^## |\\Z)','',text)
        first,_,rest=text.partition('\n');path.write_text(first+'\n\n'+block+'\n'+rest.lstrip(),encoding='utf-8')
    for prefix in ('PERFORMANCE_REPORT','HIGHLIGHT_FIX_REPORT'):
        path=DOCS/(prefix+('.en' if english else '')+'.html');text=path.read_text(encoding='utf-8')
        text=re.sub(r'<section id="cuda27">[\s\S]*?</section>','',text)
        section='<section id="cuda27">'+md.render(block)+'<img alt="CUDA OCR measurements, not translation latency" style="max-width:100%" src="'+image+'"></section>'
        text=text.replace('</header>','</header>'+section,1) if '</header>' in text else text.replace('</h1>','</h1>'+section,1)
        path.write_text(text,encoding='utf-8')
for name in ('PERFORMANCE_REPORT.json','HIGHLIGHT_FIX_REPORT.json'):
    path=DOCS/name;data=json.loads(path.read_text(encoding='utf-8'));data['current_version_cuda_ocr']=summary
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

font=json.loads((ROOT/'reports/font27-replay.json').read_text(encoding='utf-8'))
font_rows=[{'version':row['version'],'font_px':row['snapshot']['font_px'],
            'rows':row['snapshot']['source_rows'],'text_units':row['snapshot']['text_units'],
            'drawable_rows':sum(line.get('drawable',True) for line in row['snapshot']['lines'])} for row in font['rendering']]
assert [(r['version'],r['font_px'],r['rows'],r['drawable_rows'],r['text_units']) for r in font_rows]==[
    ('0.01.26',14,9,9,184),('0.01.27',19,9,9,184)]
font_zh='''## 0.01.27 \u539f\u751f\u5b57\u53f7\u56de\u653e\uff1a\u72ec\u7acb\u663e\u793a\u9a8c\u6536

\u4f7f\u7528 0.01.25 \u4fdd\u5b58\u7684 NEEDY \u4e5d\u884c\u51e0\u4f55\u4e0e\u540c\u4e00\u6bb5\u8bd1\u6587\uff0c\u8c03\u7528\u771f\u5b9e GDI\uff0c\u5e76\u901a\u8fc7\u5b9e\u9645\u7a97\u53e3\u533a\u57df\u906e\u7f69\u5408\u6210\u5230\u5e73\u8272\u6e90\u80cc\u666f\uff1a0.01.26 \u4e3a 14px\uff0c0.01.27 \u4e3a 19px\uff1b\u4e5d\u884c\u5747\u53ef\u7ed8\u5236\uff0c\u6587\u672c\u603b\u91cf\u540c\u4e3a 184 \u4e2a UTF-16 \u5355\u5143\u3002\u4ec5\u5c06\u6781\u77ed\u7eed\u884c\u7684\u4e00\u4e2a\u5b57\u7c07\u653e\u5165\u524d\u884c\u6d4b\u5f97\u4f59\u91cf\uff0c\u6ca1\u6709\u6269\u5927\u884c\u6846\u6216\u8de8\u72ec\u7acb\u5bf9\u8c61\u79fb\u52a8\u6587\u5b57\u3002

\u8fd9\u662f\u4fdd\u5b58\u6570\u636e\u7684\u539f\u751f\u7ed8\u5236\u56de\u653e\uff0c**\u4e0d\u662f\u6e38\u620f\u6b63\u5728\u8fd0\u884c\u7684\u622a\u56fe\uff0c\u4e5f\u4e0d\u662f OCR\u3001\u7ffb\u8bd1\u51c6\u786e\u7387\u6216\u54cd\u5e94\u901f\u5ea6\u63d0\u5347\u8bc1\u636e**\u3002\u56fe\u4e2d 14px / 19px \u662f GDI \u5b57\u53f7\uff0c\u4e0d\u7b49\u4e8e\u53ef\u89c1\u58a8\u8ff9\u9ad8\u3002\u76f8\u5173 GDI \u5b9a\u5411\u56de\u5f52 66 \u9879\u901a\u8fc7\uff1b\u5b8c\u6574\u7248\u672c\u9a8c\u6536\u4ecd\u89c1 TEST_REPORT.json\u3002\u539f\u59cb\u8bc1\u636e\uff1a`reports/font27-replay.json`\u3001`reports/font27-replay-comparison.png`\u3001`reports/font27-tests.log`\u3002
'''
font_en='''## 0.01.27 Native font replay: separate display validation

Replay the saved 0.01.25 NEEDY nine-row geometry and the same translation through real GDI, composited using actual window-region masks on a flat source-colored panel. Version 0.01.26 uses 14px; 0.01.27 uses 19px. All nine rows draw and both retain 184 UTF-16 units. One cluster from the tiny continuation moves into measured spare width on the preceding row, without expanding row rectangles or moving text between separate objects.

This is native rendering of saved data, **not a running-game screenshot or evidence of better OCR, translation accuracy or latency**. 14px/19px denote GDI font size, not visible ink height. The focused GDI regression batch passed 66 tests; full acceptance remains in TEST_REPORT.json. Sources: `reports/font27-replay.json`, `reports/font27-replay-comparison.png`, `reports/font27-tests.log`.
'''
font_image='data:image/png;base64,'+base64.b64encode((ROOT/'reports/font27-replay-comparison.png').read_bytes()).decode('ascii')
for english,block in ((False,font_zh),(True,font_en)):
    base=DOCS/'en' if english else DOCS
    for name in ('PERFORMANCE_REPORT.md','HIGHLIGHT_FIX_REPORT.md'):
        path=base/name;text=path.read_text(encoding='utf-8')
        text=re.sub('(?ms)^## 0\\.01\\.27 (?:\u539f\u751f\u5b57\u53f7\u56de\u653e\uff1a\u72ec\u7acb\u663e\u793a\u9a8c\u6536|Native font replay: separate display validation)\\n.*?(?=^## |\\Z)','',text)
        # Keep GPU first and insert this distinct evidence section before the
        # scheduling simulation, never inside the historic real-game chapter.
        marker='## 0.01.27 Separate scheduling simulation' if english else '## 0.01.27 \u72ec\u7acb\u8c03\u5ea6\u6a21\u62df'
        text=text.replace(marker,block+'\n'+marker,1)
        path.write_text(text,encoding='utf-8')
    for prefix in ('PERFORMANCE_REPORT','HIGHLIGHT_FIX_REPORT'):
        path=DOCS/(prefix+('.en' if english else '')+'.html');text=path.read_text(encoding='utf-8')
        text=re.sub(r'<section id="font27">[\s\S]*?</section>','',text)
        section='<section id="font27">'+md.render(block)+'<img alt="Saved-data native GDI replay, not a running game" style="max-width:100%" src="'+font_image+'"></section>'
        text=text.replace('<section id="probe27">',section+'<section id="probe27">',1)
        path.write_text(text,encoding='utf-8')
for name in ('PERFORMANCE_REPORT.json','HIGHLIGHT_FIX_REPORT.json'):
    path=DOCS/name;data=json.loads(path.read_text(encoding='utf-8'))
    data['current_version_native_replay']={'version':'0.01.27','kind':font['kind'],'source_record_version':font['source_record_version'],
        'measurements':font_rows,'source':'reports/font27-replay.json','focused_tests':66,'test_log':'reports/font27-tests.log'}
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Added independent measured CUDA panel and SVG; historical API/accuracy records retained.')
