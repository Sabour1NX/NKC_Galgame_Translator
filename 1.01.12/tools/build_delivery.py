# SPDX-License-Identifier: MIT
"""Create customer documents and a public delivery directory from allowlists."""
from pathlib import Path
import argparse,hashlib,html,json,re,shutil,zipfile
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
VERSION=ROOT.name
parser=argparse.ArgumentParser();parser.add_argument('--docs-only',action='store_true');parser.add_argument('--publish-root',action='store_true');args=parser.parse_args()
md=MarkdownIt('commonmark',{'html':False}).enable('table')
CSS='''*{box-sizing:border-box}body{margin:0;background:#f6f3ef;color:#252429;font:17px/1.85 "Microsoft YaHei UI",system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:38px 32px}header{border-top:5px solid #bc2942;padding:26px 0 36px}h1{font-size:48px;line-height:1.3;letter-spacing:-1px}h2{margin-top:38px;font-size:25px}p{color:#635b60}a{color:#b4233f;text-decoration:none}nav{display:flex;gap:24px;flex-wrap:wrap}.eyebrow{color:#bc2942;font-size:12px;letter-spacing:3px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}.card{padding:24px;background:#fff;border:1px solid #e3d9d3;border-radius:12px}.card h2{margin:4px 0 8px}.card p{font-size:15px}code{font:13px/1.6 Consolas,monospace;overflow-wrap:anywhere}table{display:block;overflow:auto;border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}.button{display:inline-block;background:#b92741;color:#fff;padding:10px 20px;border-radius:6px}footer{border-top:1px solid #ddd;margin-top:40px;padding:18px 0;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}@media(max-width:700px){main{padding:20px}.grid{grid-template-columns:1fr}h1{font-size:36px}}'''
def page(title,body,lang='zh-CN'):
    return '<!doctype html><html lang="'+lang+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:"><title>'+html.escape(title)+'</title><style>'+CSS+'</style></head><body><main>'+body+'</main></body></html>'

english=(ROOT/'docs/en/CUSTOMER_GUIDE.md').read_text(encoding='utf-8')
chinese=(ROOT/'docs/CUSTOMER_GUIDE.md').read_text(encoding='utf-8')
(ROOT/'docs/CUSTOMER_GUIDE.html').write_text(page('\u4e8c\u8272\u8776 '+VERSION+' · \u4f7f\u7528\u6307\u5357',md.render(chinese)),encoding='utf-8')
(ROOT/'docs/CUSTOMER_GUIDE.en.html').write_text(page('Nishokuchou 0.01.27 · User guide',md.render(english).replace('href="../','href="'),'en'),encoding='utf-8')
if args.docs_only:raise SystemExit(0)

assert json.loads((ROOT/'reports/package-verification.json').read_text(encoding='utf-8'))['passed']
delivery=ROOT/'delivery';customer=delivery/'customer';release=delivery/'release'
for folder in (customer,release):folder.mkdir(parents=True,exist_ok=True)
allowed={'index.html','USER_GUIDE.html','USER_GUIDE.en.html','PERFORMANCE.html','PERFORMANCE.en.html',
         'PERFORMANCE.json','TEST_REPORT.json','AGREEMENT.html','AGREEMENT.en.html','AGREEMENT.ja.html','LICENSE.txt','README.txt'}
# Do not silently carry unrelated private files into this customer bundle.
assert all((p.name in allowed and p.is_file()) or (p.name=='teacher-review27' and p.is_dir()) for p in customer.iterdir())
# The report navigation points into this public, self-contained review folder.
# Copy an exact extension allowlist and reject any unexpected existing payload.
review_source=ROOT/'docs/teacher-review27';review_dest=customer/'teacher-review27'
if review_source.is_dir():
    review_files={p.relative_to(review_source) for p in review_source.rglob('*') if p.is_file() and p.suffix.lower() in ('.html','.svg','.json','.txt')}
    if review_dest.exists():
        assert all(p.relative_to(review_dest) in review_files for p in review_dest.rglob('*') if p.is_file())
    for relative in sorted(review_files):
        target=review_dest/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(review_source/relative,target)
