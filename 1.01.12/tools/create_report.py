# SPDX-License-Identifier: MIT
"""Bundle verified public project documents; never sends mail or shuts down."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = ROOT.name
NAME = 'NKC_Galgame_Translator'
SECRET = re.compile(rb'sk-[A-Za-z0-9_-]{16,}')


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    assert re.fullmatch(r'\d+\.\d{2}\.\d{2}', VERSION)
    reports = ROOT / 'reports'
    tests = load_json(ROOT / 'docs/TEST_REPORT.json')
    assert tests.get('version') == VERSION
    assert tests.get('pytest', {}).get('passed', 0) > 0
    assert tests['pytest'].get('failed') == 0
    assert all(tests.get(name) is True for name in
               ('source_selfcheck', 'packaged_selfcheck', 'relocated_zip_selfcheck'))
    verification = load_json(reports / 'package-verification.json')
    assert verification.get('version') == VERSION
    assert all(verification.get(name) is True for name in
               ('passed', 'source_matches_workspace', 'private_payloads_absent'))
    supplemental = tests.get('supplemental_private_ocr')
    supplemental_note = ''
    if supplemental:
        supplemental_summary = (reports / 'pytest-private-ocr.txt').read_text(encoding='utf-8-sig').strip().splitlines()[-1]
        assert f"{supplemental.get('passed')} passed" in supplemental_summary
        assert tests['total_unique_passed'] == tests['pytest']['passed'] + supplemental['passed']
        supplemental_note = f'\u72ec\u7acb\u8865\u6d4b\uff1a{supplemental_summary}\u3002\u5168\u5957\u4e0e\u8865\u6d4b\u539f\u59cb\u65e5\u5fd7\u5206\u522b\u4fdd\u7559\u3002'
    summary = (reports / 'pytest-final.txt').read_text(encoding='utf-8-sig').strip().splitlines()[-1]
    assert f"{tests['pytest']['passed']} passed" in summary and 'failed' not in summary
    packaged_name = next((name for name in ('packaged-selftest-final.json', 'packaged-selftest.json')
                          if (reports / name).is_file()), None)
    assert packaged_name is not None
    packaged = load_json(reports / packaged_name)
    assert packaged.get('ok') and packaged.get('frozen') and packaged.get('version') == VERSION
    now = datetime.now(timezone(timedelta(hours=8)))
    schema_status = verification.get('checks', {}).get('sbom', {}).get('official_schema', 'not_available')
    body = f'''\u4e8c\u8272\u8776·\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1 {VERSION} · \u9879\u76ee\u6587\u6863\u4e0e\u4ea4\u4ed8\u62a5\u544a
\u65f6\u95f4\uff1a{now:%Y-%m-%d %H:%M:%S} Asia/Shanghai

\u672c\u6b21\u66f4\u65b0\uff1a\u65b0\u589e\u4fdd\u5b88\u7684\u82f1\u6587\u83dc\u5355 OCR \u8d28\u91cf\u68c0\u67e5\u3002\u591a\u4e2a\u660e\u663e\u8fd1\u5f62\u8bef\u8bfb\u8bc1\u636e\u547d\u4e2d\u65f6\uff0c\u4fdd\u7559\u539f\u6e38\u620f\u50cf\u7d20\uff0c\u6e05\u9664\u65e7\u8bd1\u6587\uff0c\u62d2\u7edd\u8fdf\u5230\u6d41\u5f0f\u8986\u76d6\uff1b\u4e0d\u628a\u9519\u8bef\u8bc6\u522b\u4e32\u91cd\u65b0\u753b\u56de\u5c4f\u5e55\u3002\u8be5\u6846\u4e0d\u8fdb\u5165\u7ffb\u8bd1\u5f15\u64ce\u3001\u9519\u8bef\u7f13\u5b58\u67e5\u8be2\u3001\u7ffb\u8bd1\u8bf7\u6c42\u6216\u8bcd\u5178\u5199\u5165\uff0c\u4e5f\u4e0d\u63a8\u8fdb\u5b66\u4e60\u8ba1\u6570\u3002\u5176\u4ed6\u53ef\u4fe1\u6846\u6b63\u5e38\u7ffb\u8bd1\uff0c\u540e\u7eed\u6b63\u5e38\u8bc6\u522b\u53ef\u6062\u590d\u3002
\u8fd9\u4e0d\u662f\u901a\u7528\u62fc\u5199\u68c0\u67e5\u6216\u8bed\u4e49\u5224\u9519\u5668\u3002\u4e13\u540d\u3001\u6e38\u620f\u672f\u8bed\u548c\u5355\u7eaf\u672a\u6536\u5f55\u5355\u8bcd\u4e0d\u662f\u62d2\u7edd\u7406\u7531\u3002\u53ef\u9009 AI \u56fe\u50cf\u8bc6\u522b\u4f4d\u4e8e\u95e8\u63a7\u4e4b\u524d\uff0c\u4ecd\u6309\u5176\u81ea\u8eab\u8bbe\u7f6e\u8fd0\u884c\u3002\u4fdd\u7559\u65e2\u6709\u65e0\u4e0a\u9650\u5f00\u5173\u3001512 \u6b21\u6210\u529f\u5b66\u4e60\u4e0e\u667a\u80fd\u5206\u6d41\uff1b\u8bf7\u6c42\u6b21\u6570\u5f00\u5173\u4e0d\u53d6\u6d88\u5e76\u53d1\u3001\u8d85\u65f6\u6216\u79bb\u7ebf\u7ea6\u675f\u3002

\u672c\u7248\u9a8c\u8bc1\uff1a{summary}
{supplemental_note}
\u6e90\u7801\u81ea\u68c0\u3001\u6253\u5305EXE\u81ea\u68c0\u3001\u6539\u540d\u76ee\u5f55\u89e3\u538b\u8fd0\u884c\u81ea\u68c0\u5747\u901a\u8fc7\u3002\u7a0b\u5e8f\u5305\u548c\u6e90\u7801\u5305\u5b8c\u6210CRC\u3001\u8def\u5f84\u3001SHA256\u3001\u5bf9\u5e94\u6e90\u7801\u3001\u79c1\u6709\u6570\u636e\u6392\u9664\u53ca\u6e05\u5355\u6838\u9a8c\u3002SBOM\u5b98\u65b9JSON Schema\u6821\u9a8c\u72b6\u6001\uff1a{schema_status}\u3002\u8fd9\u4e0d\u7b49\u4e8e\u53d1\u5e03\u8005\u7b7e\u540d\u3001\u5168\u90e8\u6f0f\u6d1e\u5ba1\u8ba1\u6216\u6240\u6709\u6e38\u620f\u517c\u5bb9\u6027\u4fdd\u8bc1\u3002
\u672c\u8f6e\u81ea\u52a8\u6d4b\u8bd5\u4ed8\u8d39API\u8bf7\u6c42\u6570\uff1a{tests.get('real_paid_api_requests_in_automated_tests', 0)}\u3002\u65e7\u7248OCR/\u6e38\u620f\u6837\u672c\u82e5\u5728\u62a5\u544a\u4e2d\u51fa\u73b0\uff0c\u4ec5\u5217\u4e3aprevious_version_evidence\uff0c\u4e0d\u4ee3\u8868\u672c\u8f6e\u91cd\u65b0\u6d4b\u8bd5\u3002

\u9644\u4ef6\u5185\u5bb9\uff1a\u5b8c\u6574\u4e2d\u6587\u4e0e\u82f1\u6587HTML\u9879\u76ee\u624b\u518c\u3001\u53ef\u89c6\u5316\u9879\u76ee\u7ed3\u6784\u4e0e\u5de5\u4f5c\u6d41\u7a0b\u3001\u7c7b\u4e0e\u6a21\u5757\u8bf4\u660e\u3001\u7ec6\u9897\u7c92\u5ea6\u63a5\u53e3\u89c4\u8303\u3001\u4f9d\u8d56\u6e05\u5355\u3001\u514d\u8d23\u58f0\u660e\u4e0eMIT\u3001\u7b2c\u4e09\u65b9\u8bb8\u53ef\uff0c\u4ee5\u53ca\u672c\u7248\u6d4b\u8bd5\u548c\u53d1\u884c\u6821\u9a8c\u62a5\u544a\u3002HTML\u4e3a\u79bb\u7ebf\u9759\u6001\u6587\u6863\uff0c\u65e0\u811a\u672c/CDN\u3002
\u8bf7\u89e3\u538b\u540e\u6253\u5f00docs/PROJECT_MANUAL.html\uff08\u4e2d\u6587\uff09\u6216docs/PROJECT_MANUAL.en.html\uff08English\uff09\u3002

\u672c\u673a\u7a0b\u5e8f\u5305\uff1a{ROOT / 'dist' / f'{NAME}-{VERSION}-windows-x64.zip'}
\u672c\u673a\u6e90\u7801\u5305\uff1a{ROOT / 'dist' / f'{NAME}-{VERSION}-source.zip'}
\u9879\u76ee\u6587\u6863\u5305\u4e0d\u542b\u5b8c\u6574\u7a0b\u5e8f\u3001\u79c1\u4ebaAPI Key\u3001DPAPI\u5bc6\u6587\u3001\u7ffb\u8bd1\u6570\u636e\u5e93\u6216\u6e38\u620f\u7d20\u6750\u3002\u65e7\u7248\u672c\u72ec\u7acb\u4fdd\u7559\u3002

\u6b64\u5de5\u5177\u53ea\u5728\u672c\u5730\u751f\u6210\u62a5\u544a\u548c\u6587\u6863\u5305\uff0c\u4e0d\u53d1\u9001\u90ae\u4ef6\uff0c\u4e0d\u521b\u5efa\u6216\u542f\u52a8\u5173\u673a\u4efb\u52a1\u3002\u672c\u8f6e OCR \u4fee\u590d\u6ca1\u6709\u91cd\u65b0\u5b89\u6392\u90ae\u4ef6\u53d1\u9001\u6216\u5173\u673a\u3002
'''
    report = reports / f'{NAME}-{VERSION}-report.txt'
    report.write_text(body, encoding='utf-8')
    files = [(report, 'report.txt')]
    for name in ('README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        files.append((ROOT / name, name))
    # Copy only the public docs tree. Keep relative links and examples usable.
    for path in sorted((ROOT / 'docs').rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.md', '.html', '.json', '.csv', '.tsv', '.tmx', '.txt'):
            files.append((path, path.relative_to(ROOT).as_posix()))
    for name in ('package-verification.json', packaged_name, 'source-selftest.json',
                 'relocated-selftest-final.json', 'relocated-selftest.json',
                 'manual-html-check.json', 'ui-language-snapshots.json', 'pytest-final.txt', 'pytest-private-ocr.txt'):
        path = reports / name
        if path.is_file():
            files.append((path, 'reports/' + name))
    seen, manifest = set(), []
    archive = reports / f'{NAME}-{VERSION}-project-documents.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path, relative in files:
            assert relative not in seen, relative
            seen.add(relative)
            assert path.is_file() and not path.is_symlink()
            assert path.resolve().is_relative_to(ROOT)
            raw = path.read_bytes()
            if SECRET.search(raw):
                raise RuntimeError('Possible credential in public document; report refused')
            assert not any(part in {'config', 'data', 'demo'} for part in Path(relative).parts)
            bundle.writestr(relative, raw)
            manifest.append({'file': relative, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        bundle.writestr('document-manifest.json', json.dumps({'version': VERSION, 'files': manifest},
                                                           ensure_ascii=False, indent=2))
    assert archive.stat().st_size < 3_000_000, 'Document attachment exceeds mail limit'
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    delivery = {'version': VERSION, 'report': str(report), 'attachment': str(archive),
                'bytes': archive.stat().st_size, 'files': len(manifest) + 1,
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'includes_private_config': False, 'includes_game_assets': False,
                'email_sent': False, 'shutdown_armed': False}
    (reports / 'document-delivery.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(delivery, ensure_ascii=False))


if __name__ == '__main__':
    main()
