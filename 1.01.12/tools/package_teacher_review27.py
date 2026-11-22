# SPDX-License-Identifier: MIT
"""Build portable review materials and attachment-sized independent ZIP parts.

No config, game assets, private history or API credentials are read. Parts all
extract into the same teacher-review27 directory; each ZIP is independently
readable. This never sends mail or arms shutdown.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import zipfile
import zlib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'teacher-review27'
REPORTS = ROOT / 'reports' / 'teacher-review27'
LIMIT = 2_850_000  # Outlook direct file attachment limit is below 3 MB.
ALLOWED = {'.html', '.md', '.txt', '.json', '.svg', '.png', '.csv'}
SECRET = re.compile(rb'sk-[A-Za-z0-9_-]{20,}')


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.links=[]; self.ids=set(); self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        for key in ('href','src','poster'):
            if attrs.get(key):self.links.append(attrs[key])


def verify_links(stage):
    parsed={p.resolve():Links(p.read_text(encoding='utf-8')) for p in stage.rglob('*.html')}
    failures=[]
    for file,document in parsed.items():
        for link in document.links:
            url=urlsplit(link)
            if url.scheme or url.netloc:continue
            target=(file.parent/unquote(url.path)).resolve() if url.path else file
            if not target.is_relative_to(stage.resolve()) or not target.exists():
                failures.append((str(file.relative_to(stage)),link))
            elif url.fragment and target in parsed and unquote(url.fragment) not in parsed[target].ids:
                failures.append((str(file.relative_to(stage)),link))
    if failures:raise ValueError('Nonportable links: '+repr(failures[:20]))


def main():
    stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    delivery = ROOT / 'delivery' / ('teacher-review-' + stamp)
    stage = delivery / 'teacher-review27'
    stage.mkdir(parents=True)
    assert (SOURCE / 'index.html').is_file()
    for file in sorted(SOURCE.rglob('*')):
        if not file.is_file():
            continue
        relative = file.relative_to(SOURCE)
        if file.suffix.lower() not in ALLOWED or any(not p.isascii() for p in relative.parts):
            raise ValueError('Unexpected review artifact: ' + str(relative))
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    browser = json.loads((REPORTS / 'document-browser.json').read_text(encoding='utf-8'))
    assert browser['passed'], 'Browser verification failed'
    docshots = stage / 'document-screenshots'
    docshots.mkdir()
    cards = []
    for item in browser['screenshots']:
        name = item['file']
        assert Path(name).name == name and name.isascii()
        shutil.copy2(REPORTS / 'document-screenshots' / name, docshots / name)
        cards.append('<figure><a href="'+html.escape(name)+'"><img loading="lazy" src="'+html.escape(name)+'" alt="'+html.escape(item['title'])+'"></a><figcaption>'+html.escape(item['title'])+' · '+html.escape(item['view'])+(' · mobile' if item['mobile'] else '')+'</figcaption></figure>')
    (docshots/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>\u6587\u6863\u5b9e\u62cd · 0.01.27</title><style>body{font:16px system-ui;background:#f5f2ed;color:#232228;max-width:1350px;margin:40px auto;padding:20px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}figure{margin:0;background:white;padding:12px;border-radius:12px}img{width:100%;height:260px;object-fit:contain;object-position:top;background:#eee}figcaption{padding:10px}</style><a href="../index.html">\u8fd4\u56de\u8bc4\u5ba1\u5165\u53e3</a><h1>\u6587\u6863\u5b9e\u9645\u6e32\u67d3\u622a\u56fe</h1><p>\u9694\u79bb\u6d4f\u89c8\u5668\u5b9e\u9645\u6e32\u67d3\uff1b\u6bcf\u5e45\u56fe\u4e3a\u4e00\u4e2a\u89c6\u53e3\uff0c\u7ae0\u8282\u9875\u4e0d\u662f\u5168\u6587\u957f\u622a\u56fe\u3002\u70b9\u51fb\u67e5\u770b\u539f\u59cb PNG\u3002\u5b8c\u6574\u5185\u5bb9\u89c1\u53ef\u68c0\u7d22 HTML \u624b\u518c\u3002</p><main>'+''.join(cards)+'</main></html>',encoding='utf-8')
    (stage/'DOCUMENT_SCREENSHOTS.html').write_text('<!doctype html><meta charset="utf-8"><title>\u6587\u6863\u622a\u56fe\u5165\u53e3</title><a href="document-screenshots/index.html">\u6253\u5f00\u5168\u90e8\u6587\u6863\u622a\u56fe</a>',encoding='utf-8')
    (stage/'README.txt').write_text('Nishokuchou 0.01.27 | Teacher review\n\nOpen index.html in a browser. UI gallery: gallery.html.\nDocument rendering screenshots: document-screenshots/index.html.\nComplete manuals: manual.zh.html and manual.en.html.\nAll content works offline. No private API configuration is included.\n\nEmail parts are ordinary independent ZIP files. Extract ALL parts to the SAME folder; their teacher-review27/ paths merge automatically. Parts are not a split ZIP and do not need a joining utility.\n\nCreated: '+datetime.now().astimezone().isoformat()+'\n',encoding='utf-8')
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    for file in files:
        if file.suffix.lower() not in {'.png'} and SECRET.search(file.read_bytes()):
            raise ValueError('Credential-like token blocked in '+file.name)
        if file.name.lower() in {'credentials.bin','local.json'}:
            raise ValueError('Private file blocked')
    verify_links(stage)
    # Put the main entry first, then regular docs, then screenshot evidence.
    files.sort(key=lambda p:(p.relative_to(stage).parts[0] in {'screenshots','document-screenshots','assets'},str(p)))
    groups, group, estimate = [], [], 0
    for file in files:
        relative = 'teacher-review27/'+file.relative_to(stage).as_posix()
        size = len(zlib.compress(file.read_bytes(),9)) + len(relative.encode())*2 + 200
        if size > LIMIT-10000:
            raise ValueError('Single artifact too large for direct mail: '+str(file))
        if group and estimate+size > LIMIT-10000:
            groups.append(group);group=[];estimate=0
        group.append(file);estimate+=size
    if group:groups.append(group)
    attachments=[]
    for i,group in enumerate(groups,1):
        file=delivery/f'nishokuchou-0.01.27-review-{i:02d}-of-{len(groups):02d}.zip'
        with zipfile.ZipFile(file,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for member in group:archive.write(member,'teacher-review27/'+member.relative_to(stage).as_posix())
        assert file.stat().st_size < LIMIT
        with zipfile.ZipFile(file) as archive:assert archive.testzip() is None
        attachments.append({'file':str(file),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'members':len(group)})
    complete=delivery/'nishokuchou-0.01.27-teacher-review-complete.zip'
    with zipfile.ZipFile(complete,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for file in files:archive.write(file,'teacher-review27/'+file.relative_to(stage).as_posix())
    result={'version':'0.01.27','created':datetime.now().astimezone().isoformat(),'root':str(delivery),'entry':str(stage/'index.html'),'complete_zip':str(complete),'public_files':len(files),'document_screenshots':len(browser['screenshots']),'attachments':attachments,'private_data_included':False,'emails_sent':False,'shutdown_armed':False}
    (delivery/'MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (REPORTS/'delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
