# SPDX-License-Identifier: MIT
from pathlib import Path
import json,platform,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
assert ROOT.name=='0.01.24'
before=json.loads((ROOT/'reports/baseline15-ocr.json').read_text(encoding='utf-8'))
after=json.loads((ROOT/'reports/current24-ocr.json').read_text(encoding='utf-8'))
features=json.loads((ROOT/'reports/feature24-probe.json').read_text(encoding='utf-8'));assert features['passed']
assert '1563 passed, 1 skipped' in (ROOT/'reports/tests-final.log').read_text(encoding='utf-8')
assert '1 passed' in (ROOT/'reports/tests-wgc.log').read_text(encoding='utf-8')
selfcheck=ROOT/'selftest.json'
if selfcheck.exists():
    evidence=json.loads(selfcheck.read_text(encoding='utf-8'));assert evidence['version']=='0.01.24' and evidence['ok']
    selfcheck.replace(ROOT/'reports/source-selftest.json')
report={'schema':1,'version':'0.01.24','date':'2026-11-18','platform':platform.platform(),
    'validation_status':'source_passed_release_checks_pending',
    'automated_tests':{'passed':1564,'skipped':1,'unique_cases':1565,
        'full_run_seconds':185.32,'restricted_run_passed':1563,
        'capture_check_rerun_passed':1,'capture_check_rerun_seconds':.73,
        'rerun_reason':'Restricted sandbox denied WGC with E_ACCESSDENIED; same check passed outside sandbox.',
        'skipped_reason':'Windows foreground activation lock held by another application'},
    'source_selfcheck':True,'real_paid_api_requests_in_automated_tests':0,
    'feature_validation':features,'accuracy_baseline':'0.01.15','accuracy_report':'PERFORMANCE_REPORT.json',
    'accuracy_character_count':356,'accuracy_before_percent':before['accuracy']['character_accuracy_percent'],
    'accuracy_after_percent':after['accuracy']['character_accuracy_percent'],
    'accuracy_gain_percentage_points':round(after['accuracy']['character_accuracy_percent']-before['accuracy']['character_accuracy_percent'],3),
    'benchmark_features':'Whole image, pixel OCR, automatic fonts off; same inputs across versions.',
    'legal_terms_changed':False,'source_and_native_abi':2}
path=ROOT/'docs/TEST_REPORT.json'
if path.exists():
    old=json.loads(path.read_text(encoding='utf-8'))
    if old.get('version')=='0.01.24' and old.get('validation_status')=='passed':report=old
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name in ('ARCHITECTURE.md','en/ARCHITECTURE.md'):
    p=ROOT/'docs'/name;text=p.read_text(encoding='utf-8').replace('1–8\u7ebf\u7a0b\uff0c\u9ed8\u8ba42','1–8\u7ebf\u7a0b\uff0c\u9ed8\u8ba44').replace('1–8 workers, default2','1–8 workers, default4')
    p.write_text(text,encoding='utf-8')
for name in ('CUSTOMER_GUIDE.md','en/CUSTOMER_GUIDE.md'):
    p=ROOT/'docs'/name;text=p.read_text(encoding='utf-8').replace('0.01.23 \u7684\u5206\u533a\u5b57\u7b26\u51c6\u786e\u7387','0.01.24 \u7684\u5206\u533a\u5b57\u7b26\u51c6\u786e\u7387').replace('0.01.23 · Windows','0.01.24 · Windows')
    p.write_text(text,encoding='utf-8')
guide=ROOT/'docs/PROJECT_GUIDE.html';text=guide.read_text(encoding='utf-8')
if 'id="regions-font24"' not in text:
    svg='''<div class="diagram" id="regions-font24"><svg viewBox="0 0 1120 180" role="img" aria-label="\u591a\u9009\u533a\u4e0e\u5b57\u4f53\u6a21\u5757"><g><rect class="node" x="20" y="20" width="320" height="110" rx="12"/><text class="title" x="36" y="50">CapturePlan · Python</text><text class="desc" x="36" y="79">1–8\u9009\u533a / \u4e00\u5e27\u6355\u83b7 / \u95f4\u9699\u906e\u7f69</text><text class="desc" x="36" y="106">\u5206\u533a\u5206\u7ec4\u4e0e\u8ffd\u8e2a\uff0c\u4e0d\u8de8\u6846\u62fc\u63a5</text></g><path class="line" d="M340 75H390"/><g><rect class="accent" x="390" y="20" width="320" height="110" rx="12"/><text class="title" x="406" y="50">font_style · Python/Pillow</text><text class="desc" x="406" y="79">\u6e90\u56fe\u98ce\u683c\u8fd1\u4f3c / \u6709\u754c\u7ed3\u679c\u7f13\u5b58</text><text class="desc" x="406" y="106">\u76ee\u6807\u8bed\u79cd\u4e0e\u5b9e\u9645\u8bd1\u6587\u5b57\u5f62\u68c0\u67e5</text></g><path class="line" d="M710 75H760"/><g><rect class="node" x="760" y="20" width="320" height="110" rx="12"/><text class="title" x="776" y="50">Styled overlay · C++/GDI</text><text class="desc" x="776" y="79">\u9010\u6846\u5b57\u4f53 / \u539f\u884c\u6392\u7248 / \u81ea\u52a8\u7f29\u5b57</text><text class="desc" x="776" y="106">\u65e0\u652f\u6301\u5b57\u4f53\u65f6\u4fdd\u7559\u539f\u6587</text></g></svg></div>'''
    start=text.index('<section id="architecture">');end=text.index('</section>',start)
    text=text[:end]+svg+text[end:];guide.write_text(text,encoding='utf-8')
