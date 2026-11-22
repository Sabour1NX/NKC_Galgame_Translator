# SPDX-License-Identifier: MIT
"""Build a standalone, script-free manual from reviewed repository documents."""
import html
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ('README.md', '\u5f00\u59cb\u4f7f\u7528'), ('docs/USER_GUIDE.md', '\u7528\u6237\u6307\u5357'), ('docs/PERFORMANCE_REPORT.md', '\u54cd\u5e94\u901f\u5ea6\u4e0e\u6027\u80fd\u62a5\u544a'),
    ('docs/ARCHITECTURE.md', '\u7ed3\u6784\u3001\u6a21\u5757\u4e0e\u7c7b'), ('docs/WORKFLOWS.md', '\u5de5\u4f5c\u6d41\u7a0b'),
    ('docs/API.md', '\u7ec6\u9897\u7c92\u5ea6\u63a5\u53e3\u89c4\u8303'), ('docs/INPUT_INTERFACES.md', '\u8f93\u5165\u4e0e OCR IPC'),
    ('docs/UI_INTERFACES.md', 'UI \u72b6\u6001\u548c\u4e8b\u4ef6'), ('docs/LOCAL_TRANSLATION.md', '\u53c2\u6570\u4e0e\u538b\u7f29\u8bed\u5883'),
    ('docs/CONTEXT_AGENT.md', '\u8054\u7f51\u7406\u89e3\u4e0e\u663e\u793a\u5206\u5c42'),
    ('docs/DICTIONARIES.md', '\u5386\u53f2\u8bcd\u5178\u5bfc\u5165'), ('docs/OFFLINE_ENGINES.md', '\u7eaf AI \u8def\u7ebf\u8bf4\u660e'),
    ('docs/SECURITY.md', '\u5b89\u5168\u8fb9\u754c'), ('docs/DEPENDENCIES.md', '\u4f9d\u8d56\u4e0e\u6784\u5efa'),
    ('docs/RELEASE.md', '\u53d1\u5e03\u4e0e\u9a8c\u8bc1'), ('CHANGELOG.md', '\u7248\u672c\u53d8\u5316'),
    ('docs/USER_AGREEMENT.md', '\u514d\u8d23\u58f0\u660e\u4e0e MIT'), ('THIRD_PARTY_NOTICES.md', '\u7b2c\u4e09\u65b9\u8bb8\u53ef'),
]


def page_id(path):
    return 'p-' + Path(path).stem.lower().replace('_', '-')


def slug(text):
    return re.sub(r'[^\w\-\u4e00-\u9fff]', '', text.lower().replace(' ', '-'))


