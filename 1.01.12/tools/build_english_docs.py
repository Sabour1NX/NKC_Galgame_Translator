# SPDX-License-Identifier: MIT
"""Build the complete English manual without scripts or remote resources."""
from __future__ import annotations

import html
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ('README.md', 'Getting started'), ('USER_GUIDE.md', 'User guide'), ('PERFORMANCE_REPORT.md', 'Response performance report'),
    ('ARCHITECTURE.md', 'Modules, classes and threads'), ('WORKFLOWS.md', 'Workflows'),
    ('API.md', 'Granular API reference'), ('INPUT_INTERFACES.md', 'Input and OCR IPC'),
    ('UI_INTERFACES.md', 'UI methods and state'), ('LOCAL_TRANSLATION.md', 'Settings and compressed context'),
    ('CONTEXT_AGENT.md', 'Online context and display layers'),
    ('DICTIONARIES.md', 'Historical dictionary import'), ('OFFLINE_ENGINES.md', 'AI-only route'),
    ('SECURITY.md', 'Security boundaries'), ('DEPENDENCIES.md', 'Dependencies and builds'),
    ('RELEASE.md', 'Release and verification'), ('CHANGELOG.md', 'Change history'),
    ('USER_AGREEMENT.md', 'Disclaimer and complete MIT'),
    ('THIRD_PARTY_NOTICES.md', 'Third-party notices'),
]


def page_id(path: str) -> str:
    return 'p-' + Path(path).stem.lower().replace('_', '-')


def slug(value: str) -> str:
    return re.sub(r'[^\w\-\u4e00-\u9fff]', '', value.lower().replace(' ', '-'))


def box(x: int, y: int, title: str, first: str, second: str, kind: str = 'node') -> str:
    values = [html.escape(v) for v in (title, first, second)]
    return (f'<g><rect class="{kind}" x="{x}" y="{y}" width="320" height="100" rx="12"/>'
            f'<text class="title" x="{x+16}" y="{y+29}">{values[0]}</text>'
            f'<text class="desc" x="{x+16}" y="{y+54}">{values[1]}</text>'
            f'<text class="desc" x="{x+16}" y="{y+77}">{values[2]}</text></g>')


def arrow(points: str, marker: str) -> str:
    return f'<polyline class="line" points="{points}" marker-end="url(#{marker})"/>'


def svg(name: str, title: str, description: str, body: str, height: int) -> str:
    return (f'<svg viewBox="0 0 1120 {height}" role="img" aria-labelledby="{name}-title {name}-desc">'
            f'<title id="{name}-title">{html.escape(title)}</title>'
            f'<desc id="{name}-desc">{html.escape(description)}</desc><defs>'
            f'<marker id="{name}-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0 0L10 5L0 10Z" fill="#b33431"/></marker></defs>'+body+'</svg>')


