# SPDX-License-Identifier: MIT
"""Create only local engineering entry points; no customer documents or reports."""
from pathlib import Path
import argparse
import html
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-root',action='store_true')
    args=parser.parse_args()
    version=ROOT.name
    if not re.fullmatch(r'\d+\.\d{2}\.\d{2}',version):raise ValueError('Invalid version directory')
    required=('dist/NKC_Galgame_Translator/NKC_Galgame_Translator.exe',
              'demo/NeedyGirlOverdose/NKC_Galgame_Translator.exe',
              'demo/NeedyGirlOverdose/config/credentials.bin',
              f'dist/NKC_Galgame_Translator-{version}-source.zip')
    if not all((ROOT/name).is_file() for name in required):raise RuntimeError('Engineering artifacts are incomplete')
    body=f'''<h1>\u4e8c\u8272\u8776 {html.escape(version)} · \u5de5\u7a0b\u6587\u4ef6</h1>
<ul><li><a href="demo/NeedyGirlOverdose/">\u4e2a\u4eba\u8fd0\u884c\u76ee\u5f55</a>\uff1aNKC_Galgame_Translator.exe</li>
<li><a href="dist/NKC_Galgame_Translator/">\u516c\u5f00\u7a0b\u5e8f\u76ee\u5f55</a></li>
<li><a href="dist/">\u7a0b\u5e8f\u3001\u6e90\u7801\u4e0e\u53ef\u9009 CUDA \u6269\u5c55\u5f52\u6863</a></li>
<li><a href="./">\u5f00\u53d1\u6e90\u7801\u76ee\u5f55</a></li></ul>
<p>\u5f00\u53d1\u76ee\u5f55\u548c\u4e2a\u4eba\u8fd0\u884c\u76ee\u5f55\u5305\u542b\u79c1\u6709 API \u914d\u7f6e\u53ca\u5386\u53f2\uff0c\u4e0d\u7528\u4e8e\u516c\u5f00\u5206\u53d1\u3002</p>
<p><a href="docs/PROJECT_MANUAL.html">\u5386\u53f2\u624b\u518c</a>\u4fdd\u7559 0.01.27 \u5185\u5bb9\uff0c\u672c\u8f6e\u672a\u66f4\u65b0\u6587\u6863\u6216\u5236\u4f5c\u6f14\u793a\u3002</p>'''
    def page(content):return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>\u4e8c\u8272\u8776 · \u5de5\u7a0b\u5165\u53e3</title><body>'+content+'</body></html>'
    (ROOT/'OPEN_FIRST.html').write_text(page(body),encoding='utf-8')
    (ROOT/'DIRECTORIES.txt').write_text(
        f'Nishokuchou {version} - engineering files\n\n'
        'demo/NeedyGirlOverdose/ : configured private executable with CUDA runtime\n'
        'dist/NKC_Galgame_Translator/ : public executable, no private configuration\n'
        'dist/ : public runtime ZIP, source ZIP, optional CUDA add-on and SHA256 sums\n'
        './ : development source; config and data are private\n'
        'docs/ : historical 0.01.27 documents; not refreshed for this engineering update\n',encoding='utf-8')
    if args.publish_root:
        (ROOT.parent/'OPEN_FIRST.html').write_text(page(f'<h1>\u4e8c\u8272\u8776 {version} · \u5de5\u7a0b\u6587\u4ef6</h1><p><a href="{version}/OPEN_FIRST.html">\u6253\u5f00\u5f53\u524d\u5de5\u7a0b\u5165\u53e3</a></p>'),encoding='utf-8')
    print(f'Engineering entry points ready: {version}')


if __name__=='__main__':main()
