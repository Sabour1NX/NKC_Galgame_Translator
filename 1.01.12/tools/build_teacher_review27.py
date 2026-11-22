# SPDX-License-Identifier: MIT
"""Build an offline teacher-review portal from explicitly scoped public evidence.

Only this version's teacher-review measurements are plotted. No credentials,
private profiles, old performance summaries, network calls or packaging.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import io
import json
import mimetypes
from pathlib import Path
import re
import statistics
import sys
import subprocess
from datetime import datetime
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
EVIDENCE=ROOT/'reports/teacher-review27'
OUT=DOCS/'teacher-review27'
VERSION='0.01.27'
BASELINE='0.01.15'
MD=MarkdownIt('commonmark',{'html':False}).enable('table')
CSS='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:#f5f4ef;color:#162a32;font:16px/1.8 "Segoe UI","Microsoft YaHei UI",sans-serif}a{color:#007d79;text-decoration:none}a:hover{text-decoration:underline}header.site{background:#122a33;color:white;position:sticky;top:0;z-index:5;border-bottom:1px solid #3b5057}.top{max-width:1280px;margin:auto;padding:15px 28px;display:flex;align-items:center;justify-content:space-between;gap:24px}.brand{font-weight:700;letter-spacing:.07em;color:white;white-space:nowrap}.brand small{font-weight:400;color:#a3bdc4;margin-left:16px;font-size:12px}nav{display:flex;gap:22px;flex-wrap:wrap}nav a{color:#d7e6e8;font-size:14px}nav a.active{color:#69e1cf}main{max-width:1250px;margin:auto;padding:42px 30px 72px}.eyebrow{font-size:12px;letter-spacing:.17em;text-transform:uppercase;color:#007d79;font-weight:700}.hero{padding:38px 0 42px;border-bottom:1px solid #ccd7d6;margin-bottom:34px}.hero h1{font-size:clamp(36px,5.1vw,68px);line-height:1.2;letter-spacing:-.055em;margin:18px 0 22px;max-width:1000px}.hero p{max-width:840px;font-size:19px;color:#52646a}.hero .approved{font-size:13px;letter-spacing:.14em;color:#007d79}.pill{display:inline-block;padding:4px 11px;border-radius:24px;font-size:12px;background:#e0eeeb;color:#12655d;margin:3px 6px 3px 0}.pill.pending{background:#f3e5cd;color:#7f601e}.pill.negative{background:#f1ddd5;color:#96462c}.button{display:inline-block;background:#007d79;color:white;border-radius:8px;padding:11px 19px;font-weight:600;margin:6px 10px 6px 0}.button.secondary{background:#e1e9e5;color:#145450}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.card{background:white;border:1px solid #d9e1dd;border-radius:12px;padding:25px}.card h3{margin:8px 0 10px;font-size:22px;line-height:1.5}.card p{margin:8px 0;color:#56696d}.number{font-size:38px;font-weight:650;line-height:1.2;letter-spacing:-.04em}.meta{font-size:12px;color:#647a7e}.step{font:600 13px/1.3 Consolas,monospace;color:#168478}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-top:42px}h2{font-size:29px;line-height:1.4;letter-spacing:-.025em;margin:10px 0 18px}h3{font-size:21px;margin:28px 0 10px}section{margin:30px 0 44px;scroll-margin-top:90px}.note{padding:17px 20px;border-left:4px solid #07867e;background:#eaf1ec;color:#3f5b5b;margin:20px 0}.note.amber{border-color:#a78439;background:#f4ecda}.note p{margin:4px 0}.lede{font-size:18px;max-width:930px;color:#4a6066}.rule{border:0;border-top:1px solid #ccd7d6;margin:35px 0}table{width:100%;border-collapse:collapse;font-size:14px;margin:17px 0}td,th{text-align:left;padding:12px 14px;border-bottom:1px solid #dce3df;vertical-align:top}th{font-size:12px;color:#4e666b;letter-spacing:.04em;background:#edf0e9}tbody tr:hover{background:#f0f6f2}.table-wrap{overflow:auto}pre{background:#152b34;color:#d4e8e5;padding:20px;border-radius:9px;overflow:auto;font:13px/1.7 Consolas,monospace}code{font-family:Consolas,monospace;font-size:.89em;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}blockquote{margin:18px 0;padding:10px 18px;background:#edf1e9;border-left:3px solid #9ba995}img{max-width:100%;height:auto}.chart{background:white;border:1px solid #d9e1dd;border-radius:12px;padding:18px;margin:24px 0}.chart svg{width:100%;height:auto;display:block}.diagram{overflow-x:auto;background:white;border:1px solid #d9e1dd;border-radius:12px;padding:20px}.diagram svg{display:block;min-width:850px;width:100%;height:auto}.diagram .box{fill:#f7faf7;stroke:#c2d6d0}.diagram .accent{fill:#e1f1eb;stroke:#168478}.diagram .dark{fill:#18333e;stroke:#18333e}.diagram .title{font:600 17px "Segoe UI","Microsoft YaHei UI",sans-serif;fill:#16373b}.diagram .label{font:13px "Segoe UI","Microsoft YaHei UI",sans-serif;fill:#506a6c}.diagram .light{fill:#e2f0ef}.diagram .arrow{stroke:#3f8981;stroke-width:2;fill:none}.gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.shot{background:white;border:1px solid #d4dfda;border-radius:10px;overflow:hidden}.shot .thumb{height:210px;background:#e8ece8;display:flex;align-items:center;justify-content:center;overflow:hidden}.shot img{object-fit:contain;width:100%;height:100%}.shot .caption{padding:16px}.shot h3{font-size:16px;margin:5px 0}.shot .caption p{font-size:12px;color:#63777b;margin:5px 0}.toc{background:white;padding:20px;border:1px solid #dbe2db;border-radius:10px;position:sticky;top:90px;align-self:start;max-height:82vh;overflow:auto}.toc a{display:block;font-size:13px;padding:5px 2px}.manual-layout{display:grid;grid-template-columns:235px minmax(0,1fr);gap:30px}.manual article{background:white;border:1px solid #dce3df;border-radius:12px;padding:28px;margin-bottom:24px;scroll-margin-top:90px}.manual h1{font-size:29px;line-height:1.4}.manual h2{font-size:23px}.manual h3{font-size:19px}.manual table{display:block;overflow:auto}.manual pre{font-size:12px}.manual .chapter{font-size:11px;letter-spacing:.12em;color:#19867c}.footer{border-top:1px solid #cedbd5;padding:25px 0;color:#687e80;font-size:12px;margin-top:50px}.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#52666a}.swatch{width:11px;height:11px;border-radius:2px;display:inline-block;background:#a6b8be;margin-right:5px}.swatch.current{background:#008e81}details{background:white;border:1px solid #d8e0dc;border-radius:8px;padding:14px 18px;margin:12px 0}summary{font-weight:600;cursor:pointer}.empty{padding:30px;background:#eee9dc;color:#786b51;border:1px dashed #c3b48a;border-radius:10px}@media(max-width:950px){.grid,.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}.top{align-items:flex-start;gap:12px}.brand small{display:none}nav{gap:12px}.manual-layout{grid-template-columns:1fr}.toc{position:static;max-height:none}.toc a{display:inline-block;padding-right:12px}}@media(max-width:620px){.top{padding:12px 18px;display:block}nav{margin-top:8px;flex-wrap:nowrap;overflow:auto;white-space:nowrap;padding-bottom:3px}main{padding:24px 18px}.hero{padding-top:16px}.hero p{font-size:17px}.grid,.grid.two,.gallery{grid-template-columns:1fr}.card{padding:21px}.manual article{padding:20px 16px}.shot .thumb{height:245px}.section-head{display:block}h2{font-size:25px}.hero h1{font-size:40px}.number{font-size:34px}}@media print{header.site,.toc{position:static}.manual-layout{display:block}main{padding:0;max-width:none}.card,article,.chart,.shot{break-inside:avoid}nav{display:none}a{color:#173c3d}.diagram svg{min-width:0}.hero h1{font-size:40px}}'''

def esc(value):return html.escape(str(value),quote=True)
def load(path,default=None):
    if not path.is_file():return default
    return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')
def uri(path,thumbnail=False):
    if thumbnail:
        with Image.open(path) as image:
            image.thumbnail((560,380));buffer=io.BytesIO();image.convert('RGB').save(buffer,format='JPEG',quality=88)
        return 'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')
    return 'data:'+str(mimetypes.guess_type(path.name)[0] or 'image/png')+';base64,'+base64.b64encode(path.read_bytes()).decode('ascii')

def shell(title,body,active='index',language='zh-CN',depth=''):
    links=[('index','\u8bc4\u5ba1\u603b\u89c8'),('performance','\u6027\u80fd\u4e0e\u65b9\u6cd5'),('gallery','UI \u56fe\u5e93'),('architecture','\u7ed3\u6784\u4e0e\u63a5\u53e3'),('manual.zh','\u5b8c\u6574\u624b\u518c'),('manual.en','English')]
    if language=='en':links=[('index','Review home'),('performance.en','Performance'),('gallery','UI gallery'),('architecture','Architecture'),('manual.zh','\u4e2d\u6587\u624b\u518c'),('manual.en','English manual')]
    nav=''.join(f'<a class="{"active" if key==active else ""}" href="{depth}{key}.html">{label}</a>' for key,label in links)
    return '<!doctype html><html lang="'+language+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:"><title>'+esc(title)+' · \u4e8c\u8272\u8776 0.01.27</title><style>'+CSS+'</style></head><body><header class="site"><div class="top"><a class="brand" href="'+depth+'index.html">\u4e8c\u8272\u8776 <small>NISHOKUCHOU / REVIEW 27</small></a><nav>'+nav+'</nav></div></header><main>'+body+'<footer class="footer">\u4e8c\u8272\u8776 · \u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1 / Windows x64<br>0.01.15 \u57fa\u7ebf → 0.01.27 \u5f53\u524d\u5b9e\u73b0\u3002\u79bb\u7ebf\u8bc4\u5ba1\u8d44\u6599\uff1b\u8bf7\u6c42/\u622a\u56fe\u8303\u56f4\u6309\u6bcf\u9879\u8bc1\u636e\u6807\u6ce8\u3002\u65e0\u9065\u6d4b\u3001\u65e0\u5916\u90e8\u9875\u9762\u8d44\u6e90\u3002</footer></main></body></html>'

def hero(kicker,title,description):
    return '<div class="hero"><div class="eyebrow">'+kicker+'</div><h1>'+title+'</h1><p>'+description+'</p></div>'
def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def status(value,negative=False):return '<span class="pill'+(' negative' if negative else '')+'">'+esc(value)+'</span>'

def diagram(kind):
    def box(x,y,title,lines,dark=False):
        cls='dark' if dark else 'accent'
        return f'<rect x="{x}" y="{y}" width="310" height="110" rx="12" class="{cls}"/><text x="{x+16}" y="{y+29}" class="title'+(' light' if dark else '')+'">'+esc(title)+'</text>'+''.join(f'<text x="{x+16}" y="{y+57+i*23}" class="label'+(' light' if dark else '')+'">'+esc(line)+'</text>' for i,line in enumerate(lines))
    def arrow(path,dashed=False):return '<path class="arrow" d="'+path+'" marker-end="url(#'+kind+'-arrow)"'+(' stroke-dasharray="6 4"' if dashed else '')+'/>'
    if kind=='modules':
        nodes=[(20,20,'App / CudaControls · Python',['\u4e3b\u7ebf\u7a0b\uff1a\u7a97\u53e3\u3001\u8bed\u8a00\u3001API\u3001\u8bbe\u7f6e','\u9996\u6b21\u8bed\u8a00\u9875\u5171\u7528 CUDA \u63a7\u4ef6'],True),
            (390,20,'OcrCore · Python',['\u5168\u5e27\u53d6\u56fe\u4e0e\u8bed\u8a00/\u540e\u7aef\u8def\u7531','\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4f18\u5148 CPU'],False),
            (760,20,'CudaOcr → helper',['\u53d7\u9650 JSON IPC / \u72ec\u7acb\u8fdb\u7a0b','PP-OCRv6-small / \u5b9e\u9645 kernel \u9a8c\u8bc1'],False),
            (20,190,'Pipeline / ObjectTracker',['\u6709\u754c\u89c2\u6d4b\u961f\u5217 / \u7a33\u5b9a ID','\u5bf9\u8c61 revision \u963b\u6b62\u65e7\u8bd1\u6587\u56de\u6d41'],False),
            (390,190,'TranslationEngine',['Python / HTTPS SSE / \u9884\u7b97','\u53ea\u751f\u6210\u8bd1\u6587\uff0c\u4e0d\u751f\u6210\u7ed8\u5236\u547d\u4ee4'],True),
            (760,190,'ContextArchive / ContextAgent',['SQLite+zlib / \u6709\u754c\u5386\u53f2\u53c2\u8003','\u5b8c\u6210\u8bd1\u6587\u540e\u540e\u53f0\u5237\u65b0\u641c\u7d22'],False),
            (20,360,'OverlayState · Python',['\u5f53\u524d\u4fee\u8ba2 / \u5f53\u524d\u5750\u6807 / \u6d41\u5f0f\u72b6\u6001','\u4e0d\u63a5\u6536\u641c\u7d22\u7b14\u8bb0\u6216\u63a8\u7406\u6587\u672c'],False),
            (390,360,'NativeCore · C++17 / Win32',['\u539f\u884c\u77e9\u5f62 / \u7ec4\u5b57\u53f7 / \u5b57\u8ddd','GDI \u53cc\u7f13\u51b2 / \u70b9\u51fb\u7a7f\u900f'],True),
            (760,360,'\u7a97\u53e3\u4e0e\u6570\u636e\u8fb9\u754c',['\u4ec5\u6240\u9009 HWND / PID \u524d\u53f0','\u5bc6\u94a5DPAPI / \u516c\u5171\u8d44\u6599\u4e0d\u542b\u79c1\u5bc6\u5e93'],False)]
        arrows=[('M330 75 H390',False),('M700 75 H760',False),('M545 130 V158 H175 V190',False),('M330 245 H390',False),('M760 245 H700',False),('M700 280 H730 V310 H915 V300',True),('M545 300 V325 H175 V360',False),('M330 415 H390',False),('M700 415 H760',False)]
    elif kind=='threads':
        nodes=[(20,20,'\u4e3b\u8fdb\u7a0b · Tk \u4e3b\u7ebf\u7a0b ×1',['\u914d\u7f6e / \u4e8b\u4ef6\u5e94\u7528 / OverlayState','UI\u53ea\u5728\u6240\u5c5e\u7ebf\u7a0b\u66f4\u65b0'],True),
            (390,20,'\u91c7\u96c6 ×1 → \u6700\u65b0\u89c2\u6d4b\u961f\u52171',['\u4e00\u6b21\u6574\u5e27 → \u591a\u4e2aROI','OCR\u8c03\u7528\u987a\u5e8f\u53d7\u5f53\u524d\u540e\u7aef\u7ea6\u675f'],False),
            (760,20,'\u534f\u8c03 ×1 → \u5339\u914d\u6c60\u9ed8\u8ba42',['1–4\u4e2a\u5339\u914d\u5de5\u4f5c\u7ebf\u7a0b','\u6700\u591a32\u5bf9\u8c61 / revision\u9010\u5bf9\u8c61'],False),
            (760,190,'\u7ffb\u8bd1\u6c60 · \u5f53\u524dUI\u9ed8\u8ba48',['\u53ef\u8c031–16\uff1bPipeline\u6784\u9020\u9ed8\u8ba44','\u5bb9\u91cf\u5185\u63d0\u4ea4\uff1b\u7f51\u7edcI/O\u53ef\u91cd\u53e0'],True),
            (390,190,'\u539f\u751f\u7ed8\u5236\u7ebf\u7a0b ×1',['C++ Win32 \u6d88\u606f\u5faa\u73af','\u66f4\u65b0\u5408\u5e76 / \u53cc\u7f13\u51b2 / \u70b9\u51fb\u7a7f\u900f'],True),
            (20,190,'\u53c2\u8003\u540e\u53f0 · \u6700\u591a1\u4f5c\u4e1a',['\u6210\u529f\u8bd1\u6587\u4e4b\u540e\u5237\u65b0 / \u65e0\u961f\u5217','\u5171\u7528\u7f51\u7edc\u9884\u7b97\u4e0e\u5e76\u53d1\u69fd'],False),
            (20,360,'\u53ef\u9009 CPU OCR helper',['stdout\u8bfb\u53d6\u7ebf\u7a0b\uff1b\u6574\u5e27worker1','\u533a\u57df\u7ec6\u5316\u9ed8\u8ba44\uff0c\u53ef\u8c031–8'],False),
            (390,360,'\u53ef\u9009 CUDA helper',['\u72ec\u7acb\u8fdb\u7a0b\uff1b\u4e32\u884cJSON\u8bf7\u6c42','GPU/ORT\u5185\u90e8\u7ebf\u7a0b\u4e0d\u8ba1\u4e3a\u56fa\u5b9a\u6570'],False),
            (760,360,'\u53ef\u9009\u4e91\u7aef\u56fe\u50cf\u6838\u9a8c\u6c60 ×1',['\u6309\u5f00\u5173\u3001\u95f4\u9694\u4e0e\u7f6e\u4fe1\u6761\u4ef6\u8fd0\u884c','\u4e0d\u4e3a\u6bcf\u4e2aOCR\u6846\u65e0\u9650\u521b\u5efa\u7ebf\u7a0b'],False)]
        arrows=[('M330 75 H390',False),('M700 75 H760',False),('M915 130 V190',False),('M760 245 H700',False),('M390 245 H330',True),('M175 130 V155 H360 V415 H390',True),('M175 300 V360',True)]
    else:
        nodes=[(20,20,'01 · \u786e\u5b9a\u76ee\u6807\u4e0e\u8303\u56f4',['\u9009\u62e9\u771f\u5b9e\u6e38\u620f\u8fdb\u7a0b\u4e0e\u8bed\u8a00','\u5b8c\u6574\u5ba2\u6237\u533a\u6216 1–8 \u4e2a\u77e9\u5f62'],True),
            (390,20,'02 · \u8bc6\u522b\u4e0e\u53ef\u4fe1\u5b9a\u4f4d',['\u672c\u5730 OCR / \u53ef\u9009\u56fe\u50cf\u6838\u9a8c','CUDA / CPU / fallback \u5982\u5b9e\u62a5\u544a'],False),
            (760,20,'03 · \u5bf9\u8c61\u4e0e\u5df2\u6709\u8bed\u5883',['\u53ea\u7528\u5f53\u524d\u51e0\u4f55\u548c\u5df2\u5b8c\u6210\u53c2\u8003','\u540c\u8303\u56f4\u5386\u53f2\uff1b\u9996\u6587\u4e0d\u7b49\u641c\u7d22'],False),
            (760,190,'04 · \u6d41\u5f0f AI \u7ffb\u8bd1',['\u4fdd\u7559\u6e90\u6587\u4e0e\u6362\u884c','\u6709\u754c SSE / \u5e76\u53d1 / \u8bf7\u6c42\u989d\u5ea6'],True),
            (390,190,'05 · \u7edf\u4e00\u62df\u5408\u4e0e\u663e\u793a',['\u6d41\u5f0f\u53ef\u5bb9\u7eb3\u524d\u7f00\uff0cfinal\u6574\u7ec4\u62df\u5408','\u5f31\u6781\u77ed\u884c\u4e0d\u538b\u57ae\u6574\u6bb5\u6b63\u6587'],False),
            (20,190,'06 · \u89c2\u5bdf\u4e0e\u540e\u7eed\u66f4\u65b0',['\u5931\u7126\u64a4\u4e0b / \u79fb\u52a8\u91cd\u5b9a\u4f4d','\u540e\u53f0\u53c2\u8003\u53ea\u5e2e\u52a9\u540e\u7eed\u8bed\u53e5'],False)]
        arrows=[('M330 75 H390',False),('M700 75 H760',False),('M915 130 V190',False),('M760 245 H700',False),('M390 245 H330',False)]
    height=490 if kind in ('modules','threads') else 330
    return '<div class="diagram"><svg viewBox="0 0 1090 '+str(height)+'" role="img" aria-label="'+kind+'"><defs><marker id="'+kind+'-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#3f8981"/></marker></defs>'+''.join(arrow(*a) for a in arrows)+''.join(box(*n) for n in nodes)+'</svg></div>'

def index_page(summary,inventory):
    tests=load(DOCS/'TEST_REPORT.json',{})
    full=tests.get('full_suite',{})
    shots=inventory.get('screenshots',[])
    body=hero('TEACHER REVIEW / BASELINE 0.01.15 → CURRENT 0.01.27','\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c<br>\u66f4\u5c11\u7684\u7b49\u5f85','\u4ece\u6e38\u620f\u539f\u6587\u5230\u539f\u4f4d\u8bd1\u6587\uff0c\u628a\u54cd\u5e94\u3001\u51c6\u786e\u6027\u548c\u53ef\u9a8c\u8bc1\u6027\u653e\u5728\u540c\u4e00\u5f20\u8bc4\u5ba1\u684c\u4e0a\u3002\u8fd9\u91cc\u5148\u8bf4\u660e\u7cfb\u7edf\u505a\u4e86\u4ec0\u4e48\uff0c\u518d\u8bf4\u660e\u6570\u636e\u80fd\u652f\u6301\u4ec0\u4e48\u3002')
    body+='<section id="overview"><div class="grid"><div class="card"><span class="step">01 / \u4ea7\u54c1\u76ee\u6807</span><h3>\u4fdd\u6301\u539f\u4f4d\u9605\u8bfb</h3><p>\u8bc6\u522b\u76ee\u6807\u6e38\u620f\u5185\u6587\u5b57\uff0c\u6d41\u5f0f\u751f\u6210\u8bd1\u6587\uff0c\u5e76\u5728\u672c\u5730\u6d4b\u5f97\u7684\u4f4d\u7f6e\u663e\u793a\u3002\u6362\u884c\u3001\u5b57\u4f53\u3001\u80cc\u666f\u548c\u7a97\u53e3\u8fb9\u754c\u7531\u672c\u5730\u7a0b\u5e8f\u7ba1\u7406\u3002</p></div><div class="card"><span class="step">02 / \u5de5\u7a0b\u53d6\u820d</span><h3>\u9009\u62e9\u5408\u9002\u7684\u8bc6\u522b\u8def\u5f84</h3><p>\u5e38\u89c4\u4e2d\u65e5\u82f1\u6587\u5b57\u53ef\u7528 CUDA\uff1b\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u573a\u666f\u4fdd\u7559 CPU \u4e13\u7ebf\u3002\u540e\u53f0\u8bed\u5883\u4e0d\u6321\u9996\u6587\uff0c\u4e0d\u628a\u6a21\u578b\u5206\u6570\u5f53\u51c6\u786e\u7387\u3002</p></div><div class="card"><span class="step">03 / \u8bc4\u5ba1\u539f\u5219</span><h3>\u6bcf\u4e2a\u7ed3\u8bba\u6709\u8fb9\u754c</h3><p>\u51b7\u542f\u52a8\u3001\u70ed\u8def\u5f84\u3001\u7f13\u5b58\u3001\u5b57\u7b26\u51c6\u786e\u7387\u3001\u5b9e\u9645\u7aef\u5230\u7aef\u5206\u522b\u62a5\u544a\uff1b\u7528\u65b0\u6d4b\u91cf\u5bf9\u6bd4 .15 \u548c .27\uff0c\u4fdd\u7559\u5b8c\u6574\u539f\u59cb\u6837\u672c\u3002</p></div></div></section>'
    body+='<section id="status"><div class="section-head"><h2>\u5f53\u524d\u9a8c\u8bc1\u72b6\u6001</h2><span class="meta">\u4e0d\u540c\u7c7b\u578b\u7684\u9a8c\u8bc1\u4e0d\u4e92\u76f8\u66ff\u4ee3</span></div><div class="grid"><div class="card"><div class="number">'+esc(full.get('passed','—'))+'</div><h3>\u7248\u672c\u56de\u5f52\u901a\u8fc7</h3><p>'+esc(full.get('skipped','—'))+' \u9879\u8df3\u8fc7\uff1b\u6b64\u6570\u5b57\u6765\u81ea\u5df2\u5f52\u6863\u7684\u672c\u7248\u672c\u5b8c\u6574\u6d4b\u8bd5\uff0c\u4e0d\u4e0e\u5206\u6279\u6d4b\u8bd5\u76f8\u52a0\u3002</p></div><div class="card"><div class="number">'+str(len(shots))+'</div><h3>UI \u8868\u9762\u622a\u56fe</h3><p>\u771f\u5b9e\u5e94\u7528\u6e32\u67d3\uff0c\u9694\u79bb\u6f14\u793a\u72b6\u6001\uff1b\u6bcf\u5f20\u56fe\u6807\u6ce8\u8bed\u8a00\u3001\u9875\u9762\u548c\u8986\u76d6\u9650\u5236\u3002</p></div><div class="card"><div class="number">'+('\u65b0\u6d4b\u91cf' if summary else '\u6d4b\u91cf\u4e2d')+'</div><h3>\u56fa\u5b9a .15 \u57fa\u7ebf</h3><p>\u65b0\u4e00\u8f6e\u76f8\u540c\u8f93\u5165\u3001\u4ea4\u66ff\u987a\u5e8f\u6d4b\u8bd5\uff1b\u5c1a\u672a\u5b8c\u6210\u7684\u94fe\u8def\u660e\u786e\u7559\u7a7a\uff0c\u4e0d\u590d\u7528 .25 \u6570\u5b57\u5192\u5145 .27\u3002</p></div></div></section>'
    body+='<section id="reading-path"><h2>\u5efa\u8bae\u8bc4\u5ba1\u8def\u7ebf</h2><div class="grid two">'+''.join('<a class="card" href="'+link+'"><span class="step">'+number+'</span><h3>'+title+'</h3><p>'+desc+'</p></a>' for number,title,desc,link in [('01 / 5\u5206\u949f','\u770b\u4ea7\u54c1\u4e0e\u5b8c\u6574\u64cd\u4f5c','\u4ece\u521d\u6b21\u8bed\u8a00\u3001CUDA\u3001API \u69fd\u5230\u5c4f\u5e55\u7ffb\u8bd1\u3001\u8bcd\u5178\u3001\u624b\u52a8\u7ffb\u8bd1\u548c\u8bbe\u7f6e\u3002','manual.zh.html'),('02 / 10\u5206\u949f','\u770b\u6027\u80fd\u800c\u975e\u53e3\u53f7','\u5148\u770b\u6d4b\u8bd5\u6761\u4ef6\uff0c\u518d\u5206\u522b\u8bfb\u6bcf\u8f6e\u8017\u65f6\u3001\u5b57\u7b26\u8f6c\u5f55\u8bef\u5dee\u548c\u7aef\u5230\u7aef\u8bc1\u636e\u3002','performance.html'),('03 / 10\u5206\u949f','\u770b\u7ed3\u6784\u4e0e\u63a5\u53e3','\u6a21\u5757\u8bed\u8a00\u3001\u7ebf\u7a0b\u3001IPC\u3001\u63d0\u793a\u6570\u636e\u8fb9\u754c\u3001\u4f9d\u8d56\u4e0e\u5f53\u524d\u9650\u5236\u3002','architecture.html'),('04 / \u6309\u9700','\u9010\u9875\u6838\u5bf9 UI','\u5b8c\u6574\u622a\u56fe\u6e05\u5355\uff0c\u539f\u5c3a\u5bf8\u94fe\u63a5\u548c\u672a\u8986\u76d6\u9879\u76ee\u3002','gallery.html')])+'</div></section>'
    body+='<section id="evidence"><h2>\u8bc1\u636e\u600e\u6837\u7ec4\u7ec7</h2>'+table(['\u8bc1\u636e','\u652f\u6301\u7684\u5224\u65ad','\u4e0d\u80fd\u63a8\u51fa\u7684\u7ed3\u8bba'],[['\u65b0\u56fa\u5b9a\u56fe OCR','\u540c\u56fe\u3001\u540c\u6807\u6ce8\u4e0b\u7684\u8bc6\u522b\u8017\u65f6\u4e0e\u5b57\u7b26\u5dee\u5f02','\u4e0d\u80fd\u63a8\u65ad\u4efb\u610f\u6e38\u620f\u3001\u4efb\u610f\u65b0\u6587\u672c\u901f\u5ea6'],['\u771f\u5b9e API \u7aef\u5230\u7aef\uff08\u5982\u5b8c\u6210\uff09','\u8be5\u6837\u672c\u4ece\u56fa\u5b9a\u56fe\u7247\u5230\u8bd1\u6587\u56de\u8c03\u7684\u65f6\u95f4','\u672c\u8f6e\u4e0d\u542b\u7ed8\u5236/\u5c4f\u5e55\u53ef\u89c1\u6027\uff0c\u4e5f\u4e0d\u662f\u7a33\u5b9a\u670d\u52a1\u5546SLA'],['UI \u56fe\u5e93','\u5217\u51fa\u7684\u9875\u9762\u786e\u5b9e\u6e32\u67d3\u3001\u63a7\u4ef6\u53ef\u89c1','\u4e0d\u7b49\u4e8e\u5b9e\u673a\u6e38\u620f\u8986\u76d6\u6210\u529f'],['\u81ea\u52a8\u5316\u4e0e\u539f\u751f\u6d4b\u8bd5','\u5df2\u8986\u76d6\u5951\u7ea6\u53ca\u56de\u5f52\u7528\u4f8b\u901a\u8fc7','\u4e0d\u7b49\u4e8e\u4e0d\u5b58\u5728\u672a\u77e5\u7f3a\u9677']])+'</section>'
    body+='<section id="limits"><h2>\u4fdd\u7559\u660e\u786e\u7684\u9650\u5236</h2><div class="note amber">OCR \u4ecd\u53ef\u80fd\u8bef\u8bc6\u522b\uff1b\u4f4e\u7f6e\u4fe1\u548c\u6781\u77ed\u6846\u53ef\u80fd\u4fdd\u7559\u539f\u6587\u3002\u8054\u7f51\u8bd1\u6587\u4f9d\u8d56\u670d\u52a1\u5546\u54cd\u5e94\u3002CUDA \u8d28\u91cf\u6ed1\u6761\u4e0d\u662f\u51c6\u786e\u7387\u767e\u5206\u6bd4\uff0c\u663e\u5b58\u9884\u7b97\u4e0d\u662f\u6574\u8fdb\u7a0b\u786c\u4e0a\u9650\u3002\u72ec\u5360\u5168\u5c4f\u3001\u53d7\u4fdd\u62a4\u753b\u9762\u548c\u590d\u6742\u5b57\u4f53\u987b\u9010\u6e38\u620f\u9a8c\u8bc1\u3002</div><p>\u516c\u5f00\u8d44\u6599\u4e0d\u5305\u542b\u4e2a\u4eba\u914d\u7f6e\u3001DPAPI \u5bc6\u94a5\u3001\u79c1\u4eba\u7ffb\u8bd1\u5386\u53f2\u6216\u6e38\u620f\u7a0b\u5e8f\u3002\u539f\u59cb\u8bc4\u5ba1\u622a\u56fe\u4f7f\u7528\u9694\u79bb\u72b6\u6001\uff0c\u6765\u6e90\u4e0e\u9650\u5236\u53ef\u5728\u56fe\u5e93\u9010\u9879\u67e5\u770b\u3002</p></section>'
    return shell('\u8bc4\u5ba1\u603b\u89c8',body)

def architecture_page():
    body=hero('ENGINEERING / EXPLAINABLE BOUNDARIES','\u6a21\u578b\u8d1f\u8d23\u7406\u89e3\uff0c<br>\u7a0b\u5e8f\u8d1f\u8d23\u8fb9\u754c\u3002','Python \u7ec4\u7ec7\u4ea4\u4e92\u3001I/O \u4e0e\u8c03\u5ea6\uff0cC++ \u5904\u7406\u7cfb\u7edf\u6355\u83b7\u548c\u539f\u751f\u7ed8\u5236\uff1b\u53ef\u9009 CUDA helper \u901a\u8fc7\u6709\u754c JSON IPC \u9694\u79bb\u3002')
    body+='<section id="modules"><h2>\u9879\u76ee\u6a21\u5757\u4e0e\u8bed\u8a00</h2>'+diagram('modules')+table(['\u6a21\u5757 / \u7c7b','\u8bed\u8a00\u4e0e\u4f4d\u7f6e','\u804c\u8d23'],[
        ['App / SettingsPanel / CudaControls','Python / Tk','\u4e3b\u7ebf\u7a0b\u63a7\u4ef6\u3001\u4e09\u69fdAPI\u3001\u9996\u6b21\u8bed\u8a00\u4e0eCUDA\u5171\u7528\u914d\u7f6e'],['OcrCore / CudaOcr / PortableOcr','Python / \u56fe\u7247JSON IPC','\u91c7\u96c6\u8def\u7531\u3001GPU\u6838\u9a8c\u3001CPU\u56de\u9000\u4e0e\u8fdb\u7a0b\u751f\u547d\u5468\u671f'],['CUDA helper / Engine','\u72ec\u7acb Python\uff0cONNX Runtime CUDA','PP-OCRv6-small\u68c0\u6d4b/\u8bc6\u522b\uff1b\u5b9e\u9645kernel\u8bc1\u636e'],['Pipeline / ObjectTracker','Python / \u6709\u754c\u7ebf\u7a0b\u6c60','\u6700\u65b0\u89c2\u6d4b\u3001\u7a33\u5b9aID\u3001\u6bcf\u5bf9\u8c61revision\u3001\u4efb\u52a1\u5bb9\u91cf'],['TranslationEngine / ContextAgent','Python / httpx SSE','\u5171\u4eab\u9884\u7b97\u3001\u5148\u663e\u793a\u540e\u540e\u53f0\u8bed\u5883\u3001\u53d6\u6d88'],['ContextArchive','Python / SQLite / zlib','\u8303\u56f4\u9694\u79bb\u5386\u53f2\u3001\u6709\u754c\u63d0\u793a\u6458\u5f55\u3001\u6210\u529f\u8bb0\u5f55'],['OverlayState / NativeCore','Python ctypes / C++17','\u62d2\u7edd\u65e7\u54cd\u5e94\u3001\u539f\u4f4d\u77e9\u5f62\u3001\u884c\u5e03\u5c40\u3001\u7a97\u53e3\u524d\u53f0\u8fb9\u754c']])+'</section>'
    body+='<details><summary>\u9879\u76ee\u76ee\u5f55\u7ed3\u6784\uff08\u6838\u5fc3\u6e90\u7801\uff09</summary><pre>'+esc('''0.01.27/
├─ nkc_galgame_translator/                         Python \u5e94\u7528\u4e0eI/O\u8c03\u5ea6
│  ├─ app.py                          App\uff1aTk\u751f\u547d\u5468\u671f\u3001\u4e8b\u4ef6\u4e0e\u914d\u7f6e
│  ├─ settings_ui.py                  SettingsPanel\uff1a\u5e38\u89c4\u8bbe\u7f6e
│  ├─ cuda_settings_ui.py             CudaControls\uff1a\u9996\u6b21\u8bbe\u7f6e/\u5e38\u89c4\u8bbe\u7f6e\u5171\u7528
│  ├─ ocr.py / cuda_ocr.py             OcrCore / CudaOcr\uff1a\u8def\u7531\u4e0e\u6709\u754cIPC
│  ├─ pipeline.py / tracking.py        Pipeline / ObjectTracker\uff1a\u5bf9\u8c61\u751f\u547d\u5468\u671f
│  ├─ presentation.py                 OverlayState\uff1a\u5f53\u524d\u4fee\u8ba2\u4e0e\u663e\u793a\u72b6\u6001
│  ├─ translation.py                  TranslationEngine\uff1aSSE\u3001\u5e76\u53d1\u3001\u989d\u5ea6
│  ├─ context_agent.py                 ContextAgent\uff1a\u6709\u754c\u540e\u53f0\u53c2\u8003
│  ├─ context_archive.py               ContextArchive\uff1aSQLite\u538b\u7f29\u8bed\u5883
│  └─ native.py                        NativeCore\uff1actypes ABI\u8fb9\u754c
├─ native/                             C++17 / Win32
│  ├─ core.h / core.cpp                \u6355\u83b7\u3001\u7a97\u53e3\u7ea6\u675f\u3001GDI\u8986\u76d6\u7ebf\u7a0b\u3001C\u5bfc\u51fa
│  └─ fixed_layout.h                   \u5b57\u7c07\u3001\u884c\u6846\u3001\u6574\u7ec4\u62df\u5408\u3001\u6d41\u5f0f\u524d\u7f00
├─ tools/                              \u6784\u5efa\u3001\u72ec\u7acbhelper\u3001\u9a8c\u8bc1\u4e0e\u6587\u6863
│  ├─ ocr_helper.py                    Tesseract\u8fdb\u7a0b/\u533a\u57df\u7ec6\u5316\u6c60
│  ├─ cuda_ocr_helper.py               ONNX Runtime CUDA\u8fdb\u7a0b
│  ├─ package.ps1 / verify_release.py  \u53ef\u590d\u6838\u516c\u5171\u53d1\u884c\u8fb9\u754c
│  └─ build_teacher_review27.py        \u6b64\u79bb\u7ebf\u95e8\u6237\u7684\u751f\u6210\u5165\u53e3
├─ tests/                              \u5355\u5143\u3001\u5e76\u53d1\u3001\u539f\u751fGDI\u4e0e\u53d1\u5e03\u56de\u5f52
├─ docs/                               \u5b8c\u6574\u53cc\u8bed\u624b\u518c\u3001\u63a5\u53e3\u3001\u8bb8\u53ef\u3001\u8bc4\u5ba1\u95e8\u6237
└─ reports/teacher-review27/            \u672c\u6b21\u8f93\u5165\u3001\u539f\u59cb\u8f6e\u6b21\u4e0e\u622a\u56fe\u6e05\u5355''')+'</pre><p>\u56fe\u4e2d\u7684\u5bf9\u8c61\u662f\u5c4f\u5e55\u6587\u5b57\u533a\u57df\uff0c\u4e0d\u901a\u8fc7\u8bfb\u53d6\u6e38\u620f\u5185\u5b58\u83b7\u5f97\u5185\u90e8\u5bf9\u8c61\u6811\u3002\u5f53\u524d\u6587\u6863\u5305\u4e0d\u542b\u79c1\u4eba\u914d\u7f6e\u3001\u6e38\u620f\u6587\u4ef6\u6216\u5bc6\u94a5\u3002</p></details>'
    body+='<section id="threads"><h2>\u7ebf\u7a0b\u5206\u5de5\uff0c\u4e0d\u7b49\u4e8e\u65e0\u9650\u5e76\u884c</h2>'+diagram('threads')+'<div class="grid two"><div class="card"><h3>\u611f\u77e5\u4e0e\u7ffb\u8bd1</h3><p>\u5f53\u524dUI\u54cd\u5e94\u9884\u8bbe\u9ed8\u8ba4\uff1a\u5339\u914d2\u3001\u533a\u57df\u7ec6\u53164\u3001\u7ffb\u8bd1\u5e76\u53d18\uff1b\u5e73\u8861\u9884\u8bbe\u4e3a2/2/4\u3002\u6700\u65b0\u89c2\u6d4b\u53ea\u4fdd\u7559\u5bb9\u91cf1\uff0c\u591a\u4e2a\u9009\u533a\u6765\u81ea\u540c\u4e00\u5e27\u3002\u540e\u7aef\u53ef\u505a\u6709\u754c\u533a\u57df\u7ec6\u5316\uff1b\u5e76\u975e\u6bcf\u6846\u5404\u5efaOCR\u8fdb\u7a0b\u3002</p></div><div class="card"><h3>\u663e\u793a\u4e0e\u53c2\u8003</h3><p>Tk\u53ea\u5728\u4e3b\u7ebf\u7a0b\u66f4\u65b0\uff0cC++\u7ed8\u5236\u72ec\u7acb\u3002\u540e\u53f0\u8bed\u5883\u6700\u591a1\u4f5c\u4e1a\u3001\u65e0\u961f\u5217\uff0c\u4e0e\u8bd1\u6587\u5171\u4eab\u5bb9\u91cf\uff1b\u5e76\u53d1\u4e3a1\u65f6\u4e0d\u5360\u552f\u4e00\u663e\u793a\u69fd\u3002\u4e0a\u8ff0\u662f\u663e\u5f0fworker\u4e0a\u9650\uff0c\u4e0d\u662f\u7cfb\u7edf\u7ebf\u7a0b\u603b\u6570\uff0c\u5e93\u5185\u90e8\u7ebf\u7a0b\u4f1a\u53d8\u5316\u3002</p></div></div><div class="note">\u5bf9\u8c61ID\u662fOCR\u6846\u7684\u542f\u53d1\u5f0f\u5173\u8054\uff0c\u5e76\u975eUnity/\u6e38\u620f\u5185\u5b58\u5bf9\u8c61ID\u3002\u906e\u6321\u3001\u540c\u6587\u4ea4\u53c9\u548c\u5e03\u5c40\u8df3\u53d8\u53ef\u80fd\u6b67\u4e49\uff1b\u79fb\u52a8\u53ea\u66f4\u65b0\u4f4d\u7f6e\uff0c\u6587\u5b57\u53d8\u5316\u9012\u589erevision\uff0c\u8fc7\u671f\u7ed3\u679c\u4e0d\u4f1a\u5e94\u7528\u3002Python CPU\u5339\u914d\u53d7GIL\u7ea6\u675f\uff0c\u4e0d\u4fdd\u8bc1\u7ebf\u6027\u52a0\u901f\u3002</div></section>'
    body+='<section id="workflow"><h2>\u4e00\u6b21\u7ffb\u8bd1\u7684\u5b8c\u6574\u6d41\u7a0b</h2>'+diagram('workflow')+'</section>'
    body+='<section id="interfaces"><h2>\u7ec6\u9897\u7c92\u5ea6\u63a5\u53e3\u4e0e\u5951\u7ea6</h2>'+table(['\u63a5\u53e3','\u8f93\u5165/\u8f93\u51fa','\u5173\u952e\u8fb9\u754c'],[
        ['CudaOcr(root, memory_mb=1024, quality=75)','recognize(image, language) → lines / ocr_ms / cuda','≤4096/\u8f74\uff1b≤512\u884c\u300164000\u5b57\u7b26\uff1b1MiB\u54cd\u5e94\uff1b\u5750\u6807\u5728\u56fe\u5185'],['CudaOcr.warmup() / cancel()','\u5408\u6210\u5f20\u91cf\u9884\u70ed / \u7ec8\u6b62helper','\u4e0d\u91c7\u5c4f\u3001\u4e0d\u8054\u7f51\uff1b\u65b0\u56fe\u5f62\u72b6\u4ecd\u6709\u521d\u59cb\u5316\u6210\u672c'],['ContextAgent.peek(key)','\u5df2\u5b8c\u6210\u540c\u6e38\u620f/\u8eab\u4efd/\u8bed\u5411/\u8bed\u5883\u53c2\u8003','\u4e0d\u7b49\u5f85Future\uff1b\u6700\u591a32\u7f13\u5b58\uff1b\u6458\u8981900s/\u5931\u8d2530s'],['ContextAgent.refresh(...)','\u6210\u529f\u663e\u793a\u540e\u5c1d\u8bd5\u540e\u53f0\u8bf7\u6c42','1\u4f5c\u4e1a\u65e0\u961f\u5217\uff1b\u540c\u9884\u7b97/\u5e76\u53d1\uff1b\u53d6\u6d88\u5f52\u8fd8\u69fd'],['TranslationEngine.translate(...)','\u539f\u6587\u4e0e\u53c2\u8003 → \u7d2f\u79ef\u7eaf\u8bd1\u6587 SSE','\u65e0\u672c\u5730\u5de5\u5177\uff1b\u5bc6\u94a5\u4e0d\u8fdb\u63d0\u793a\uff1b\u7f51\u9875\u548c\u6a21\u578b\u90fd\u662f\u6570\u636e'],['OverlayState / GLRegion / GLSourceRow','ID/revision\u4e0e\u539f\u884c\u77e9\u5f62 → \u539f\u751f\u663e\u793a','ABI2\uff1bfont_intrinsic_px / lines[].drawable \u8bca\u65ad\u9010\u884c\u53ef\u89c1\u6027'],['CudaControls.values() / tuning','enabled\u3001quality 0–100\u3001memory 256–16384','\u7528\u6237\u914d\u7f6e\u9ed8\u8ba4\u5f00\u542f/75/1024\uff1b\u663e\u5b58arena\u9884\u7b97\u4e0d\u662f\u603b\u663e\u5b58\u4e0a\u9650']])+'<p><a href="manual.zh.html#p-api">\u5b8c\u6574 API \u5951\u7ea6 →</a>\u3000<a href="manual.en.html#p-input-interfaces">English IPC contracts →</a></p></section>'
    body+='<section id="dependencies"><h2>\u4f9d\u8d56\u3001\u8bb8\u53ef\u4e0e\u4ea4\u4ed8\u8fb9\u754c</h2>'+table(['\u7ec4\u4ef6','\u7248\u672c/\u89d2\u8272','\u5206\u53d1\u4e0e\u9a8c\u8bc1'],[['\u57fa\u7840\u8fd0\u884c\u65f6','CPython 3.14 x64\u3001Tk\u3001httpx\u3001SQLite','\u516c\u5f00\u57fa\u7840\u5305\uff1b\u51c6\u786e\u7248\u672c\u53caSHA\u89c1\u5bf9\u5e94\u9501\u6587\u4ef6'],['CUDA\u53ef\u9009\u7ec4\u4ef6','ONNX Runtime GPU 1.32.0 / RapidOCR 3.10.0','CUDA13.x runtime / cuDNN9.x\uff1b\u56fa\u5b9a28\u5305\u4e0e\u6a21\u578bSHA'],['\u6a21\u578b','PP-OCRv6-small \u68c0\u6d4b/\u8bc6\u522b','\u72ec\u7acb\u6a21\u578b\u6743\u91cd\uff1b\u4fdd\u7559\u5bf9\u5e94\u6a21\u578b\u8bb8\u53ef'],['\u539f\u751f\u6838\u5fc3','C++17 / Win32 / GDI / WGC','\u65b0\u7248\u672c\u72ec\u7acb\u7f16\u8bd1\uff1bPE\u53ca\u5bfc\u51fa\u68c0\u67e5\u4e0e\u6e90\u7801\u5bf9\u5e94'],['\u9879\u76ee\u4e0e\u7b2c\u4e09\u65b9','\u4e3b\u7a0b\u5e8fMIT','\u7b2c\u4e09\u65b9\u8bb8\u53ef\u4fdd\u7559\uff0c\u4e0d\u80fd\u56e0IPC\u7701\u7565\u5176\u8bb8\u53ef\u4e49\u52a1']])+'<div class="note">\u6ca1\u6709\u5339\u914d\u7684CUDA\u7ec4\u4ef6\u6216GPU\u65f6\u4fdd\u7559CPU\u8def\u5f84\u3002\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u5728Auto\u4e2d\u4f18\u5148\u4e13\u95e8CPU\u8bc6\u522b\u3002\u5df2\u5b89\u88c5\u6587\u4ef6\u4e0d\u662fGPU\u5de5\u4f5c\u7684\u8bc1\u636e\uff0c\u5fc5\u987b\u9a8c\u8bc1\u5b9e\u9645 provider \u548c kernel\u3002</div></section>'
    return shell('\u7ed3\u6784\u4e0e\u63a5\u53e3',body,'architecture')

def gallery_page(inventory):
    shots=inventory.get('screenshots',[]);unavailable=inventory.get('unavailable',[])
    body=hero('INTERFACE / FULL-SURFACE INVENTORY','\u9010\u9875\u67e5\u770b\uff0c<br>\u9010\u9879\u6838\u9a8c\u3002','\u539f\u5c3a\u5bf8\u622a\u56fe\u901a\u8fc7\u72ec\u7acb HTML \u6253\u5f00\uff1b\u56fe\u7247\u5185\u5d4c\uff0c\u590d\u5236\u6587\u4ef6\u5939\u6216\u5206\u5305\u89e3\u538b\u540e\u4ecd\u53ef\u79bb\u7ebf\u9605\u8bfb\u3002\u622a\u56fe\u662f\u9694\u79bb\u72b6\u6001\u7684\u771f\u5b9e\u5e94\u7528\u6e32\u67d3\uff0c\u4e0d\u4ee3\u8868\u771f\u5b9e\u8d26\u53f7\u6216\u5df2\u5b8c\u6210\u5b9e\u673a\u7ffb\u8bd1\u3002')
    body+='<section id="coverage"><h2>\u8986\u76d6\u4e0e\u672a\u8986\u76d6</h2>'+status(str(len(shots))+' \u5f20\u5df2\u767b\u8bb0\u622a\u56fe')+status(str(len(unavailable))+' \u9879\u672a\u8986\u76d6',bool(unavailable))
    if unavailable:body+=table(['\u672a\u8986\u76d6\u9879','\u539f\u56e0'],[[esc(x.get('surface',x.get('title',''))),esc(x.get('reason',x.get('limitations','')))] if isinstance(x,dict) else [esc(x),'\u672a\u63d0\u4f9b\u622a\u56fe'] for x in unavailable])
    body+='</section><section id="screenshots"><h2>\u5b8c\u6574 UI \u56fe\u5e93</h2><div class="gallery">'
    records=[]
    for i,item in enumerate(shots):
        relative=Path(item['path']);path=(EVIDENCE/relative).resolve()
        if not path.is_relative_to(EVIDENCE.resolve()) or not path.is_file():raise ValueError('Screenshot outside inventory scope: '+str(relative))
        slug=re.sub(r'[^a-zA-Z0-9_-]','-',str(item.get('surface','screen'))).strip('-') or 'screen'
        filename=f'{i+1:02d}-{slug}.html';link='screenshots/'+filename
        title=str(item.get('title',item.get('surface',relative.stem)))
        limitations=item.get('limitations','');limitations='; '.join(map(str,limitations)) if isinstance(limitations,list) else str(limitations)
        caption=esc(item.get('language',''))+' · '+esc(item.get('source_version',VERSION))+' · '+esc(item.get('state',''))
        body+='<a class="shot" href="'+link+'"><div class="thumb"><img alt="'+esc(title)+'" loading="lazy" src="'+uri(path,True)+'"></div><div class="caption"><span class="step">'+f'{i+1:02d} / '+esc(item.get('surface',''))+'</span><h3>'+esc(title)+'</h3><p>'+caption+'</p><p>'+esc(limitations)+'</p></div></a>'
        shot_body=hero('UI SCREENSHOT / '+esc(item.get('surface','')),esc(title),caption)+'<section><img alt="'+esc(title)+'" src="'+uri(path)+'"><div class="note"><strong>'+esc(item.get('kind',inventory.get('kind','\u771f\u5b9e\u5e94\u7528\u754c\u9762')))+'\u3002</strong> '+esc(limitations)+'</div><p>\u89c6\u89c9\u6838\u9a8c\uff1a'+esc(item.get('verified','\u672a\u8bb0\u5f55'))+' · \u7f51\u7edc\u8bf7\u6c42\uff1a'+esc(inventory.get('network_requests','\u672a\u8bb0\u5f55'))+'</p><p><a href="../gallery.html#screenshots">← \u8fd4\u56deUI\u56fe\u5e93</a></p></section>'
        write(OUT/'screenshots'/filename,shell(title,shot_body,'gallery',depth='../'))
        records.append({**item,'review_page':link,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    body+='</div>'
    if not shots:body+='<div class="empty">\u622a\u56fe\u91c7\u96c6\u6b63\u5728\u8fdb\u884c\u3002\u6e05\u5355\u5230\u9f50\u540e\u81ea\u52a8\u586b\u5165\uff0c\u4e0d\u4f7f\u7528\u65e7\u7248\u672c\u622a\u56fe\u66ff\u4ee3\u5f53\u524d\u9875\u9762\u3002</div>'
    body+='</section>'
    write(OUT/'ui-inventory.json',json.dumps({**inventory,'screenshots':records},ensure_ascii=False,indent=2))
    return shell('UI \u56fe\u5e93',body,'gallery')

def performance_material(summary):
    """Schema adapter is extended when the measurement producer freezes data."""
    description='\u56fa\u5b9a\u57fa\u7ebf 0.01.15\uff0c\u4e0e\u5f53\u524d 0.01.27 \u6bd4\u8f83\u3002\u5148\u8bfb\u5b9e\u9a8c\u8303\u56f4\uff0c\u518d\u770b\u5404\u8f6e\u503c\uff1b\u51b7\u542f\u52a8\u3001\u590d\u8bbf\u7f13\u5b58\u548c\u80cc\u666f\u53d8\u5316\u70ed\u8def\u5f84\u4e0d\u5408\u5e76\u6210\u4e00\u4e2a\u52a0\u901f\u500d\u6570\u3002'
    body=hero('FRESH MEASUREMENTS / 0.01.15 → 0.01.27','\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c<br>\u66f4\u5c11\u7684\u7b49\u5f85',description)
    body+='<section id="method"><h2>\u5148\u754c\u5b9a\u95ee\u9898\uff0c\u518d\u6bd4\u8f83\u6570\u5b57</h2>'+table(['\u5c42\u7ea7','\u6d4b\u91cf\u8d77\u6b62\u4e0e\u6837\u672c','\u89e3\u91ca\u89c4\u5219'],[['\u51b7\u542f\u52a8 OCR','\u72ec\u7acb\u5b9e\u4f8b\u7684\u9996\u6b21\u8bc6\u522b','\u542b\u521d\u59cb\u5316\uff1b\u4e0e\u70ed\u8f6e\u5206\u5f00'],['\u76f8\u540c\u56fe\u7247\u590d\u8bbf','\u540c\u5b9e\u4f8b\u91cd\u590d\u539f\u56fe','\u53ef\u547d\u4e2d\u6574\u5e27\u7f13\u5b58\uff1b\u53ea\u8bf4\u660e\u590d\u8bbf\u6210\u672c'],['\u80cc\u666f\u53d8\u5316\u70ed\u8def\u5f84','\u552f\u4e00\u89d2\u843d\u50cf\u7d20\u53d8\u5316\u3001\u6b63\u6587\u4e0d\u53d8','\u6574\u5e27\u672a\u547d\u4e2d\uff0c\u4f46\u5141\u8bb8\u5b50\u533a\u57df\u7f13\u5b58\uff1b\u4e0d\u662f\u4efb\u610f\u65b0\u6587\u672c\u901f\u5ea6'],['\u5b57\u7b26\u51c6\u786e\u7387','\u540c\u56fe\u3001\u4eba\u5de5\u6807\u6ce8\u533a\u3001\u89c4\u8303\u5316\u7f16\u8f91\u8ddd\u79bb','\u662f\u539f\u6587\u8f6c\u5f55\uff0c\u4e0d\u662f\u8bed\u4e49\u7ffb\u8bd1\u51c6\u786e\u7387'],['\u771f\u5b9e\u7aef\u5230\u7aef','\u660e\u786e\u8d77\u70b9 → \u771f\u5b9eAPI → \u5b9e\u9645\u7ed8\u5236','\u5355\u5217\u9996\u5b57/\u5b8c\u6574\u8bd1\u6587\uff1b\u4e0d\u628aOCR\u6216\u6a21\u62dfSSE\u5f53\u7aef\u5230\u7aef']])+'</section>'
    pending='<div class="empty">\u65b0\u4e00\u8f6e\u6570\u636e\u5c1a\u672a\u5b8c\u6210\u3002\u6b64\u5904\u4fdd\u6301\u5f85\u6d4b\uff0c\u7edd\u4e0d\u642c\u7528 0.01.25 \u6216\u8c03\u5ea6\u6a21\u62df\u7ed3\u679c\u6807\u4e3a 0.01.27 \u5b9e\u6d4b\u3002</div>'
    for key,title in [('ocr','OCR\uff1a\u9996\u6b21\u4e0e\u70ed\u8def\u5f84'),('accuracy','\u51c6\u786e\u7387\uff1a\u9010\u5b57\u5dee\u5f02'),('e2e','\u771f\u5b9e\u94fe\u8def\uff1a\u8f93\u5165\u5230\u539f\u751f\u7ed8\u5236')]:
        body+='<section id="'+key+'"><h2>'+title+'</h2>'+pending+'</section>'
    body+='<section id="gpu"><h2>GPU \u8bbe\u7f6e\u7684\u5b9e\u9645\u542b\u4e49</h2><div class="grid two"><div class="card"><h3>\u8d28\u91cf\u6ed1\u6761 0–100</h3><p>\u9ed8\u8ba475\uff1b\u63a7\u5236\u68c0\u6d4b\u5206\u8fa8\u7387\u4e0a\u9650\uff0c\u630932\u50cf\u7d20\u91cf\u5316\u3002\u5c0f\u56fe\u53ef\u80fd\u7b49\u6548\uff0c\u9ad8\u6570\u503c\u4e0d\u4fdd\u8bc1\u51c6\u786e\u7387\u5355\u8c03\u63d0\u9ad8\u3002</p></div><div class="card"><h3>\u663e\u5b58\u9884\u7b97 1024 MiB</h3><p>\u53ef\u8c03256–16384 MiB\uff0c\u4e3a\u68c0\u6d4b/\u8bc6\u522barena\u9884\u7b97\uff1b\u4e0d\u4f1a\u5f3a\u884c\u5360\u6ee11GiB\uff0c\u4e0d\u5305\u542b\u5168\u90e8\u9a71\u52a8/\u8fd0\u884c\u5e93\u5f00\u9500\u3002\u684c\u9762\u603b\u663e\u5b58\u4e0d\u662f\u672c\u8fdb\u7a0b\u5360\u7528\u3002</p></div></div><div class="note">Auto \u5bf9\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4fdd\u7559CPU\u4f18\u5148\u8def\u5f84\u3002CUDA\u7f6e\u4fe1\u5ea695\u53ea\u662f\u6a21\u578b\u5206\u6570\u95e8\u69db\uff0c\u4e0d\u80fd\u8bfb\u4f5c95%\u5b9e\u6d4b\u51c6\u786e\u7387\u3002</div></section>'
    body+='<section id="raw"><h2>\u539f\u59cb\u8bb0\u5f55\u4e0e\u590d\u73b0</h2><p>\u65b0\u6d4b\u91cf\u56fa\u5b9a\u6765\u6e90\uff1a<code>reports/teacher-review27/summary.json</code>\u3002\u6bcf\u8f6e\u539f\u59cb\u6570\u636e\u5728\u540c\u76ee\u5f55 <code>raw/</code>\uff0c\u8bb0\u5f55\u7248\u672c\u3001\u573a\u666f\u3001\u8def\u5f84\u3001\u7f13\u5b58\u53ca\u8bf7\u6c42\u6b21\u6570\u3002</p>'+( '<details><summary>\u6570\u636e\u6458\u8981\uff08\u539f\u59cb\u7ed3\u6784\uff09</summary><pre>'+esc(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre></details>' if summary else pending)+'</section>'
    md='# \u4e8c\u8272\u8776 0.01.27 · \u65b0\u6d4b\u91cf\u8bc4\u5ba1\u62a5\u544a\n\n**\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c\u66f4\u5c11\u7684\u7b49\u5f85**\n\n'+description+'\n\n\u65b0\u6d4b\u91cf\u6b63\u5728\u8fdb\u884c\uff1b\u5b8c\u6574\u65b9\u6cd5\u4e0e\u9010\u8f6e\u8bc1\u636e\u89c1\u79bb\u7ebf\u8bc4\u5ba1\u62a5\u544a\u3002\u5f53\u524d\u4e0d\u4ee5\u4efb\u4f55\u65e7\u7248\u6570\u5b57\u586b\u8865\u672a\u5b8c\u6210\u9879\u76ee\u3002\n'
    return shell('\u6027\u80fd\u4e0e\u65b9\u6cd5',body,'performance'),md

def manual_page(english,performance_md):
    import build_html_docs,build_english_docs
    pages=build_english_docs.PAGES if english else build_html_docs.PAGES
    records=[((DOCS/'en'/path if english else ROOT/path),label) for path,label in pages]
    targets={path.resolve():'p-'+path.stem.lower().replace('_','-') for path,_ in records}
    articles=[];missing=set()
    for path,label in records:
        source=performance_md if path.name=='PERFORMANCE_REPORT.md' else path.read_text(encoding='utf-8-sig')
        tokens=MD.parse(source)
        for token in tokens:
            for child in token.children or []:
                if child.type!='link_open':continue
                href=child.attrGet('href') or '';url=urlsplit(href)
                if url.scheme or url.netloc:continue
                if href=='performance.html':child.attrSet('href','performance.html');continue
                target=(path.parent/unquote(url.path)).resolve() if url.path else path.resolve()
                if target.is_relative_to(OUT.resolve()):
                    child.attrSet('href',target.relative_to(OUT.resolve()).as_posix()+('#'+url.fragment if url.fragment else ''));continue
                if target in targets:child.attrSet('href','#'+targets[target]);continue
                mapping={'PROJECT_MANUAL.html':'manual.zh.html','PROJECT_MANUAL.en.html':'manual.en.html','PROJECT_GUIDE.html':'architecture.html','PERFORMANCE_REPORT.html':'performance.html','PERFORMANCE_REPORT.en.html':'performance.en.html','CUSTOMER_GUIDE.html':'manual.zh.html#p-user-guide','CUSTOMER_GUIDE.en.html':'manual.en.html#p-user-guide','TEST_REPORT.json':'test-report.json'}
                if target.name in mapping:child.attrSet('href',mapping[target.name]);continue
                missing.add(str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else target.name)
                child.attrSet('href','#references')
                child.attrSet('title','\u53d1\u884c\u7248\u5bf9\u5e94\u6e90\u6587\u4ef6 / source supplied with the full release')
        articles.append('<article id="'+targets[path.resolve()]+'"><div class="chapter">'+esc(label)+'</div>'+MD.renderer.render(tokens,MD.options,{})+'</article>')
    toc='<aside class="toc"><strong>'+('Contents' if english else '\u5b8c\u6574\u624b\u518c · 18\u7ae0')+'</strong>'+''.join('<a href="#'+targets[path.resolve()]+'">'+esc(label)+'</a>' for path,label in records)+'</aside>'
    heading=hero('COMPLETE MANUAL / ENGLISH' if english else 'COMPLETE MANUAL / \u4e2d\u6587','Use, understand, verify.' if english else '\u4f7f\u7528\u3001\u7406\u89e3\u3001\u9a8c\u8bc1\u3002','The complete current manual, with a fresh .15 → .27 performance chapter and local navigation.' if english else '\u4fdd\u7559\u5b8c\u6574\u64cd\u4f5c\u4e0e\u6280\u672f\u7ae0\u8282\u3002\u6027\u80fd\u7ae0\u4f7f\u7528\u65b0\u4e00\u8f6e .15 → .27 \u8bc4\u5ba1\u53e3\u5f84\uff0c\u6587\u6863\u5728\u79bb\u7ebf\u73af\u5883\u4e2d\u53ef\u72ec\u7acb\u9605\u8bfb\u3002')
    references='<section id="references"><h2>'+('Source-file references' if english else '\u53d1\u884c\u7248\u539f\u59cb\u6587\u4ef6\u7d22\u5f15')+'</h2><p>'+('These optional source documents are supplied with the full release. This review bundle does not pretend to contain every source dependency.' if english else '\u4ee5\u4e0b\u94fe\u63a5\u6307\u5411\u5b8c\u6574\u53d1\u884c\u7248\u4e2d\u7684\u6e90\u6587\u4ef6\uff1b\u8bc4\u5ba1\u624b\u518c\u4fdd\u7559\u5176\u7d22\u5f15\uff0c\u4e0d\u5047\u88c5\u5728\u6b64\u8d44\u6599\u5305\u4e2d\u63d0\u4f9b\u6240\u6709\u6e90\u7801\u548c\u4f9d\u8d56\u3002')+'</p><pre>'+esc('\n'.join(sorted(missing)))+'</pre></section>'
    return shell('English manual' if english else '\u5b8c\u6574\u4e2d\u6587\u624b\u518c',heading+'<div class="manual-layout">'+toc+'<div class="manual">'+''.join(articles)+references+'</div></div>','manual.en' if english else 'manual.zh','en' if english else 'zh-CN')

def sync_canonical(summary,performance,zh,en):
    """Idempotently replace only current status/entrypoints, preserving history."""
    note_zh='0.01.27 \u52a0\u5165\u53ef\u9009 CUDA OCR\u3001\u540e\u53f0\u8054\u7f51\u8bed\u5883\u4e0e\u6574\u7ec4\u5b57\u53f7\u4fee\u590d\u3002\u672c\u7248\u65b0\u589e\u540c\u56fe OCR \u8bc4\u5ba1\uff0c\u5bf9\u7167 0.01.15\uff0c\u5206\u522b\u62a5\u544a\u51b7\u542f\u52a8\u3001\u80cc\u666f\u53d8\u5316\u70ed\u8def\u5f84\u3001\u590d\u8bbf\u7f13\u5b58\u548c\u9010\u5b57\u7cbe\u5ea6\uff1b\u771f\u5b9e API \u94fe\u8def\u53e6\u5217\u3002\u5386\u53f2\u8bc1\u636e\u4fdd\u7559\u539f\u7248\u672c\u6807\u7b7e\uff0c\u5f53\u524d\u65b9\u6cd5\u4e0e\u8303\u56f4\u89c1\u6027\u80fd\u62a5\u544a\u53ca TEST_REPORT.json\u3002'
    note_en='Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.'
    old_zh='0.01.27 \u52a0\u5165\u53ef\u9009 CUDA OCR\u3001\u540e\u53f0\u8054\u7f51\u8bed\u5883\u4e0e\u6574\u7ec4\u5b57\u53f7\u4fee\u590d\u3002\u5386\u53f2\u771f\u5b9e API\u3001\u622a\u56fe\u548c\u6e38\u620f\u6027\u80fd\u6570\u636e\u4ecd\u6807\u4e3a 0.01.25 / 0.01.15\uff1b\u672c\u7248\u8c03\u5ea6\u6a21\u62df\u5355\u72ec\u5217\u793a\uff0c\u4e0d\u7b49\u540c\u771f\u5b9e\u6e38\u620f\u6216 API \u5ef6\u8fdf\u3002\u5f53\u524d\u9a8c\u8bc1\u8303\u56f4\u89c1 TEST_REPORT.json\u3002'
    old_en='Version 0.01.27 adds optional CUDA OCR, background web context and group font fitting fixes. Historical real-API, screenshot and game measurements retain their 0.01.25 / 0.01.15 labels. This version has a separate simulated scheduling probe, not a real game/API latency measurement. See TEST_REPORT.json for current validation scope.'
    for path in [ROOT/'README.md',*DOCS.glob('*.md'),*(DOCS/'en').glob('*.md')]:
        if re.search(r'_0\.01\.',path.name):continue
        text=path.read_text(encoding='utf-8-sig')
        text=text.replace(old_zh,note_zh).replace(old_en,note_en)
        text=text.replace('\u5206\u522b\u5217\u51fa OCR\u3001\u9996\u6bb5\u8bd1\u6587\u63d0\u4ea4\u548c\u5b8c\u6574\u8bd1\u6587\u63d0\u4ea4\u65f6\u95f4\uff1b\u539f\u751f\u63d0\u4ea4\u8ba1\u65f6\u4e0d\u7b49\u4e8e\u663e\u793a\u5668\u5b9e\u9645\u663e\u793a\u5ef6\u8fdf\uff0c\u4e0d\u4ee5 150 ms \u4f5c\u4e3a\u603b\u5ef6\u8fdf\u4e0a\u9650\u3002','\u5206\u522b\u5217\u51fa\u672c\u5730OCR\u3001\u771f\u5b9eAPI\u9996\u4e2a\u53ca\u5b8c\u6574\u8bd1\u6587\u56de\u8c03\u65f6\u95f4\uff1b\u672c\u6b21\u672a\u6d4b\u539f\u751f\u7ed8\u5236\u6216\u663e\u793a\u5668\u5448\u73b0\uff0c\u56de\u8c03\u5230\u8fbe\u4e0d\u7b49\u4e8e\u5c4f\u5e55\u53ef\u89c1\uff0c\u4e5f\u4e0d\u4ee5150ms\u4f5c\u4e3a\u603b\u5ef6\u8fdf\u4e0a\u9650\u3002')
        text=text.replace('OCR, first translation submission and complete translation submission are distinct metrics. Native submission timing is not measured monitor presentation latency; 150 ms is not an end-to-end ceiling.','Local OCR, first translation callback and final translation callback are separate metrics. This fresh run does not measure native painting or monitor presentation; callback arrival is not screen visibility and 150ms is not an end-to-end ceiling.')
        text=text.replace('\u6700\u8fd1\u6027\u80fd\u4e3b\u62a5\u544a\u5b9e\u6d4b\u6bd4\u8f830.01.15\u4e0e0.01.25\uff1b0.01.27\u672a\u91cd\u6d4b\u8fd9\u4e9b\u5386\u53f2\u6837\u672c\uff1b\u5386\u53f2\u62a5\u544a\u4fdd\u7559\u539f\u7248\u53f7\u3002','\u5f53\u524d\u6027\u80fd\u4e3b\u62a5\u544a\u4f7f\u7528\u65b0\u4e00\u8f6e0.01.15\u4e0e0.01.27\u540c\u56feOCR\u5b9e\u6d4b\uff0c\u771f\u5b9eAPI\u89c2\u6d4b\u53e6\u5217\uff1b\u5386\u53f2\u62a5\u544a\u4fdd\u7559\u539f\u7248\u53f7\u3002')
        text=text.replace('for the historical 0.01.25 versus 0.01.15 measurements, with a separate 0.01.27 scheduling simulation','for the fresh 0.01.15 versus 0.01.27 same-image comparison and separately scoped real-API observations')
        if path.name=='README.md':
            marker='<!-- teacher-review27 -->'
            if marker not in text:
                link='../teacher-review27/index.html' if path.parent.name=='en' else 'docs/teacher-review27/index.html'
                intro='[Teacher review: complete bilingual manuals, fresh .15 → .27 measurements and UI gallery]('+link+').' if path.parent.name=='en' else '[\u6559\u5e08\u8bc4\u5ba1\u5165\u53e3\uff1a\u5b8c\u6574\u4e2d\u82f1\u624b\u518c\u30010.01.15 → 0.01.27 \u65b0\u6d4b\u91cf\u3001\u5b8c\u6574 UI \u56fe\u5e93]('+link+')\u3002'
                first,rest=text.split('\n',1);text=first+'\n\n'+marker+'\n'+intro+'\n'+rest
        write(path,text)
    for path in DOCS.glob('*.html'):
        if re.search(r'_0\.01\.',path.name):continue
        text=path.read_text(encoding='utf-8-sig').replace(old_zh,note_zh).replace(old_en,note_en)
        if path.name=='PROJECT_GUIDE.html' and 'teacher-review27/architecture.html' not in text:
            text=text.replace('</nav>',' · <a href="teacher-review27/architecture.html">\u5f53\u524d\u6a21\u5757\u3001\u7ebf\u7a0b\u4e0e\u76ee\u5f55\u56fe</a></nav>',1)
        if path.name=='PROJECT_GUIDE.html':
            text=text.replace('\u538b\u7f29\u5386\u53f2 → \u53ef\u9009\u8054\u7f51','\u538b\u7f29\u5386\u53f2 + \u5df2\u5b8c\u6210\u53c2\u8003').replace('\u663e\u793a\u524d\u5171\u540c\u62df\u5408','\u6d41\u5f0f\u5b57\u53f7\u4e0e\u5b8c\u6210\u62df\u5408').replace('\u6574\u7ec4\u62df\u5408 / \u77ed\u5c3e\u884c\u4e0d\u538b\u57ae\u6b63\u6587','\u6d41\u5f0f\u4fdd\u6301\u5b57\u53f7 / final\u6574\u7ec4\u62df\u5408')
        write(path,text)
    for path in (ROOT/'CHANGELOG.md',DOCS/'en/CHANGELOG.md'):
        text=path.read_text(encoding='utf-8-sig')
        if '<!-- teacher-review27 -->' not in text:
            stamp=datetime.now().astimezone().isoformat(timespec='minutes')
            detail=('## Documentation revision · '+stamp+'\n\nFresh 0.01.15 / 0.01.27 image-to-OCR comparison, separated cache/cold/warm/accuracy scopes, same-image OCR evidence, bilingual 18-chapter manuals and an offline teacher-review portal with a per-surface UI gallery. Real-API observations are independently scoped. No application binary or version change.\n\n' if path.parent.name=='en' else '## \u6587\u6863\u4e0e\u6027\u80fd\u8bc1\u636e\u4fee\u8ba2 · '+stamp+'\n\n\u65b0\u589e 0.01.15 / 0.01.27 \u540c\u56fe OCR \u5bf9\u7167\uff0c\u5206\u5f00\u7f13\u5b58\u3001\u51b7\u542f\u52a8\u3001\u70ed\u8def\u5f84\u548c\u5b57\u7b26\u7cbe\u5ea6\uff0c\u8865\u5145\u540c\u56fe\u8bc6\u522b\u6846/\u6587\u5b57\u3001\u5b8c\u6574\u4e2d\u82f1 18 \u7ae0\u624b\u518c\u53ca\u9010\u9875\u9762 UI \u56fe\u5e93\u3002\u771f\u5b9e API \u89c2\u6d4b\u72ec\u7acb\u6ce8\u660e\u8303\u56f4\u3002\u5e94\u7528\u4e8c\u8fdb\u5236\u53ca\u7248\u672c\u53f7\u4e0d\u53d8\u3002\n\n')
            first,rest=text.split('\n',1);write(path,first+'\n\n<!-- teacher-review27 -->\n'+detail+rest)
    write(DOCS/'PERFORMANCE_REPORT.md',zh);write(DOCS/'en/PERFORMANCE_REPORT.md',en)
    def rebase(text):
        def link(match):
            value=match[1];url=urlsplit(value)
            return match[0] if url.scheme or url.netloc or value.startswith('#') else 'href="teacher-review27/'+value+'"'
        return re.sub(r'href="([^"]+)"',link,text)
    write(DOCS/'PERFORMANCE_REPORT.html',rebase(performance))
    from teacher_review_evidence27 import render_english
    english=render_english(sys.modules[__name__],summary)
    write(DOCS/'PERFORMANCE_REPORT.en.html',rebase(english))
    write(OUT/'performance.en.html',english)
    report={'schema':3,'version':VERSION,'measurement_version':VERSION,'distributed_with_version':VERSION,'baseline':BASELINE,'rebenchmarked':True,
      'measurement_kind':'fresh paired offline image-to-OcrCore; real-API pipeline observations separately scoped',
      'measured_at':summary['measured_at'],'source_report':'reports/teacher-review27/summary.json','portal':'teacher-review27/index.html',
      'offline_ocr':summary,'controls':load(EVIDENCE/'controls.json',{}),'real_api':load(EVIDENCE/'e2e-summary.json'),
      'limitations':['Not monitor scan-out latency','Changed background retains text and eligible subregion caches','Accuracy is transcription, not semantic translation','Concurrent UI capture load; no causal attribution for outliers']}
    write(DOCS/'PERFORMANCE_REPORT.json',json.dumps(report,ensure_ascii=False,indent=2))
    update=load(DOCS/'UPDATE.json');update['notes']='Optional CUDA OCR, post-display context and group fitting. Documentation refreshed with a fresh paired 0.01.15 versus 0.01.27 OCR review, separately scoped real-API observations, complete bilingual manuals and per-surface UI evidence; no binary version change.';write(DOCS/'UPDATE.json',json.dumps(update,ensure_ascii=False,indent=2))
    tests=load(DOCS/'TEST_REPORT.json');tests.update(performance_measurement_version=VERSION,performance_rebenchmarked=True,
      current_measurements_scope='Fresh paired same-image offline OCR, 0.01.15 versus 0.01.27; cold/warm/cache/character accuracy separated. Real-API pipeline observations, if present, independently scoped; not live-game display certification.',
      performance_review={'report':'reports/teacher-review27/summary.json','baseline':BASELINE,'offline_api_requests':0,'measured_at':summary['measured_at'],'real_api_report':'reports/teacher-review27/e2e-summary.json' if (EVIDENCE/'e2e-summary.json').is_file() else None})
    tests['current_simulation']='Historical separate scheduling simulation: reports/context-latency27.json; not the current performance headline.'
    write(DOCS/'TEST_REPORT.json',json.dumps(tests,ensure_ascii=False,indent=2))
    import build_html_docs,build_english_docs
    build_html_docs.build();build_english_docs.build()
    subprocess.run([sys.executable,str(ROOT/'tools/build_delivery.py'),'--docs-only'],cwd=ROOT,check=True,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sync-canonical',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    summary=load(EVIDENCE/'summary.json')
    inventory=load(EVIDENCE/'ui-inventory.json',{'screenshots':[],'unavailable':[]})
    from teacher_review_evidence27 import render,markdown as measured_markdown
    performance,markdown=render(sys.modules[__name__],summary) if summary else performance_material(summary)
    english=measured_markdown(summary,True,load(EVIDENCE/'e2e-summary.json'))
    if args.sync_canonical:
        if not summary or summary.get('failures'):raise RuntimeError('Canonical sync requires completed measurements.')
        sync_canonical(summary,performance,markdown,english)
    write(OUT/'index.html',index_page(summary,inventory));write(OUT/'architecture.html',architecture_page());write(OUT/'gallery.html',gallery_page(inventory))
    write(OUT/'performance.html',performance)
    write(OUT/'manual.zh.html',manual_page(False,markdown))
    write(OUT/'manual.en.html',manual_page(True,english))
    write(OUT/'evidence.json',json.dumps(summary,ensure_ascii=False,indent=2))
    write(OUT/'controls.json',json.dumps(load(EVIDENCE/'controls.json',{}),ensure_ascii=False,indent=2))
    write(OUT/'test-report.json',json.dumps(load(DOCS/'TEST_REPORT.json',{}),ensure_ascii=False,indent=2))
    write(OUT/'README.txt','Open index.html. Offline teacher review, 0.01.15 baseline versus 0.01.27.\nKeep relative folders intact when extracting split archives.\nNo credentials, personal settings, private history or game binaries are included.\n')
    write(OUT/'README.md','''# \u4e8c\u8272\u8776 0.01.27 · \u79bb\u7ebf\u8bc4\u5ba1\u8d44\u6599

\u4ece [index.html](index.html) \u5f00\u59cb\u3002\u5b8c\u6574\u64cd\u4f5c\u548c\u6280\u672f\u624b\u518c\u5206\u522b\u4e3a [\u4e2d\u6587](manual.zh.html) \u4e0e [English](manual.en.html)\u3002[\u6027\u80fd\u62a5\u544a](performance.html)\u3001[English performance](performance.en.html)\u3001[\u6a21\u5757/\u7ebf\u7a0b/\u6d41\u7a0b](architecture.html)\u3001[UI\u56fe\u5e93](gallery.html) \u5747\u53ef\u79bb\u7ebf\u4f7f\u7528\u3002

\u5206\u5305\u65f6\u4fdd\u7559\u76f8\u5bf9\u76ee\u5f55\uff1b\u622a\u56fe\u9875\u9762\u5185\u5d4c\u539f\u56fe\uff0c\u4e0d\u4f9d\u8d56\u7f51\u7edc\u6216\u5916\u90e8PNG\u3002\u8bc1\u636eJSON\u4fdd\u7559\u5168\u90e8\u8ba1\u65f6\u6837\u672c\u3001\u8bc4\u5206\u533a\u548c\u5b9e\u9645\u8bc6\u522b\u6587\u5b57\u3002\u9010\u8f6e\u5b9e\u73b0\u54c8\u5e0c\u65e5\u5fd7\u4ecd\u5728\u5b8c\u6574\u9879\u76ee\u7684 `reports/teacher-review27/raw/`\u3002

\u672c\u6b21\u56fe\u8868\u751f\u6210\u73af\u5883\u4e3a\u5f00\u53d1\u7528 CPython 3.13.5 / Matplotlib 3.10.0 / Pillow 12.2.0 / markdown-it-py 2.2.0\u3002\u5e94\u7528\u4e0e\u5bf9\u7167\u5b9e\u9a8c\u4f7f\u7528\u5404\u6d4b\u91cf\u8bb0\u5f55\u6ce8\u660e\u7684\u8fd0\u884c\u65f6\uff08\u672c\u6b21\u4e3a\u9879\u76eeCPython 3.14.10\uff09\uff0c\u4e24\u8005\u4e0d\u80fd\u6df7\u540c\u3002\u751f\u6210\u62a5\u544a\u4e0d\u8bf7\u6c42API\u3001\u4e0d\u8bfb\u79c1\u4eba\u914d\u7f6e\u3002

\u5728\u5b8c\u65740.01.27\u6e90\u7801\u76ee\u5f55\u91cd\u5efa\uff1a

```powershell
python -X utf8 tools/build_teacher_review27.py --sync-canonical
python -X utf8 tools/check_manuals.py
```

\u8f93\u5165\u5fc5\u987b\u4fdd\u7559\u672c\u6b21 `reports/teacher-review27/summary.json`\u3001controls\u3001\u539f\u56fefixtures\u548c\u622a\u56feinventory\u3002\u771f\u5b9eAPI\u89c2\u6d4b\u53ea\u5728e2e-summary\u5b9e\u9645\u5b58\u5728\u65f6\u5217\u51fa\u3002\u5386\u53f2\u8fc1\u79fb\u811a\u672c build_docs27/build_gpu_report27 \u4e0d\u518d\u7528\u4e8e\u8986\u76d6\u5f53\u524d\u62a5\u544a\u3002\u6b64\u6b65\u9aa4\u53ea\u751f\u6210\u6587\u6863\uff1b\u53d1\u5e03\u5305\u7531\u72ec\u7acb\u6784\u5efa\u548c\u9a8c\u8bc1\u6d41\u7a0b\u5904\u7406\u3002
''')
    print(json.dumps({'output':str(OUT),'measurement_ready':summary is not None,'screenshots':len(inventory.get('screenshots',[])),'canonical_updated':args.sync_canonical}))

if __name__=='__main__':main()