def diagrams() -> str:
    a = 'modules-arrow'
    body = ''.join([
        arrow('550,120 550,170', a), arrow('340,220 390,220', a),
        arrow('710,220 760,220', a), arrow('550,270 550,320', a),
        arrow('180,270 180,320', a), arrow('340,370 390,370', a),
        arrow('920,270 920,320', a), arrow('920,270 920,295 730,295 730,370 710,370', a),
        arrow('550,420 550,470', a),
        arrow('180,170 180,70 390,70', a),
        arrow('20,220 5,220 5,520 20,520', a),
        arrow('340,520 370,520 370,220 390,220', a),
        box(390, 20, 'App · Python / Tk', 'Select1–8 rectangles; Enter to confirm', 'Main thread owns every widget', 'accent'),
        box(20, 170, 'OcrCore / CapturePlan · Python', 'CUDA helper or Windows / Tesseract', 'JSON IPC; local source geometry'),
        box(390, 170, 'Pipeline · Python', 'Quality gates; columns / prose groups', 'Object IDs, revisions and stale checks', 'accent'),
        box(760, 170, 'TranslationEngine · Python', 'AI-only streaming requests', 'Parallel I/O with bounded concurrency'),
        box(20, 320, 'ObjectTracker · Python', 'Match multiple visible text objects', 'Worker pool; keep scene identity'),
        box(390, 320, 'OverlayState / font_style', 'Per-box style; target glyph checks', 'Each cell stays in its source bounds'),
        box(760, 320, 'ContextArchive / ContextAgent', 'Scoped history; completed web notes', 'Refresh after display; no waiting queue', 'local'),
        box(20, 470, 'VisionCore · optional', 'Selected game crop; default off', 'Anchored text; shared API allowance'),
        box(760, 470, 'translatability · Python', 'HUD / keys / repeated-glyph noise', 'Raw identity check; no network'),
        box(390, 470, 'NativeCore · C++ / Win32', 'Fixed rows; shared paragraph font', 'Full-width final spacing; click-through', 'accent'),
    ])
    architecture = svg('modules', 'Modules, languages and responsibilities',
                       'Python coordinates UI, OCR, object tracking and translation. C++ captures and renders. SQLite stores scoped translations.', body, 590)
    a = 'workflow-arrow'
    body = ''.join([
        arrow('340,70 390,70', a), arrow('710,70 760,70', a),
        arrow('920,120 920,180', a), arrow('760,230 710,230', a),
        arrow('390,230 340,230', a), arrow('180,280 180,360', a),
        arrow('340,410 390,410', a), arrow('710,410 760,410', a),
        box(20, 20, 'Select target and languages', 'Confirm language, agreement and API', 'Bind the chosen game HWND / PID'),
        box(390, 20, 'Capture and OCR', 'One frame;1–8 isolated regions', 'Masked gaps; optional AI reading'),
        box(760, 20, 'Quality, track and settle', 'Suspect or low-value rows stay original', 'Accepted text tracks IDs / revisions'),
        box(760, 180, 'API availability and allowance', 'Missing API: browse records only', 'New valid tasks always use AI', 'accent'),
        box(390, 180, 'Context layer', 'History + completed web reference', 'Refresh later; no overlay notes', 'local'),
        box(20, 180, 'Translation-only LLM', 'Bounded SSE; current source only', 'Complete result and context archived'),
        box(20, 360, 'Identity, source rows and labels', 'Keep source rows; adjust final spacing', 'Brackets are an independent choice'),
        box(390, 360, 'Display: stable stream font', 'Final output fits the whole group', 'Original rows; streamed mask growth', 'accent'),
        box(760, 360, 'Target-bound output', 'Final output masks source rectangle', 'Focus loss / stop hides overlays'),
        '<text class="note-text" x="20" y="510">Rejected OCR: remove old overlays; skip translation and learning; late chunks cannot repaint.</text>',
        '<text class="note-text" x="20" y="537">History: lossless local zlib records; prompt excerpts are bounded, not semantic AI summaries.</text>',
        '<text class="note-text" x="20" y="564">Image reading shares request counting; unlimited mode skips only the count cap.</text>',
    ])
    workflow = svg('workflow', 'From game pixels to translated text',
                   'Capture and validate source text, read available bounded context, request translation, preserve stream font and fit final output. Stale output is rejected.', body, 590)
    a = 'trust-arrow'
    body = ''.join([
        arrow('340,70 390,70', a), arrow('340,230 365,230 365,100 390,100', a),
        arrow('710,70 760,70', a), arrow('920,120 920,180', a),
        arrow('760,230 710,230', a), arrow('550,120 550,180', a),
        arrow('550,280 550,340', a), arrow('390,390 340,390', a),
        box(20, 20, 'Untrusted game pixels', 'OCR text is data, never a command', 'One selected visible game window'),
        box(20, 180, 'Imported dictionary files', 'Size, structure and field limits', 'No XML entities or code execution'),
        box(390, 20, 'Validate and isolate', 'Bounded queues and typed values', 'Fixed rules; JSON + optional image', 'accent'),
        box(760, 20, 'Configured HTTPS provider', 'Text / optional crop / server search', 'No redirects or inherited proxy'),
        box(760, 180, 'Untrusted API response', 'Bounded JSON or streaming SSE', 'No local tools or output executor'),
        box(390, 180, 'Application state', 'Current object/revision checks', 'DPAPI key bound to full endpoint', 'accent'),
        box(390, 340, 'Display and context archive', 'Accepted events stored with zlib', 'Renderer receives bounded regions'),
        box(20, 340, 'Release and diagnostics', 'No keys, private DB or game assets', 'Sanitized errors; no user telemetry', 'local'),
        '<text class="note-text" x="20" y="495">Limits reduce exposure; they do not guarantee model accuracy, provider trust or security against a compromised account.</text>',
    ])
    trust = svg('trust', 'Input, credential and rendering boundaries',
                'Validate untrusted game, dictionary and API data. Encrypt local credentials and bind them to the configured provider. Output is never executed.', body, 520)
    layers=[]
    for number,(title,one,two) in enumerate([
        ('1 · Perception','CUDA auto / CPU fallback / refinement','Local coordinates and row evidence'),
        ('2 · Context','History + completed web references','Post-display background refresh'),
        ('3 · Translation','Current source → pure text stream','Budget, cancellation and validation'),
        ('4 · Display','Original rows; shared paragraph size','Full-width spacing after completion')]):
        x=15+number*280
        layers.append(f'<rect class="accent" x="{x}" y="20" width="250" height="112" rx="12"/><text class="title" x="{x+13}" y="49">{html.escape(title)}</text><text class="desc" x="{x+13}" y="78">{html.escape(one)}</text><text class="desc" x="{x+13}" y="103">{html.escape(two)}</text>')
        if number<3:layers.append(arrow(f'{x+250},76 {x+279},76','layers-arrow'))
    layer_diagram=svg('layers','Four distinct harness layers','The program owns geometry and tools; only translated text crosses into display.',''.join(layers),155)
    return ''.join(f'<section><h2>{title}</h2><div class="diagram">{diagram}</div></section>' for title, diagram in [
        ('Four layers: a game-translation harness', layer_diagram),
        ('Project structure: Python coordination and C++ rendering', architecture),
        ('Workflow: concurrent objects and progressive overlays', workflow),
        ('Trust boundaries: data stays data', trust),
    ])


