# SPDX-License-Identifier: MIT
"""One-time report generator migration; measured inputs remain mandatory."""
from pathlib import Path
import re
r=Path(__file__).resolve().parents[1]
p=r/'tools/build_contrast_report.py';s=p.read_text(encoding='utf-8')
assert 'baseline22-ocr.json' in s
s=s.replace('baseline22-ocr.json','baseline15-ocr.json').replace('current23-ocr.json','current24-ocr.json')
s=s.replace('PERFORMANCE_REPORT_0.01.22','HISTORICAL_KEEP')
s=s.replace('0.01.22','0.01.15').replace('0.01.23','0.01.24')
s=s.replace('HISTORICAL_KEEP','PERFORMANCE_REPORT_0.01.22')
s=s.replace('89.61','83.99').replace('37 → 16','57 → 16').replace('37 to 16','57 to 16')
s=s.replace('\u53d8\u5316\u5e27\u8017\u65f6\u589e\u52a0','\u53d8\u5316\u5e27\u8017\u65f6\u53d8\u5316').replace('Changed-frame time increase','Changed-frame time change')
s=s.replace('0.01.24 · \u5c40\u90e8 RGB \u5bf9\u6bd4','0.01.24 · \u8c03\u4f18\u540e\u7684\u6846\u67b6')
s=s.replace('<div class="head"><b>0.01.15</b>','<div class="head"><b>0.01.15 · \u8c03\u4f18\u524d\u57fa\u7ebf</b>')
s=s.replace('\u6ca1\u6709\u5347\u7ea7\u6a21\u578b\u6216\u539f\u751f DLL\u3002','\u6a21\u578b\u6587\u4ef6\u76f8\u540c\uff0c\u4f7f\u7528\u5404\u81ea\u7248\u672c\u539f\u751f DLL\uff1b\u672c\u8f6e OCR \u56de\u653e\u5173\u95ed\u81ea\u52a8\u5b57\u4f53\uff0c\u8986\u76d6\u6574\u4e2a\u8f93\u5165\u56fe\u50cf\u3002')
s=s.replace('\u53d8\u5316\u5e27\u5305\u542b\u989c\u8272\u5206\u6790\u4e0e\u5c40\u90e8\u6821\u9a8c\uff0c\u5904\u7406\u65f6\u95f4\u9ad8\u4e8e\u672c\u7ec4\u5bf9\u7167\uff1b\u76f8\u540c\u753b\u9762\u53ef\u590d\u7528 OCR \u7f13\u5b58\u3002','\u53d8\u5316\u5e27\u5728\u4e0d\u540c\u573a\u666f\u6709\u5feb\u6709\u6162\uff1b\u76f8\u540c\u753b\u9762\u53ef\u590d\u7528 OCR \u7f13\u5b58\u3002')
s=s.replace('\u9ed8\u8ba4\u533a\u57df\u7ec6\u5316\u7ebf\u7a0b 4','\u65b0\u7248\u672c\u533a\u57df\u7ec6\u5316\u7ebf\u7a0b 4\uff1b\u65e7\u7248\u672c\u4f7f\u7528\u5176\u539f\u6709\u7ed3\u6784')
start=s.index('zh=f\'\'\'');end=s.index("(ROOT/'docs/en/PERFORMANCE_REPORT.md').write_text",start)
replacement='''zh=f\'''# \u4e8c\u8272\u8776 0.01.24 · \u6027\u80fd\u4e0e\u8bc6\u522b\u62a5\u544a

**\u54c1\u8d28\u7684\u4f53\u9a8c\uff0c\u66f4\u5c11\u7684\u7b49\u5f85**

2026-11-18 · \u5bf9\u7167\uff1a**\u4e8c\u8272\u8776 0.01.15\uff08\u8c03\u4f18\u524d\u57fa\u7ebf\uff09→ \u4e8c\u8272\u8776 0.01.24\uff08\u8c03\u4f18\u540e\u7684\u6846\u67b6\uff09**\u3002

\u672c\u62a5\u544a\u70b9\u540d\u6bd4\u8f83\u672c\u9879\u76ee\u7684\u4e24\u4e2a\u7248\u672c\u30020.01.15 \u662f\u4fdd\u7559\u7684\u6700\u65e7\u7248\u672c\uff0c\u4e0d\u662f\u7b2c\u4e09\u65b9\u6846\u67b6\u7684\u539f\u751f\u6027\u80fd\u3002\u672a\u6d4b\u8bd5\u5e02\u9762\u7ade\u54c1\u3002\u67e5\u770b[\u4ea4\u4e92\u5f0f\u62a5\u544a\u4e0e\u539f\u56fe](PERFORMANCE_REPORT.html)\u3002

## \u5b9e\u6d4b\u7ed3\u679c

\u76f8\u540c\u4e09\u5f20 Space Rogue Classic \u622a\u56fe\u3001356 \u4e2a\u6807\u6ce8\u5b57\u7b26\uff1a\u5206\u533a\u5b57\u7b26\u51c6\u786e\u7387 **{before['accuracy']['character_accuracy_percent']:.2f}% → {after['accuracy']['character_accuracy_percent']:.2f}%**\uff0c\u63d0\u9ad8 **{delta:.2f} \u4e2a\u767e\u5206\u70b9**\uff1b\u7f16\u8f91\u9519\u8bef **{before['accuracy']['edits']} → {after['accuracy']['edits']}**\uff0c\u51cf\u5c11 **{error_reduction:.1f}%**\u3002

| \u573a\u666f | \u5b57\u7b26\u51c6\u786e\u7387\uff1a0.01.15 → 0.01.24 | \u8fd4\u56de\u540c\u56fe OCR / ms | \u53d8\u5316\u5e27 OCR / ms | \u53d8\u5316\u5e27\u8017\u65f6\u53d8\u5316 |
|---|---:|---:|---:|---:|
{table}

{speed_zh}

\u8fd4\u56de\u540c\u56fe\u662f12\u6b21 A→B→A \u7684\u4e2d\u4f4d\u6570\uff1b\u53d8\u5316\u5e27\u662f8\u6b21\u6539\u53d8\u89d2\u843d\u50cf\u7d20\u540e\u7684\u4e2d\u4f4d\u6570\uff0c\u6587\u5b57\u672c\u8eab\u4e0d\u53d8\uff0c\u53ef\u590d\u7528\u5c40\u90e8\u7f13\u5b58\u3002\u8f83\u5feb\u7684\u91cd\u590d\u9875\u9762\u4e0d\u80fd\u4ee3\u8868\u6bcf\u4e2a\u9996\u6b21\u753b\u9762\u3002\u53d8\u5316\u5e27\u5e76\u975e\u6240\u6709\u573a\u666f\u5747\u66f4\u5feb\uff1b\u72b6\u6001\u9875\u7684\u5c40\u90e8\u989c\u8272\u68c0\u67e5\u6709\u989d\u5916\u6210\u672c\u3002\u5b8c\u6574\u6837\u672c\u3001p95\u3001\u9996\u6b21\u8fdb\u7a0b\u8c03\u7528\u8017\u65f6\u548c\u8fdb\u7a0b\u5de5\u4f5c\u96c6\u89c1[\u539f\u59cb\u6570\u636e](PERFORMANCE_REPORT.json)\u3002

## \u70b9\u540d\u6846\u67b6\u4e0e\u8c03\u4f18\u624b\u6bb5

\u4e24\u7248\u90fd\u4f7f\u7528 CPython3.14.10\u3001Tk9.0\u3001Tesseract5.5.4 / tesserocr2.13.0\u3001Pillow13.0.0\u3001httpx0.28.1\u3001C++17/Win32/GDI\uff0c\u5e76\u5171\u4eab\u76f8\u540c\u82f1\u8bed\u6a21\u578b\uff1b\u5404\u81ea\u7248\u672cDLL\u548cOCR\u4ee3\u7801\u4e0d\u540c\u3002\u6ca1\u6709\u628a\u57fa\u7840\u6846\u67b6\u91cd\u547d\u540d\u6210\u53e6\u4e00\u5957\u7b97\u6cd5\u3002

| \u8c03\u4f18\u524d\u57fa\u7ebf\uff1a0.01.15 | \u8c03\u4f18\u540e\uff1a0.01.24 |
|---|---|
| \u539f\u6709\u91cd\u590d\u9875\u9762 OCR \u8def\u5f84 | \u7cbe\u786e\u6574\u5e27RGB\u7f13\u5b58\uff0c\u5b57\u8282\u6821\u9a8c\u540e\u590d\u7528\u76f8\u540c\u56fe\u50cf |
| \u65e2\u6709\u50cf\u7d20\u8bc6\u522b\u4e0e\u5e03\u5c40 | \u540c\u5e27AUTO/SPARSE\u626b\u63cf\u3001\u6309\u5b9e\u6d4b\u8bcd\u6846\u5206\u680f\u3001\u53d7\u9650\u533a\u57df\u7ec6\u5316 |
| \u65e2\u6709\u9884\u5904\u7406 | \u5c40\u90e8RGB\u8272\u5dee\u8bc6\u522b\uff0c\u5904\u7406\u4e0d\u540c\u6781\u6027\u548c\u8fd1\u7b49\u4eae\u5ea6\u6587\u5b57 |
| \u91cd\u590d\u5c40\u90e8\u8bc6\u522b | \u6700\u591a64\u9879/16MiB\u7cbe\u786eRGB\u8865\u8bc6\u522b\u7f13\u5b58\uff0c\u6309\u5f53\u524d\u5750\u6807\u8fd8\u539f |
| \u539f\u6709\u8c03\u5ea6 | \u540c\u952e\u5728\u9014\u6d41\u5f0f\u5171\u4eab\u3001\u4e8c\u6b21\u6355\u83b7\u786e\u8ba4\u6298\u7b97\u7a33\u5b9a\u7b49\u5f85\uff1b\u6b64\u56fe\u672a\u5355\u72ec\u8ba1\u91cf\u5176\u589e\u76ca |

0.01.24\u53e6\u5916\u52a0\u51651–8\u624b\u52a8\u9009\u533a\u3001\u5206\u533a\u9694\u79bb\u53ca\u53ef\u9009\u76f8\u4f3c\u5b57\u4f53\uff1b\u672c\u6b21\u57fa\u51c6\u4f7f\u7528\u5b8c\u6574\u56fe\u7247\u3001\u5173\u95ed\u81ea\u52a8\u5b57\u4f53\uff0c\u4e0e\u65e7\u7248\u76f8\u540c\u8f93\u5165\u3002\u989d\u5916\u529f\u80fd\u5f00\u9500\u4e0d\u6df7\u8fdb\u65e7\u7248\u5bf9\u7167\u3002\u8bbe\u7f6e\u5141\u8bb8\u589e\u52a0\u8d44\u6e90\u5360\u7528\uff0c\u4f46\u7ebf\u7a0b\u8fc7\u591a\u4e0d\u7b49\u4e8e\u66f4\u5feb\u3002\u65e9\u671f\u6309\u788e\u7247\u5206\u914d\u8bc6\u522b\u5de5\u4f5c\u4f1a\u4e22\u5931\u53e5\u6bb5\u548c\u5206\u680f\u4e0a\u4e0b\u6587\uff1b\u5bf9\u5355\u4e00\u753b\u9762\u53cd\u590d\u589e\u52a0\u7279\u4f8b\u5c5e\u4e8e\u573a\u666f\u89c4\u5219\u8fc7\u62df\u5408\u98ce\u9669\uff0c\u5e76\u975e\u672c\u62a5\u544a\u8bc1\u660e\u4e86\u6a21\u578b\u8bad\u7ec3\u8fc7\u62df\u5408\u3002

## \u6d4b\u91cf\u8fb9\u754c

\u540c\u673a\u987a\u5e8f\u56de\u653e\u3001\u65e0\u771f\u5b9eAPI\u8bf7\u6c42\u3002\u5b57\u7b26\u6307\u6807\u4f7f\u7528\u4eba\u5de5\u6807\u6ce8\u5206\u533a\u3001Levenshtein\u7f16\u8f91\u8ddd\u79bb\u3001NFKC\u3001\u53bb\u7a7a\u767d\u3001\u7edf\u4e00\u5f2f\u5f15\u53f7\u3001\u4fdd\u7559\u5927\u5c0f\u5199\uff1b\u4e0d\u7b49\u4e8e\u5b9a\u4f4dIoU\u3001\u8de8\u6e38\u620f\u7cbe\u5ea6\u3001\u7ffb\u8bd1\u8d28\u91cf\u6216\u6e38\u620fFPS\u3002HELP\u906e\u6321\u884c\u4e0e\u72b6\u6001\u65e5\u671f\u4e0d\u5728\u6807\u6ce8\u96c6\u5408\u4e2d\u3002\u590d\u6742\u7eb9\u7406\u548c\u6781\u4f4e\u5bf9\u6bd4\u4ecd\u53ef\u80fd\u6f0f\u8bc6\u522b\u3002\u5b57\u4f53\u5339\u914d\u662f\u8fd1\u4f3c\u98ce\u683c\uff0c\u5e76\u975e\u539f\u5b57\u4f53\u8fd8\u539f\u3002

\u672c\u7248\u9a8c\u6536\u7ed3\u679c\u89c1[\u6d4b\u8bd5\u8bb0\u5f55](TEST_REPORT.json)\u3002150ms\u56fe\u8868\u5b9e\u8272\u4e3amax(0,150−\u8017\u65f6)\uff0c\u900f\u660e\u90e8\u5206\u4e3a\u5360\u7528\u65f6\u95f4\uff1b\u8d85\u9884\u7b97\u663e\u793a0\u5b9e\u8272\u5e76\u6807\u6ce8\u8d85\u51fa\u91cf\u3002\u6240\u6709\u901f\u5ea6\u767e\u5206\u6bd4\u53ea\u4ece\u540c\u4e00\u573a\u666f\u3001\u540c\u4e00\u9636\u6bb5\u7684\u5b9e\u6d4b\u8017\u65f6\u8ba1\u7b97\u3002
\'''
(ROOT/'docs/PERFORMANCE_REPORT.md').write_text(zh,encoding='utf-8')
english_table=table.replace('\u8d27\u7269\u4ef7\u683c\u8868','Cargo table').replace('\u72b6\u6001\u83dc\u5355','Status menu').replace('\u5267\u60c5\u9875','Story')
en=f\'''# Nishokuchou 0.01.24 · Performance and recognition report

18 November2026 · **Nishokuchou0.01.15 (pre-tuning baseline) →0.01.24 (tuned framework)**.

Open the [interactive image evidence](../PERFORMANCE_REPORT.html). The baseline is the oldest retained project version, not a claim about a third-party library's unmodified performance. No competitor was benchmarked.

## Measurements

Three identical Space Rogue Classic screenshots,356 annotated characters: zoned character accuracy **{before['accuracy']['character_accuracy_percent']:.2f}% → {after['accuracy']['character_accuracy_percent']:.2f}%**, **+{delta:.2f} percentage points**. Edit errors **{before['accuracy']['edits']} → {after['accuracy']['edits']}**, **{error_reduction:.1f}% fewer**.

| Scene | Accuracy:0.01.15 →0.01.24 | Revisited OCR / ms | Changed-frame OCR / ms | Changed-frame time change |
|---|---:|---:|---:|---:|
{english_table}

{speed_en}

Revisited results are medians of12 A→B→A returns. Changed frames use8 unique corner-pixel changes, preserving text pixels and allowing crop reuse. Changed-frame processing is not faster in every scene. Status-page color analysis costs extra time. [Raw data](../PERFORMANCE_REPORT.json) includes samples,p95,first process calls and working set. First calls include startup and OS-cache effects.

## Named framework and optimizations

Both use CPython3.14.10,Tk9.0,Tesseract5.5.4/tesserocr2.13.0,Pillow13.0.0,httpx0.28.1 and C++17/Win32/GDI, with the same English model and each version's own code/DLL. The tuned path adds exact full-frame reuse, bounded RGB crop reuse, measured column separation, whole-frame AUTO/SPARSE scans and bounded regional refinement. Local RGB contrast supports different foreground/background polarities. Shared in-flight translation streams and confirmed capture-time settling also exist, but their gains are not measured by this OCR chart.

Version0.01.24 adds1–8 manual selections and optional approximate font styles. The paired benchmark uses whole-image input with automatic styles off. Excess recognition workers can fragment contextual evidence; scene-specific correction rules risk overfitting the tested scene. This does not establish statistical model-training overfitting.

## Scope

Sequential same-computer offline runs, no real API. Character scoring uses annotated zones,Levenshtein distance,NFKC,whitespace removal and normalized curly quotes while preserving case. It is not localization IoU,translation quality,FPS or an all-game guarantee. Obscured HELP and status-date digits are excluded. Complex backgrounds and weak contrast remain difficult. See [validation](../TEST_REPORT.json).

The chart uses150ms: solid=max(0,150−latency),transparent=occupied time. Faster results have longer bars; overruns are explicit. Speed gains and latency reductions are distinct calculations.
\'''
'''
s=s[:start]+replacement+s[end:]
needle="zh=f'''"
s=s.replace(needle,"speed_zh='\uff1b'.join(f\"{scene['name']}\u8fd4\u56de\u540c\u56fe\uff1a\u7b49\u6548\u5904\u7406\u901f\u5ea6 {scene['before']['revisited']['p50_ms']/scene['after']['revisited']['p50_ms']:.2f}×\uff0c\u8017\u65f6\u51cf\u5c11 {(1-scene['after']['revisited']['p50_ms']/scene['before']['revisited']['p50_ms'])*100:.2f}%\" for scene in scenes)+'\u3002'\nspeed_en='; '.join(f\"{scene['file']}: {scene['before']['revisited']['p50_ms']/scene['after']['revisited']['p50_ms']:.2f}x equivalent processing speed, {(1-scene['after']['revisited']['p50_ms']/scene['before']['revisited']['p50_ms'])*100:.2f}% less elapsed time\" for scene in scenes)+'.'\n"+needle)
s=s.replace('Built paired OCR fix report','Built paired OCR performance report')
# Include actual latency reduction in each scene's chart, never a fabricated
# end-to-end or API speedup. Existing150ms inverse bars remain unchanged.
s=s.replace("+' ms'}$('bar-title')","+' ms'}$('bar-title')")
s=s.replace("'\u8fd4\u56de'+s.name+' · OCR \u7f13\u5b58\u547d\u4e2d'","'\u8fd4\u56de'+s.name+' · OCR\u8017\u65f6\u51cf\u5c11 '+f((1-s.after.revisited.p50_ms/s.before.revisited.p50_ms)*100)+'% · \u7b49\u6548\u901f\u5ea6 '+f(s.before.revisited.p50_ms/s.after.revisited.p50_ms)+'×'")
p.write_text(s,encoding='utf-8')
print('Report generator now requires measured0.01.15 and0.01.24 inputs.')