def build():
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    targets = {path: page_id(path) for path, _ in PAGES}
    articles = []
    for path, title in PAGES:
        tokens = md.parse((ROOT/path).read_text(encoding='utf-8-sig'))
        used = {}
        for i, token in enumerate(tokens):
            if token.type == 'heading_open':
                heading = slug(tokens[i+1].content)
                count = used.get(heading, 0); used[heading] = count+1
                token.attrSet('id', targets[path]+'-'+heading+(f'-{count}' if count else ''))
            for child in token.children or []:
                if child.type != 'link_open': continue
                href = child.attrGet('href') or ''
                if re.match(r'^[a-zA-Z][\w+.-]*:', href) or href.startswith('//'): continue
                part, _, fragment = href.partition('#')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(part))) if part else path
                if target in targets:
                    child.attrSet('href', '#'+targets[target]+('-'+unquote(fragment) if fragment else ''))
                elif target == 'docs/PROJECT_MANUAL.html':
                    child.attrSet('href', '#top')
                else:
                    child.attrSet('href', posixpath.relpath(target, 'docs')+('#'+fragment if fragment else ''))
        articles.append(f'<article id="{targets[path]}"><div class="chapter">{html.escape(title)}</div>'+md.renderer.render(tokens, md.options, {})+'</article>')
    guide = (ROOT/'docs/PROJECT_GUIDE.html').read_text(encoding='utf-8')
    diagrams = []
    for section in ('architecture', 'workflow', 'trust'):
        match = re.search(r'<section id="'+section+r'">([\s\S]*?)</section>', guide)
        if not match: raise RuntimeError('Missing reviewed SVG section: '+section)
        diagrams.append(match.group(0).replace('href="SECURITY.md"', 'href="#p-security"'))
    # The reviewed SVG uses CSS classes; copying nodes alone produces black
    # rectangles. Keep the original, self-contained SVG styling with the nodes.
    svg_css = ''.join(re.findall(r'svg (?:text|\.[\w-]+)\{[^}]*\}', guide))
    if not all('svg .'+name+'{' in svg_css for name in ('node', 'accent', 'title', 'desc', 'line')):
        raise RuntimeError('Missing reviewed SVG styles')
    navigation = '<a href="#visual">\u53ef\u89c6\u5316\u603b\u89c8</a>'+''.join(f'<a href="#{targets[p]}">{html.escape(t)}</a>' for p,t in PAGES)
    css = '''*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:#faf7f4;color:#302b2b;font:16px/1.8 "Microsoft YaHei UI",sans-serif}aside{position:fixed;width:230px;height:100vh;overflow:auto;padding:24px 16px;background:#fff;border-right:1px solid #e4d9d5}aside b{color:#b33431;font-size:22px}aside a{display:block;padding:5px 8px;border-radius:5px;font-size:14px}a{color:#a32c29;text-decoration:none}a:hover{background:#fae9e4;text-decoration:underline}main{margin-left:230px;max-width:1230px;padding:32px 44px}header,article,#visual{background:#fff;padding:28px 32px;margin-bottom:24px;border:1px solid #e7ddda;border-radius:12px}header{border-top:6px solid #b33431}h1{font-size:30px;line-height:1.4}h2{font-size:24px;margin-top:36px;border-bottom:1px solid #eddfd9;padding-bottom:8px}h3{font-size:19px;margin-top:28px}p,li{overflow-wrap:anywhere}.chapter{font-size:13px;color:#a1433d;letter-spacing:2px}pre{padding:16px;background:#f4f1ee;border:1px solid #e6ded8;overflow:auto;font-size:13px;line-height:1.6}code{font-family:Consolas,monospace}table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow:auto;margin:16px 0}td,th{border:1px solid #dfd5d0;padding:9px 12px;text-align:left;vertical-align:top}th{background:#f6e9e5;white-space:nowrap}blockquote,.note{border-left:4px solid #ba4b42;padding:10px 18px;background:#fcf1ed}.diagram svg{width:100%;height:auto}.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}.card{padding:14px;background:#faf7f4}img{max-width:100%}.sub{color:#6f6260}article{scroll-margin-top:18px}@media(max-width:850px){aside{position:static;width:auto;height:auto}aside a{display:inline-block}main{margin:0;padding:16px}header,article,#visual{padding:18px}h1{font-size:25px}}@media print{aside{display:none}main{margin:0;padding:0;max-width:none}article{break-before:page;border:none}pre{white-space:pre-wrap}a{color:#302b2b}header,#visual{border:none}}'''
    content = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:"><title>\u4e8c\u8272\u8776 0.01.27 · \u5b8c\u6574\u9879\u76ee\u624b\u518c</title><style>'+css+svg_css+'</style></head><body><aside><b>\u4e8c\u8272\u8776</b><p>\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1 · 0.01.27<br>\u5b8c\u6574\u79bb\u7ebf\u9879\u76ee\u624b\u518c</p>'+navigation+'</aside><main id="top"><header><div class="chapter">WINDOWS X64 · MIT</div><h1>\u4e8c\u8272\u8776 · \u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1</h1><p>\u4ece\u7a97\u53e3\u753b\u9762\uff0c\u5230\u539f\u4f4d\u8bd1\u6587\u3002</p><p><a href="PROJECT_MANUAL.en.html">English complete manual</a></p><p>\u672c\u624b\u518c\u5408\u5e76\u7528\u6237\u64cd\u4f5c\u3001\u7ed3\u6784\u56fe\u3001\u6d41\u7a0b\u56fe\u3001\u7c7b\u4e0e\u6a21\u5757\u3001\u63a5\u53e3\u5951\u7ea6\u3001\u4f9d\u8d56\u3001\u5b89\u5168\u8fb9\u754c\u53ca\u8bb8\u53ef\u6b63\u6587\u3002\u9759\u6001 HTML / \u5185\u8054 SVG\uff0c\u65e0\u811a\u672c\u3001\u65e0\u8fdc\u7a0b\u8d44\u6e90\u3002</p><p class="sub">\u7a0b\u5e8f\u540d\u79f0\uff1aNKC_Galgame_Translator\u3000\u7248\u672c\uff1a0.01.27<br>\u4f7f\u7528\u6d4f\u89c8\u5668 Ctrl+F \u68c0\u7d22\uff0cCtrl+P \u6253\u5370\u3002\u4e0b\u65b9\u6d41\u7a0b\u56fe\u4e3a\u53ef\u76f4\u63a5\u9605\u8bfb\u7684 SVG\uff1b\u5404\u7ae0\u8282\u4fdd\u7559 Mermaid \u539f\u59cb\u63cf\u8ff0\u4ee5\u4fbf\u5f00\u53d1\u8005\u7f16\u8f91\u3002</p></header><div id="visual">'+''.join(diagrams)+'</div>'+''.join(articles)+'</main></body></html>'
    dest=ROOT/'docs/PROJECT_MANUAL.html';dest.write_text(content,encoding='utf-8')
    print(f'Generated {dest.name}: {len(PAGES)} chapters, {dest.stat().st_size} bytes')


if __name__ == '__main__': build()