shutil.copy2(ROOT/'docs/TEST_REPORT.json',customer/'TEST_REPORT.json')

overview='''<header><span class="eyebrow">NISHOKUCHOU · 0.01.27</span><h1>\u770b\u61c2\u6e38\u620f\uff0c<br>\u5c31\u5728\u539f\u4f4d\u3002</h1><p>\u591a\u79cd\u8bed\u8a00\u5b9e\u65f6\u7ffb\u8bd1\uff0c\u8bd1\u6587\u8ddf\u968f\u539f\u6587\u4f4d\u7f6e\uff0c\u8ba9\u4f60\u4e13\u6ce8\u6e38\u620f\u3002</p><nav><a class="button" href="USER_GUIDE.html">\u5f00\u59cb\u4f7f\u7528</a><a href="PERFORMANCE.html">\u6027\u80fd\u4e0e\u8bc6\u522b\u8868\u73b0</a><a href="USER_GUIDE.en.html">English guide</a></nav></header><div class="grid"><article class="card"><h2>\u539f\u4f4d\u9605\u8bfb</h2><p>\u5267\u60c5\u3001\u83dc\u5355\u4e0e\u8bf4\u660e\u4fdd\u6301\u5728\u6e38\u620f\u6587\u5b57\u533a\u57df\u3002\u79fb\u52a8\u7a97\u53e3\uff0c\u8bd1\u6587\u968f\u4e4b\u79fb\u52a8\u3002</p></article><article class="card"><h2>\u6d41\u5f0f\u5448\u73b0</h2><p>\u591a\u4e2a\u6587\u5b57\u6846\u5e76\u53d1\u5904\u7406\uff0c\u63a5\u6536\u8bd1\u6587\u540e\u9010\u6b65\u663e\u793a\uff0c\u9f20\u6807\u70b9\u51fb\u53ef\u7a7f\u8fc7\u8986\u76d6\u5c42\u3002</p></article><article class="card"><h2>\u6309\u4f60\u4e60\u60ef\u663e\u793a</h2><p>\u5b57\u4f53\u3001\u5b57\u53f7\u3001\u8bed\u8a00\u6807\u7b7e\u4e0e\u622a\u56fe\u663e\u793a\u53ef\u8c03\uff1b\u8f83\u957f\u8bd1\u6587\u5728\u5141\u8bb8\u8303\u56f4\u5185\u7f29\u5c0f\u3002</p></article><article class="card"><h2>\u5ef6\u7eed\u6e38\u620f\u8bed\u5883</h2><p>\u4e3a\u6e38\u620f\u4fdd\u7559\u672f\u8bed\u4e0e\u4e0a\u4e0b\u6587\u53c2\u8003\uff0c\u8ba9\u540e\u7eed AI \u8bf7\u6c42\u4f7f\u7528\u540c\u4e00\u4efd\u6e38\u620f\u6863\u6848\u3002</p></article></div><footer>Windows 10/11 x64 · \u9700\u8981\u81ea\u884c\u914d\u7f6e\u517c\u5bb9 API<br><a href="AGREEMENT.html">\u7528\u6237\u534f\u8bae</a> · <a href="AGREEMENT.en.html">English agreement</a> · <a href="AGREEMENT.ja.html">\u65e5\u672c\u8a9e</a> · <a href="LICENSE.txt">MIT</a></footer>'''
(customer/'index.html').write_text(page('\u4e8c\u8272\u8776 · \u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1',overview),encoding='utf-8')
guide=(ROOT/'docs/CUSTOMER_GUIDE.md').read_text(encoding='utf-8')
guide=re.sub(r'\[([^]]+)\]\(CONTEXT_AGENT\.md\)',r'\1',guide)
guide=guide.split('\u5f00\u53d1\u8005\u53ef\u67e5\u9605')[0].rstrip()+'\n'
guide=guide.replace('PERFORMANCE_REPORT.html','PERFORMANCE.html').replace('USER_AGREEMENT.md','AGREEMENT.html')
(customer/'USER_GUIDE.html').write_text(page('\u4e8c\u8272\u8776 0.01.27 · \u4f7f\u7528\u6307\u5357','<nav><a href="index.html">\u4e8c\u8272\u8776</a><a href="PERFORMANCE.html">\u6027\u80fd\u62a5\u544a</a><a href="USER_GUIDE.en.html">English</a></nav>'+md.render(guide)),encoding='utf-8')
en=english.replace(' See the [user agreement](../USER_AGREEMENT.en.md) for the disclaimer and MIT license, and the [complete manual](../PROJECT_MANUAL.en.html) for technical reference.',' See the [user agreement](AGREEMENT.en.html) for the disclaimer and MIT license.')
en=en.replace('../PERFORMANCE_REPORT.en.html','PERFORMANCE.en.html').replace('../USER_AGREEMENT.en.md','AGREEMENT.en.html')
en=re.sub(r'\[([^]]+)\]\(\.\./PROJECT_MANUAL\.en\.html[^)]*\)',r'\1 (included in the application documentation)',en)
en=re.sub(r'\[([^]]+)\]\((?:\.\./)?CONTEXT_AGENT\.md\)',r'\1',en)
(customer/'USER_GUIDE.en.html').write_text(page('Nishokuchou 0.01.27 · User guide','<nav><a href="index.html">Nishokuchou</a><a href="PERFORMANCE.en.html">Performance</a></nav>'+md.render(en),'en'),encoding='utf-8')
perf=(ROOT/'docs/PERFORMANCE_REPORT.html').read_text(encoding='utf-8')
perf=perf.replace('CUSTOMER_GUIDE.html','USER_GUIDE.html').replace('PERFORMANCE_REPORT.json','PERFORMANCE.json').replace('PERFORMANCE_REPORT.en.html','PERFORMANCE.en.html')
perf=perf.replace('<a href="PROJECT_MANUAL.html">\u5b8c\u6574\u9879\u76ee\u624b\u518c</a>','<a href="AGREEMENT.html">\u7528\u6237\u534f\u8bae</a>').replace('<a href="PROJECT_MANUAL.en.html">English manual</a>','<a href="USER_GUIDE.en.html">English guide</a>')
(customer/'PERFORMANCE.html').write_text(perf,encoding='utf-8')
perf_en=(ROOT/'docs/PERFORMANCE_REPORT.en.html').read_text(encoding='utf-8')
perf_en=re.sub(r'<p>Open the.*?</p>','<p><a href="PERFORMANCE.html">Interactive image evidence</a> · <a href="USER_GUIDE.en.html">User guide</a></p>',perf_en,flags=re.S)
perf_en=perf_en.replace('PERFORMANCE_REPORT.json','PERFORMANCE.json').replace('; see <a href="TEST_REPORT.json">test evidence</a>.','. The full technical evidence is included with the application source distribution.')
perf_en=perf_en.replace('PERFORMANCE_REPORT.html','PERFORMANCE.html')
perf_en=perf_en.replace('<a href="PROJECT_MANUAL.html">Chinese project manual</a>','<a href="AGREEMENT.en.html">User agreement</a>').replace('<a href="PROJECT_MANUAL.en.html">English manual</a>','<a href="USER_GUIDE.en.html">English guide</a>')
(customer/'PERFORMANCE.en.html').write_text(perf_en,encoding='utf-8')
shutil.copy2(ROOT/'docs/PERFORMANCE_REPORT.json',customer/'PERFORMANCE.json')
for suffix,lang in (('', 'zh-CN'),('.en','en'),('.ja','ja')):
    source=ROOT/'docs'/f'USER_AGREEMENT{suffix}.md'
    (customer/f'AGREEMENT{suffix}.html').write_text(page('\u4e8c\u8272\u8776 · User agreement',md.render(source.read_text(encoding='utf-8')),lang),encoding='utf-8')