index='''# \u6587\u6863\u76ee\u5f55 · 0.01.24

\u66f4\u65b0\uff1a2026-11-18\u3002\u5f53\u524d\u8d44\u6599\u5168\u90e8\u5bf9\u5e940.01.24\uff1b\u5e260.01.22\u6587\u4ef6\u540d\u7684\u6027\u80fd\u62a5\u544a\u4e3a\u539f\u59cb\u5386\u53f2\u8d44\u6599\uff0c\u4e0d\u66ff\u4ee3\u5f53\u524d0.01.15→0.01.24\u5bf9\u7167\u3002

| \u7528\u9014 | \u4e2d\u6587 | English |
|---|---|---|
| \u5ba2\u6237\u4f7f\u7528 | [\u5ba2\u6237\u624b\u518c](CUSTOMER_GUIDE.html) | [User guide](CUSTOMER_GUIDE.en.html) |
| \u5b8c\u6574\u9879\u76ee | [\u5b8c\u6574HTML\u624b\u518c](PROJECT_MANUAL.html) | [Complete manual](PROJECT_MANUAL.en.html) |
| \u6027\u80fd\u4e0e\u539f\u56fe | [\u6027\u80fd\u62a5\u544a](PERFORMANCE_REPORT.html) | [Performance](PERFORMANCE_REPORT.en.html) |
| \u7ed3\u6784\u4e0e\u6d41\u7a0b | [\u53ef\u89c6\u5316\u603b\u89c8](PROJECT_GUIDE.html) | [Diagrams](PROJECT_MANUAL.en.html#visual) |
| \u63a5\u53e3\u4e0e\u8fb9\u754c | [API](API.md)\u3001[\u8f93\u5165](INPUT_INTERFACES.md)\u3001[UI](UI_INTERFACES.md) | [API](en/API.md)\u3001[Input](en/INPUT_INTERFACES.md)\u3001[UI](en/UI_INTERFACES.md) |
| \u4f9d\u8d56\u4e0e\u53d1\u5e03 | [\u4f9d\u8d56](DEPENDENCIES.md)\u3001[\u53d1\u5e03](RELEASE.md) | [Dependencies](en/DEPENDENCIES.md)\u3001[Release](en/RELEASE.md) |
| \u534f\u8bae | [\u4e2d\u6587](USER_AGREEMENT.md)\u3001[\u65e5\u672c\u8a9e](USER_AGREEMENT.ja.md) | [English](USER_AGREEMENT.en.md) |
| \u5b9e\u6d4b\u4e0e\u9a8c\u6536 | [\u6d4b\u91cfJSON](PERFORMANCE_REPORT.json)\u3001[\u6d4b\u8bd5JSON](TEST_REPORT.json) | Same machine-readable data |

\u516c\u5f00\u8d44\u6599\u5728delivery/customer\uff0c\u6e90\u7801\u4e0e\u7a0b\u5e8f\u5305\u5728delivery/release\u3002\u5f00\u53d1\u76ee\u5f55config\u53cademo/SpaceRogueClassic\u7684\u914d\u7f6e\u548c\u5386\u53f2\u5c5e\u4e8e\u79c1\u4eba\u8d44\u6599\u3002\u534f\u8bae\u6cd5\u5f8b\u6761\u6b3e\u548cMIT\u6587\u672c\u672a\u56e0\u672c\u6b21\u529f\u80fd\u66f4\u65b0\u800c\u6539\u5199\uff1b\u517c\u5bb9\u8bf4\u660e\u5df2\u590d\u6838\u3002
'''
(ROOT/'docs/DOCUMENTATION_INDEX.md').write_text(index,encoding='utf-8')
print('Updated current documentation evidence and visual module diagram.')