CSS = '''*{box-sizing:border-box}body{margin:0;background:#faf7f4;color:#302b2b;font:16px/1.75 "Segoe UI",Arial,sans-serif}aside{position:fixed;width:246px;height:100vh;overflow:auto;padding:24px 17px;background:#fff;border-right:1px solid #e4d9d5}aside b{color:#b33431;font-size:21px}aside a{display:block;padding:5px 7px;font-size:14px}a{color:#a32c29;text-decoration:none}a:hover{text-decoration:underline}main{margin-left:246px;max-width:1280px;padding:32px 36px}header,article,#visual{background:#fff;padding:26px 30px;margin-bottom:24px;border:1px solid #e7ddda;border-radius:12px}header{border-top:6px solid #b33431}h1{font-size:30px;line-height:1.35}h2{font-size:23px;margin-top:32px;padding-bottom:8px;border-bottom:1px solid #eddfd9}h3{font-size:19px}p,li{overflow-wrap:anywhere}.chapter{font-size:13px;color:#a1433d;letter-spacing:1px}pre{padding:16px;background:#f4f1ee;overflow:auto;font-size:13px;line-height:1.6}code{font-family:Consolas,monospace}table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow:auto;margin:16px 0}td,th{border:1px solid #dfd5d0;padding:9px 12px;text-align:left;vertical-align:top}th{background:#f6e9e5}blockquote{border-left:4px solid #ba4b42;padding:10px 18px;background:#fcf1ed}.diagram{overflow:auto}.diagram svg{display:block;min-width:800px;width:100%;height:auto}svg text{font-family:"Segoe UI",Arial,sans-serif}svg .node{fill:#fffefd;stroke:#dfcec3;stroke-width:1.5}svg .accent{fill:#f8e8e4;stroke:#b33431;stroke-width:1.5}svg .local{fill:#e9f0e9;stroke:#8a9b86;stroke-width:1.5}svg .title{font-size:17px;font-weight:700;fill:#292a2c}svg .desc{font-size:14px;fill:#68645f}svg .line{fill:none;stroke:#b33431;stroke-width:2}svg .note-text{font-size:14px;fill:#68645f}article{scroll-margin-top:18px}@media(max-width:850px){aside{position:static;width:auto;height:auto}aside a{display:inline-block}main{margin:0;padding:16px}header,article,#visual{padding:18px}h1{font-size:25px}}@media print{aside{display:none}main{margin:0;padding:0;max-width:none}article{break-before:page;border:none}pre{white-space:pre-wrap}a{color:#302b2b}header,#visual{border:none}.diagram svg{min-width:0}}'''