shutil.copy2(ROOT/'LICENSE',customer/'LICENSE.txt')
(customer/'README.txt').write_text('Open index.html. All documents work offline.\nCustomer materials for Nishokuchou 0.01.27.\nThis folder contains no API key, configuration, private history or game program.\n',encoding='utf-8')
for suffix in ('windows-x64.zip','source.zip','SHA256SUMS.txt'):
    name=f'NKC_Galgame_Translator-{VERSION}-{suffix}'
    shutil.copy2(ROOT/'dist'/name,release/name)
for suffix in ('cuda-addon.zip','cuda-addon-SHA256SUMS.txt'):
    name=f'NKC_Galgame_Translator-{VERSION}-{suffix}'
    source,destination=ROOT/'dist'/name,release/name
    if source.is_file():
        destination.unlink(missing_ok=True)
        try:destination.hardlink_to(source)
        except OSError:shutil.copy2(source,destination)
with zipfile.ZipFile(delivery/f'NKC_Galgame_Translator-{VERSION}-customer-docs.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(customer.rglob('*')):
        if p.is_file():z.write(p,'customer/'+p.relative_to(customer).as_posix())
(delivery/'index.html').write_text(page('\u4e8c\u8272\u8776 · \u5bf9\u5916\u4ea4\u4ed8','<header><span class="eyebrow">PUBLIC DELIVERY / 0.01.27</span><h1>\u4e8c\u8272\u8776 · \u5bf9\u5916\u4ea4\u4ed8</h1><p>\u5ba2\u6237\u8d44\u6599\u548c\u516c\u5f00\u8f6f\u4ef6\u5305\u3002</p></header><div class="grid"><article class="card"><h2>\u5ba2\u6237\u8d44\u6599</h2><p>\u4ea7\u54c1\u4ecb\u7ecd\u3001\u4f7f\u7528\u6307\u5357\u3001\u6027\u80fd\u62a5\u544a\u4e0e\u4e2d\u82f1\u65e5\u534f\u8bae\u3002</p><a href="customer/index.html">\u6253\u5f00\u8d44\u6599</a></article><article class="card"><h2>\u516c\u5f00\u8f6f\u4ef6</h2><p>Windows x64 \u7a0b\u5e8f\u5305\u3001\u5bf9\u5e94\u6e90\u7801\u548c SHA256 \u6e05\u5355\u3002</p><a href="release/">\u6253\u5f00\u53d1\u884c\u6587\u4ef6\u5939</a></article></div>'),encoding='utf-8')
(delivery/'README.txt').write_text('Public delivery for Nishokuchou 0.01.27\n\ncustomer/ : offline customer presentation, guides, performance evidence and agreements\nrelease/  : public Windows x64 ZIP, corresponding-source ZIP and SHA256 list\nnishokuchou-0.01.27-customer-docs.zip : customer/ as one shareable attachment\n\nPrivate API configuration and history are not included.\n',encoding='utf-8')

locations=[('\u5ba2\u6237\u5c55\u793a\u4e0e\u624b\u518c','delivery/customer/index.html','delivery/customer/','\u53ef\u76f4\u63a5\u7ed9\u5ba2\u6237\uff1a\u4ea7\u54c1\u4ecb\u7ecd\u3001\u64cd\u4f5c\u6307\u5357\u3001\u6027\u80fd\u62a5\u544a\u53ca\u534f\u8bae\u3002'),
 ('\u516c\u5f00\u53d1\u5e03\u6587\u4ef6','delivery/index.html','delivery/release/','Windows x64 ZIP\u3001\u5bf9\u5e94\u6e90\u7801 ZIP\u3001SHA256 \u6e05\u5355\u3002'),
 ('\u53ef\u9009 CUDA \u6269\u5c55','dist/nishokuchou-0.01.27-cuda-addon.zip','dist/nishokuchou-0.01.27-cuda-addon.zip','\u5173\u95ed\u7a0b\u5e8f\u540e\u89e3\u538b\u5230\u7a0b\u5e8f\u6839\u76ee\u5f55\u3002\u5185\u542b\u72ec\u7acb\u8fd0\u884c\u73af\u5883\u3001\u6a21\u578b\u548c\u7b2c\u4e09\u65b9\u8bb8\u53ef\uff1b\u9700\u8981\u517c\u5bb9\u7684 NVIDIA GPU \u4e0e\u9a71\u52a8\u3002'),
 ('\u672c\u673a\u7a7a\u914d\u7f6e\u8bd5\u7528','trial/nishokuchou-0.01.27-trial/','trial/nishokuchou-0.01.27-trial/','\u53ef\u8fd0\u884c\u516c\u5f00\u7248\uff1b\u4f7f\u7528\u8005\u81ea\u884c\u586b\u5199 API\u3002'),
 ('\u79c1\u4eba\u914d\u7f6e\u8fd0\u884c\u7248','demo/NeedyGirlOverdose/','demo/NeedyGirlOverdose/','\u4fdd\u7559\u539f\u52a0\u5bc6 API \u4e0e\u6e38\u620f\u6863\u6848\uff0c\u4ec5\u4e2a\u4eba\u4f7f\u7528\u3002'),
 ('\u5b8c\u6574\u5f00\u53d1\u8d44\u6599','docs/PROJECT_MANUAL.html','./','\u6e90\u7801\u3001\u7ed3\u6784\u56fe\u3001\u63a5\u53e3\u3001\u6d4b\u8bd5\u53ca\u6784\u5efa\uff1bconfig/ \u542b\u79c1\u4eba\u52a0\u5bc6\u914d\u7f6e\u3002'),
 ('\u5185\u90e8\u8bb0\u5f55','reports/internal/','reports/','\u6d4b\u8bd5\u3001\u539f\u59cb\u8ba1\u65f6\u3001\u5185\u90e8\u5206\u6790\u548c\u4ea4\u4ed8\u6838\u9a8c\u3002')]
cards=''.join('<article class="card"><h2>'+title+'</h2><code>'+path+'</code><p>'+description+'</p><a href="'+href+'">\u6253\u5f00</a></article>' for title,href,path,description in locations)
index=page('\u4e8c\u8272\u8776 0.01.27 · \u76ee\u5f55\u5165\u53e3','<header><span class="eyebrow">WORKSPACE INDEX / 0.01.27</span><h1>\u8d44\u6599\u4e0e\u7a0b\u5e8f\uff0c\u6309\u7528\u9014\u6253\u5f00\u3002</h1><p>\u5bf9\u5916\u53d1\u9001\u4f7f\u7528 delivery/\uff1b\u4e2a\u4eba\u8fd0\u884c\u4f7f\u7528 demo/NeedyGirlOverdose/\u3002</p></header><div class="grid">'+cards+'</div><footer>\u6240\u6709\u76ee\u5f55\u4f7f\u7528 ASCII \u540d\u79f0\u3002\u5df2\u6709\u7a0b\u5e8f\u8def\u5f84\u4fdd\u7559\uff0c\u907f\u514d\u5f71\u54cd\u5bfc\u5165\u3001\u8fd0\u884c\u6216\u5bc6\u94a5\u8bfb\u53d6\u3002</footer>')
(ROOT/'OPEN_FIRST.html').write_text(index,encoding='utf-8')
if args.publish_root:
    (ROOT.parent/'OPEN_FIRST.html').write_text(page('\u4e8c\u8272\u8776 · \u9879\u76ee\u5165\u53e3','<header><h1>\u4e8c\u8272\u8776 · \u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1</h1><p>\u5f53\u524d\u7248\u672c 0.01.27</p><a class="button" href="0.01.27/OPEN_FIRST.html">\u6253\u5f00\u76ee\u5f55\u5165\u53e3</a></header>'),encoding='utf-8')
(ROOT/'DIRECTORIES.txt').write_text('Nishokuchou 0.01.27 - directory map\n\n'+'\n'.join(path+' : '+description for _,_,path,description in locations)+'\n\nOPEN_FIRST.html is the local index. delivery/ is the public handoff.\n',encoding='utf-8')
(ROOT/'reports/internal').mkdir(exist_ok=True)
(ROOT/'reports/internal/README.txt').write_text('Internal development records\nRaw benchmark JSON, test logs and release checks remain in reports/ for reproducibility.\nThis directory is excluded from public packages.\n',encoding='utf-8')
print(json.dumps({'version':VERSION,'delivery':str(delivery),'customer_files':len(list(customer.iterdir())),'private_files_copied':False}))