def build() -> Path:
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    targets = {f'docs/en/{path}': page_id(path) for path, _ in PAGES}
    articles = []
    for filename, title in PAGES:
        path = f'docs/en/{filename}'
        tokens = md.parse((ROOT / path).read_text(encoding='utf-8-sig'))
        used = {}
        for i, token in enumerate(tokens):
            if token.type == 'heading_open':
                heading = slug(tokens[i+1].content)
                count = used.get(heading, 0)
                used[heading] = count + 1
                token.attrSet('id', targets[path]+'-'+heading+(f'-{count}' if count else ''))
            for child in token.children or []:
                if child.type != 'link_open':
                    continue
                href = child.attrGet('href') or ''
                if re.match(r'^[a-zA-Z][\w+.-]*:', href) or href.startswith('//'):
                    continue
                part, _, fragment = href.partition('#')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(part))) if part else path
                if target in targets:
                    child.attrSet('href', '#'+targets[target]+('-'+unquote(fragment) if fragment else ''))
                elif target in ('docs/PROJECT_MANUAL.en.html', 'docs/en/PROJECT_MANUAL.en.html'):
                    child.attrSet('href', '#top')
                else:
                    child.attrSet('href', posixpath.relpath(target, 'docs')+('#'+fragment if fragment else ''))
        articles.append(f'<article id="{targets[path]}"><div class="chapter">{html.escape(title)}</div>'+md.renderer.render(tokens, md.options, {})+'</article>')
    navigation = '<a href="#visual">Visual overview</a>'+''.join(f'<a href="#{page_id(path)}">{html.escape(title)}</a>' for path, title in PAGES)
    content = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">'
               '<title>Nishokuchou 0.01.27 · Complete project manual</title><style>'+CSS+'</style></head><body>'
               '<aside><b>Nishokuchou</b><p>Real-time game translation<br>0.01.27 · Complete offline manual</p>'+navigation+'</aside>'
               '<main id="top"><header><div class="chapter">WINDOWS X64 · MIT</div>'
               '<h1>Nishokuchou · Real-time game translation</h1><p>From game pixels to in-place translated text.</p>'
               '<p><a href="PROJECT_MANUAL.html">\u4e2d\u6587\u5b8c\u6574\u624b\u518c</a></p>'
               '<p>This complete English edition covers user workflows, diagrams, modules and classes, granular interfaces, dependencies, release checks and full license material. It is static HTML with inline SVG: no scripts or remote resources.</p>'
               '<p>Program: <code>NKC_Galgame_Translator</code> · Version 0.01.27. Use Ctrl+F to search or Ctrl+P to print. The diagrams below are readable without a Mermaid renderer.</p>'
               '</header><div id="visual">'+diagrams()+'</div>'+''.join(articles)+'</main></body></html>')
    dest = ROOT/'docs/PROJECT_MANUAL.en.html'
    dest.write_text(content, encoding='utf-8')
    print(f'Generated {dest.name}: {len(PAGES)} chapters, {dest.stat().st_size} bytes')
    return dest


if __name__ == '__main__':
    build()
