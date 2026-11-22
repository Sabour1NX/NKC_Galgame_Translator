# SPDX-License-Identifier: MIT
"""Refresh reviewed 0.01.27 documentation, preserving historical measurements.

Run before build_html_docs.py / build_english_docs.py / build_delivery.py
--docs-only. This does not build packages or switch the project root launcher.
"""
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
if (DOCS/'PERFORMANCE_REPORT.json').is_file() and json.loads((DOCS/'PERFORMANCE_REPORT.json').read_text(encoding='utf-8')).get('schema') == 3:
    raise SystemExit('Fresh teacher-review evidence is canonical. Use python -X utf8 tools/build_teacher_review27.py --sync-canonical; this historical migration must not overwrite it.')
VERSION = '0.01.27'
ZH_OLD = '0.01.26 \u66f4\u65b0\u754c\u9762\u4e0e\u7a97\u53e3\u9009\u62e9\uff0c\u4fdd\u7559\u4e3b\u7a0b\u5e8f\u7a97\u53e3\u56fe\u6807\u3002\u6700\u8fd1\u7684\u901f\u5ea6\u4e0e\u7cbe\u5ea6\u6d4b\u91cf\u6765\u81ea 0.01.25\uff1b\u672c\u8f6e\u672a\u91cd\u65b0\u6d4b\u91cf\uff0c\u4e0d\u628a\u65e7\u6570\u503c\u5f53\u4f5c 0.01.26 \u5b9e\u6d4b\u3002'
EN_OLD = 'Version 0.01.26 updates the interface and window selection while retaining the application window icon. The latest speed and accuracy measurements are from 0.01.25. This update was not rebenchmarked; previous numbers are not measurements of 0.01.26.'
ZH_NOTE = '0.01.27 \u52a0\u5165\u53ef\u9009 CUDA OCR\u3001\u540e\u53f0\u8054\u7f51\u8bed\u5883\u4e0e\u6574\u7ec4\u5b57\u53f7\u4fee\u590d\u3002\u5386\u53f2\u771f\u5b9e API\u3001\u622a\u56fe\u548c\u6e38\u620f\u6027\u80fd\u6570\u636e\u4ecd\u6807\u4e3a 0.01.25 / 0.01.15\uff1b\u672c\u7248\u8c03\u5ea6\u6a21\u62df\u5355\u72ec\u5217\u793a\uff0c\u4e0d\u7b49\u540c\u771f\u5b9e\u6e38\u620f\u6216 API \u5ef6\u8fdf\u3002\u5f53\u524d\u9a8c\u8bc1\u8303\u56f4\u89c1 TEST_REPORT.json\u3002'
EN_NOTE = 'Version 0.01.27 adds optional CUDA OCR, background web context and group font fitting fixes. Historical real-API, screenshot and game measurements retain their 0.01.25 / 0.01.15 labels. This version has a separate simulated scheduling probe, not a real game/API latency measurement. See TEST_REPORT.json for current validation scope.'

CUDA_ZH = '''## 0.01.27 CUDA \u8bc6\u522b\u4e0e\u5b9e\u9645\u56de\u9000

\u9996\u6b21\u8bed\u8a00\u8bbe\u7f6e\u548c\u5e38\u89c4\u8bbe\u7f6e\u5171\u7528 CUDA \u63a7\u4ef6\u3002`cuda_enabled` \u9ed8\u8ba4\u5f00\u542f\uff1b\u53ea\u5728 OCR **\u81ea\u52a8\u6a21\u5f0f**\u4e14\u6e90\u8bed\u8a00\u4e3a\u82f1\u8bed\u3001\u65e5\u8bed\u6216\u4e2d\u6587\u65f6\u5c1d\u8bd5 CUDA\u3002\u624b\u52a8 Windows / Pixel \u6a21\u5f0f\u660e\u786e\u8d70 CPU\uff1b\u5176\u4ed6\u8bed\u8a00\u7ee7\u7eed\u4f7f\u7528\u5df2\u6709\u672c\u5730\u8bc6\u522b\u3002\u7ec4\u4ef6\u7f3a\u5931\u3001\u65e0\u517c\u5bb9 GPU\u3001\u6a21\u578b\u6821\u9a8c\u6216\u63a8\u7406\u5931\u8d25\u65f6\u56de\u9000 Windows / Tesseract\uff0c\u5e76\u663e\u793a\u5b9e\u9645\u72b6\u6001\uff0c\u4e0d\u80fd\u628a“\u6587\u4ef6\u5df2\u5b89\u88c5”\u5f53\u4f5c“CUDA \u5df2\u8fd0\u884c”\u3002\u5931\u8d25\u540e\u7684\u5f53\u524d OCR \u5b9e\u4f8b\u4e0d\u53cd\u590d\u91cd\u8bd5 GPU\uff0c\u4fee\u6539\u8bbe\u7f6e\u540e\u505c\u6b62\u5e76\u91cd\u65b0\u5f00\u59cb\u3002

| \u8bbe\u7f6e | \u9ed8\u8ba4 | \u8303\u56f4\u4e0e\u4f5c\u7528 |
|---|---|---|
| `cuda_enabled` | `true` | \u5f00\u5173\uff1b\u4e0d\u81ea\u52a8\u4e0b\u8f7d\u6216\u5b89\u88c5\u7ec4\u4ef6 |
| `cuda_quality` | `75` | 0–100\uff0c\u9ad8\u6027\u80fd\u5230\u9ad8\u7cbe\u5ea6\uff1b\u7ebf\u6027\u8c03\u8282\u68c0\u6d4b\u957f\u8fb9\uff0c\u6309 32 \u50cf\u7d20\u91cf\u5316 |
| `cuda_memory_mb` | `1024` | 256–16384 MiB\uff1b\u63a8\u7406\u5185\u5b58 arena \u9884\u7b97\uff0c\u4e0d\u4f1a\u5f3a\u884c\u5360\u6ee1 1 GiB\uff0c\u8fd0\u884c\u5e93\u548c\u9a71\u52a8\u53e6\u6709\u5f00\u9500 |

\u68c0\u6d4b\u957f\u8fb9\u7ea6\u4e3a `768 + 11.52 × cuda_quality` \u540e\u6309 32 \u50cf\u7d20\u91cf\u5316\uff1b75 \u5bf9\u5e94 1632 \u50cf\u7d20\u3002\u4ec5\u7f29\u5c0f\u8d85\u51fa\u4e0a\u9650\u7684\u56fe\u50cf\uff0c\u5c0f\u56fe\u5728\u4e0d\u540c\u6863\u4f4d\u53ef\u80fd\u7b49\u6548\uff1b\u6570\u503c\u4e0d\u662f\u51c6\u786e\u7387\u767e\u5206\u6bd4\uff0c\u4e5f\u4e0d\u4fdd\u8bc1\u5355\u8c03\u63d0\u901f\u6216\u63d0\u9ad8\u7cbe\u5ea6\u3002CUDA \u6a21\u578b\u4e3a PP-OCRv6-small\uff0cGPU/\u4f9d\u8d56\u9a8c\u8bc1\u7ed3\u679c\u4ee5\u672c\u7248\u62a5\u544a\u4e3a\u51c6\uff0c\u4e0d\u63d0\u524d\u58f0\u79f0\u6240\u6709 NVIDIA \u663e\u5361\u53ef\u7528\u3002

\u542f\u7528\u53ef\u9009\u4e91\u7aef AI \u56fe\u50cf\u7cbe\u8bfb\u65f6\uff0cCUDA \u5df2\u8f93\u51fa\u7684\u884c\u4ec5\u5728\u7f6e\u4fe1\u5ea6\u4e0d\u4f4e\u4e8e 95 \u4e14\u6ca1\u6709\u62d2\u7edd\u6807\u8bb0\u65f6\u76f4\u63a5\u9001\u8bd1\uff0c\u5176\u4f59\u4ecd\u8d70\u6838\u9a8c\u8def\u5f84\u3002**95 \u662f\u6a21\u578b\u5206\u6570\u95e8\u69db\uff0c\u4e0d\u662f 95% \u5b9e\u6d4b\u51c6\u786e\u7387\u627f\u8bfa**\u3002CUDA \u672c\u5730 OCR \u4e0d\u4e0a\u4f20\u56fe\u7247\uff1b\u4e91\u7aef\u7cbe\u8bfb\u4ecd\u9075\u5faa\u72ec\u7acb\u5f00\u5173\u548c\u56fe\u7247\u53d1\u9001\u89c4\u5219\u3002
'''
CUDA_EN = '''## 0.01.27 CUDA recognition and actual fallback

The first-run language page and regular settings share CUDA controls. `cuda_enabled` defaults to true. CUDA is attempted only in **Auto OCR mode** for English, Japanese or Chinese. Explicit Windows / Pixel modes use CPU, as do other languages. Missing components, incompatible hardware, invalid models or failed inference fall back to Windows / Tesseract with actual status. Installed files do not prove GPU execution. A failed OCR instance does not repeatedly retry CUDA; stop and restart after changing settings.

| Setting | Default | Range and meaning |
|---|---|---|
| `cuda_enabled` | `true` | Enable/disable; no automatic component downloads |
| `cuda_quality` | `75` | 0–100, performance to accuracy; linearly adjusts detector input limit with 32-pixel quantization |
| `cuda_memory_mb` | `1024` | 256–16384 MiB inference arena budget; does not force allocation of 1 GiB; runtime/driver overhead is additional |

The detector long-side limit is approximately `768 + 11.52 × cuda_quality`, rounded to a multiple of 32; 75 selects 1632 pixels. Only larger images are downscaled, so settings can be equivalent for small images. The slider is not an accuracy percentage and does not guarantee monotonically better accuracy or speed. The model is PP-OCRv6-small. Consult this version's GPU/dependency results rather than assuming every NVIDIA GPU works.

With optional cloud image refinement enabled, CUDA rows with confidence at least 95 and no rejection marker can proceed directly to translation; other rows remain on the verification path. **95 is a model-score threshold, not a measured 95% accuracy promise.** Local CUDA OCR uploads no image; cloud refinement remains a separate opt-in image-transfer path.
'''
FONT_ZH = '''## 0.01.27 \u6574\u7ec4\u62df\u5408\u4e0e\u77ed\u7eed\u884c

\u540c\u4e00\u6bb5\u6b63\u6587\u4ee5\u6e90\u884c\u58a8\u8ff9\u9ad8\u5ea6\u7684\u4e2d\u4f4d\u6570\u4f5c\u7a33\u5b9a\u53c2\u8003\u3002\u81f3\u5c11\u4e09\u884c\u4e14\u6709\u81f3\u5c11\u4e24\u6761\u5bbd\u6b63\u6587\u3001\u5bbd\u6b63\u6587\u5360\u591a\u6570\u65f6\uff0c\u6781\u77ed\u7eed\u884c\u6216\u660e\u663e\u4f4e\u58a8\u8ff9\u884c\u4e0d\u5355\u72ec\u628a\u6574\u7ec4\u538b\u6210\u6781\u5c0f\u5b57\u53f7\u3002\u5355\u4e2a Region \u5185\uff0c\u77ed\u7eed\u884c\u6ea2\u51fa\u53ef\u5c1d\u8bd5\u628a\u5b8c\u6574\u5b57\u7c07\u5206\u914d\u5230\u7d27\u90bb\u524d\u884c\u5df2\u6d4b\u5f97\u7684\u7a7a\u4f59\u5bbd\u5ea6\uff0c\u6700\u591a\u68c0\u67e5 64 \u4e2a\u5019\u9009\u4e14\u7eed\u884c\u81f3\u5c11\u4fdd\u7559\u4e00\u7c07\uff1b\u884c\u6846\u4e0d\u6269\u5927\u3002\u4e0d\u80fd\u5bb9\u7eb3\u7684\u5f31\u8bc1\u636e\u884c\u4fdd\u7559\u539f\u6587\u5b57\u50cf\u7d20\u3002\u8de8 Region \u4e0d\u632a\u52a8\u6587\u5b57\uff1b\u666e\u901a\u3001\u4e2d\u5bbd\u957f\u8bd1\u6587\u4ecd\u7ea6\u675f\u5171\u540c\u5b57\u53f7\u3002

\u6d41\u5f0f\u9636\u6bb5\u663e\u793a\u5f53\u524d\u53c2\u8003\u5b57\u53f7\u80fd\u5bb9\u7eb3\u7684\u524d\u7f00\uff0c\u5b8c\u6574\u8bd1\u6587\u4ecd\u7d2f\u8ba1\u4fdd\u5b58\uff1b\u5b8c\u6210\u540e\u518d\u6267\u884c\u6574\u7ec4\u62df\u5408\u548c\u6ee1\u5bbd\u5b57\u8ddd\u3002\u6807\u9898\u3001\u5217\u3001\u6e90\u5b57\u53f7/\u98ce\u683c\u3001\u56fa\u5b9a\u5b57\u53f7\u4e0e\u663e\u5f0f\u5b57\u53f7\u4e0a\u9650\u8fb9\u754c\u4fdd\u7559\u3002\u5c11\u6570\u5f31\u6846\u53ef\u80fd\u4ecd\u663e\u793a\u539f\u6587\uff0c\u6d41\u5f0f\u5c3e\u90e8\u53ef\u80fd\u7b49\u5230 final \u540e\u51fa\u73b0\u3002\u8fd9\u662f\u663e\u793a\u4fee\u590d\uff0c\u4e0d\u4ee3\u8868 OCR \u6216\u8bed\u4e49\u7ffb\u8bd1\u51c6\u786e\u7387\u63d0\u9ad8\u3002

\u4e0d\u65b0\u589e\u7528\u6237\u914d\u7f6e\uff0c\u4e0d\u6539\u53d8 ABI 2 \u6216\u539f\u6709\u5bfc\u51fa\u7b7e\u540d\uff1b\u539f\u751f\u8bca\u65ad\u65b0\u589e `font_intrinsic_px` \u4e0e `lines[].drawable`\u3002\u672c\u7248 C++ \u6838\u5fc3\u9700\u8981\u91cd\u65b0\u7f16\u8bd1\u4e0e\u9a8c\u6536\uff0c\u65e7\u7248 native audit \u4e0d\u6784\u6210\u672c\u7248\u4e8c\u8fdb\u5236\u8bc1\u636e\u3002
'''
FONT_EN = '''## 0.01.27 Group fitting and short continuation rows

Continuous body text uses median source-row ink height as a stable reference. In a group of at least three rows with at least two wide body rows forming a majority, a very short continuation or unusually shallow ink row does not alone shrink the whole paragraph. Within one region, overflowing continuation text can move complete clusters into measured spare width on the immediately preceding row: at most 64 candidates, retaining at least one cluster on the continuation. No row rectangle expands. A weak row that still cannot fit preserves original pixels. Text never transfers between regions; ordinary/medium-width long translations still constrain the shared font size.

Streaming paints the prefix fitting the current reference size while retaining cumulative full text; final output triggers group fitting and full-width spacing. Heading, column, source-style/size, fixed-size and explicit-cap boundaries remain. Some weak boxes can retain untranslated source, and a stream tail can wait for final output. This is a rendering fix, not an OCR or semantic-accuracy claim.

No new setting or ABI 2/export-signature change. Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. This version's C++ core requires a new build/audit; the old native audit does not certify its binary.
'''
CONTEXT_ZH = '''## 0.01.27 \u9996\u6587\u4e0d\u7b49\u5f85\u8054\u7f51\u53c2\u8003

`TranslationEngine.translate()` \u53ea\u8bfb\u53d6\u5df2\u5b8c\u6210\u7684 `ContextAgent.peek(key)`\uff0c\u7acb\u5373\u4ee5\u5f53\u524d\u539f\u6587\u3001\u624b\u52a8\u8bed\u5883\u4e0e\u5df2\u6709\u5386\u53f2\u53d1\u8d77\u65e0\u5de5\u5177\u7684\u8bd1\u6587\u8bf7\u6c42\u3002\u6210\u529f\u8bd1\u6587\u5b8c\u6210\u5e76\u91ca\u653e\u7f51\u7edc\u69fd\u540e\uff0c\u624d\u8c03\u7528 `refresh()` \u5c1d\u8bd5\u540e\u53f0\u68c0\u7d22\uff1b\u65b0\u53c2\u8003\u4f9b\u540e\u7eed\u8bed\u53e5\u4f7f\u7528\uff0c\u4e0d\u56de\u6539\u5df2\u663e\u793a\u7684\u8bd1\u6587\uff0c\u4e5f\u4e0d\u8fdb\u5165\u8986\u76d6\u4e8b\u4ef6\u3002

\u540e\u53f0\u6700\u591a\u4e00\u4e2a\u4f5c\u4e1a\u3001\u65e0\u7b49\u5f85\u961f\u5217\uff1b\u76f8\u540c\u8303\u56f4\u5171\u4eab\u7ed3\u679c\uff0c\u8303\u56f4\u952e\u5305\u542b\u6e38\u620f\u3001\u53ef\u6267\u884c\u8eab\u4efd\u3001\u6e90/\u76ee\u6807\u8bed\u8a00\u4e0e\u7528\u6237\u8bed\u5883\u3002\u6700\u591a 32 \u9879\u7f13\u5b58\uff0c\u6709\u6458\u8981 900 \u79d2\uff0c\u65e0\u6458\u8981\u6216\u5931\u8d25 30 \u79d2\u3002\u80cc\u666f\u8bf7\u6c42\u5171\u7528\u5e76\u53d1\u3001\u6b21\u6570\u3001token \u7edf\u8ba1\u4e0e\u53d6\u6d88\uff1b\u6709\u524d\u53f0\u7b49\u5f85\u8005\u65f6\u8ba9\u4f4d\uff0c\u5e76\u53d1\u4e0a\u9650\u4e3a 1 \u65f6\u4e0d\u5360\u7528\u552f\u4e00\u663e\u793a\u69fd\u3002\u9884\u7b97\u4f59\u91cf\u4e0d\u8db3\u65f6\u4f18\u5148\u8bd1\u6587\uff1b\u5173\u95ed\u5148\u53d6\u6d88 transport\uff0c\u518d\u7b49\u5f85\u80cc\u666f\u7ebf\u7a0b\u9000\u51fa\u3002

\u641c\u7d22\u5931\u8d25\u4e0d\u4f1a\u4e22\u6389\u5df2\u7ecf\u6210\u529f\u7684\u8bd1\u6587\uff1b\u8ba4\u8bc1/\u4f59\u989d\u9519\u8bef\u7684\u80cc\u666f\u72b6\u6001\u8bb0\u4e3a\u4e0d\u53ef\u7528\u5e76\u51b7\u5374\uff0c\u663e\u793a\u8bf7\u6c42\u81ea\u8eab\u7684\u9519\u8bef\u4ecd\u62a5\u544a\u3002\u72b6\u6001 `searching` \u53ea\u8868\u793a\u540e\u53f0\u5de5\u4f5c\uff0c`searched` \u9700\u6700\u7ec8\u670d\u52a1\u7aef\u6765\u6e90\u8bc1\u636e\u3002\u6e38\u620f\u3001\u5386\u53f2\u3001\u7f51\u9875\u548c\u6458\u8981\u90fd\u662f JSON \u4e2d\u7684\u4e0d\u53ef\u4fe1\u53c2\u8003\uff1b\u65e0\u672c\u5730\u5de5\u5177\u6267\u884c\u3001\u65e0\u8fd4\u56de URL \u81ea\u52a8\u8bbf\u95ee\u3001\u65e0\u5bc6\u94a5\u8fdb\u5165\u63d0\u793a\u3002
'''
CONTEXT_EN = '''## 0.01.27 Display does not wait for web reference

`TranslationEngine.translate()` reads only completed `ContextAgent.peek(key)` reference and immediately sends a tool-free translation request using current source, supplied context and available history. Only after successful translation and network-slot release does `refresh()` attempt background research. New notes benefit later sentences, never revise an already displayed translation or enter overlay events.

At most one background task and no waiting queue. The key includes game, executable identity, source/target languages and supplied context; 32 cached entries, 900 seconds with a summary and 30 seconds for empty/failed references. Background work shares concurrency, request/token accounting and cancellation, yields to waiting display jobs and does not use the sole slot when concurrency is one. Remaining budget favors translation. Closing cancels transport and joins the background worker.

Research failure cannot discard successful output. Background authentication/balance errors become unavailable with cooldown; errors in display requests still surface normally. `searching` denotes background work; `searched` requires final server-source evidence. Source/history/pages/notes remain untrusted JSON data: no local tools, automatic returned-URL fetches or credentials in prompts.
'''
PROBE_ZH = '''## 0.01.27 \u72ec\u7acb\u8c03\u5ea6\u6a21\u62df\uff1a\u4e0d\u662f\u5b9e\u673a\u6027\u80fd

`reports/context-latency27.json` \u4f7f\u7528 httpx MockTransport\u3001\u5168\u65b0\u5f15\u64ce\uff0c\u5404\u7248\u672c\u4e09\u6b21\uff1a\u6a21\u62df\u8054\u7f51\u53c2\u8003\u7b49\u5f85 300ms\u3001\u8bd1\u6587\u7b49\u5f85 15ms\u30020.01.26 \u9996\u6b21\u663e\u793a\u56de\u8c03\u4e2d\u4f4d\u4e3a **318.019ms**\uff0c0.01.27 \u4e3a **16.610ms**\uff1b\u8bf7\u6c42\u987a\u5e8f\u7531\u80cc\u666f→\u8bd1\u6587\u6539\u4e3a\u8bd1\u6587→\u80cc\u666f\uff0c\u5747\u8ba1 2 \u6b21\u8bf7\u6c42\uff0c\u5176\u4e2d 1 \u6b21\u8bed\u5883\u8bf7\u6c42\u3002\u65e0\u7f51\u7edc\u3001\u65e0\u771f\u5b9e API\u3001\u65e0\u6e38\u620f UI\uff0c\u4e0d\u4ee3\u8868\u771f\u5b9e OCR\u3001GPU\u3001\u7f51\u7edc\u6216\u7aef\u5230\u7aef\u6e38\u620f\u5ef6\u8fdf\u3002

\u5386\u53f2\u4e0b\u5217 API\u3001\u622a\u56fe\u7cbe\u5ea6\u4e0e\u5b9e\u673a\u6570\u636e\u4ecd\u5c5e\u4e8e 0.01.25 / 0.01.15\uff1b\u5c24\u5176 0.01.25 \u7684 10 \u79d2\u9996\u6587\u5305\u542b\u56fe\u50cf\u7cbe\u8bfb\u548c\u8054\u7f51\u53c2\u8003\uff0c\u4e0d\u80fd\u628a\u5168\u90e8\u5dee\u503c\u5f52\u56e0\u4e8e\u641c\u7d22\u3002\u672c\u7248\u539f\u751f/GPU\u53ca\u5b8c\u6574\u56de\u5f52\u7ed3\u8bba\u987b\u67e5\u770b\u6700\u7ec8 TEST_REPORT.json\uff0c\u4e0d\u628a\u5c40\u90e8\u6d4b\u8bd5\u6570\u5f53\u4f5c\u5b8c\u6574\u9a8c\u6536\u3002
'''
PROBE_EN = '''## 0.01.27 Separate scheduling simulation, not live performance

`reports/context-latency27.json` uses httpx MockTransport and three fresh-engine samples per version: simulated reference delay 300ms and display delay 15ms. Median first display callback changes from **318.019ms** in 0.01.26 to **16.610ms** in 0.01.27. Order changes from context→display to display→context, with two accounted requests including one context request in both. No network, real API or game UI is used. This does not measure real OCR, GPU, network or end-to-end game latency.

The historical real-API, screenshot-accuracy and live-game measurements below remain 0.01.25 / 0.01.15 results. The 0.01.25 ten-second first output included both vision refinement and web context; the entire delay cannot be attributed to search. Consult final TEST_REPORT.json for this version's native/GPU and full regression scope; partial test counts are not full acceptance.
'''

def write(path, text):
    path.write_text(text.rstrip()+'\n', encoding='utf-8')

def add(path, block):
    text=path.read_text(encoding='utf-8-sig')
    heading=block.splitlines()[0]
    if heading in text:return
    first, _, rest=text.partition('\n')
    write(path, first+'\n\n'+block+'\n'+rest.lstrip())

# Current documents only: named historic reports and changelog entries retain
# their original version labels and measurements.
for path in [ROOT/'README.md', *DOCS.rglob('*.md')]:
    if path.name in ('CHANGELOG.md','PERFORMANCE_REPORT_0.01.22.md'):continue
    text=path.read_text(encoding='utf-8-sig')
    migrate = ZH_OLD in text or EN_OLD in text or '0.01.27' not in text
    text=text.replace(ZH_OLD,ZH_NOTE).replace(EN_OLD,EN_NOTE)
    if migrate:text=text.replace('0.01.26','0.01.27')
    text=text.replace('0.01.27\u672a\u91cd\u6d4b\uff1b','0.01.27\u672a\u91cd\u6d4b\u8fd9\u4e9b\u5386\u53f2\u6837\u672c\uff1b').replace('0.01.27 was not rebenchmarked','0.01.27 did not remeasure those historical samples')
    write(path,text)

for en in (False,True):
    base=DOCS/'en' if en else DOCS
    for name in ('USER_GUIDE.md','CUSTOMER_GUIDE.md','LOCAL_TRANSLATION.md','UI_INTERFACES.md','INPUT_INTERFACES.md','DEPENDENCIES.md'):
        add(base/name,CUDA_EN if en else CUDA_ZH)
    for name in ('USER_GUIDE.md','CUSTOMER_GUIDE.md','API.md','ARCHITECTURE.md','WORKFLOWS.md'):
        add(base/name,FONT_EN if en else FONT_ZH)
    for name in ('API.md','ARCHITECTURE.md','WORKFLOWS.md','SECURITY.md','CONTEXT_AGENT.md'):
        add(base/name,CONTEXT_EN if en else CONTEXT_ZH)
    for name in ('PERFORMANCE_REPORT.md','HIGHLIGHT_FIX_REPORT.md'):
        add(base/name,PROBE_EN if en else PROBE_ZH)
    readme=base/'README.md' if en else ROOT/'README.md'
    for block in (CUDA_EN if en else CUDA_ZH,CONTEXT_EN if en else CONTEXT_ZH,FONT_EN if en else FONT_ZH):add(readme,block)

# Remove the retired synchronous contract instead of leaving contradictory prose.
zh=DOCS/'CONTEXT_AGENT.md';text=zh.read_text(encoding='utf-8')
text=text.replace('\u5148\u53d6\u5f97\u53d7\u9650\u80cc\u666f\u53c2\u8003\uff0c\u518d\u8fdb\u884c\u65e0\u5de5\u5177\u7684\u7eaf\u8bd1\u6587\u8bf7\u6c42','\u8bfb\u53d6\u5df2\u6709\u53d7\u9650\u80cc\u666f\u53c2\u8003\u540e\u7acb\u5373\u8fdb\u884c\u7eaf\u8bd1\u6587\u8bf7\u6c42\uff1b\u65b0\u80cc\u666f\u68c0\u7d22\u5728\u6210\u529f\u8bd1\u6587\u4e4b\u540e\u542f\u52a8')
text=text.replace('\u8054\u7f51\u7406\u89e3\u4f1a\u589e\u52a0\u4e00\u4e2a\u6a21\u578b\u8bf7\u6c42\u548c\u7b49\u5f85\u65f6\u95f4','\u8054\u7f51\u7406\u89e3\u4f1a\u589e\u52a0\u4e00\u4e2a\u540e\u53f0\u6a21\u578b\u8bf7\u6c42\uff0c\u4f46\u9996\u6bb5\u4e0d\u7b49\u5f85\u8be5\u8bf7\u6c42')
text=text.replace('\u8ba4\u8bc1\u3001\u4f59\u989d\u548c\u6743\u9650\u9519\u8bef\u76f4\u63a5\u62a5\u544a\uff0c\u4e0d\u4f2a\u88c5\u6210\u641c\u7d22\u6210\u529f','\u663e\u793a\u8bf7\u6c42\u7684\u8ba4\u8bc1\u3001\u4f59\u989d\u548c\u6743\u9650\u9519\u8bef\u76f4\u63a5\u62a5\u544a\uff1b\u80cc\u666f\u5931\u8d25\u6807\u4e3a\u4e0d\u53ef\u7528\u5e76\u51b7\u5374\uff0c\u4e0d\u4f2a\u88c5\u6210\u641c\u7d22\u6210\u529f')
text=text.replace('    D --> E[\u7eaf\u8bd1\u6587\u8bf7\u6c42]','    D -. \u540e\u7eed\u8bed\u53e5\u590d\u7528 .-> E[\u7eaf\u8bd1\u6587\u8bf7\u6c42]\n    E -. \u5b8c\u6210\u540e\u5237\u65b0 .-> C')
text=text.replace('`enabled/status/summary/sources/search_calls/cache_hits/cache_entries`','`enabled/status/summary/sources/search_calls/cache_hits/cache_entries/background_active`')
write(zh,text)
en=DOCS/'en/CONTEXT_AGENT.md';text=en.read_text(encoding='utf-8')
text=text.replace('Online context adds a model request and waiting time','Online context adds a background model request without making first display wait')
text=text.replace('Authentication, balance and permission errors remain visible.','Display authentication, balance and permission errors remain visible; background failures become unavailable with cooldown.')
text=text.replace('It obtains background references, then makes a translation-only request without tools.','It reads available references without waiting, sends a tool-free translation, then attempts background refresh after successful completion.')
text=text.replace('    D --> E[Translation-only request]','    D -. later requests .-> E[Translation-only request]\n    E -. after completion .-> C')
text=text.replace('`enabled/status/summary/sources/search_calls/cache_hits/cache_entries`','`enabled/status/summary/sources/search_calls/cache_hits/cache_entries/background_active`')
write(en,text)

for path in [ROOT/'README.md',*DOCS.rglob('*.md')]:
    if path.name in ('CHANGELOG.md','PERFORMANCE_REPORT_0.01.22.md'):continue
    text=path.read_text(encoding='utf-8')
    corrections={
        '\u4e0a\u9650\u4f9d\u636e\u6700\u5c0f\u6e90\u58a8\u8ff9\u9ad8\u5ea6\u3001\u663e\u5f0f\u5b57\u53f7\u548c\u540c\u4fee\u8ba2\u5df2\u6709\u5b57\u53f7\u786e\u5b9a':'\u4e0a\u9650\u4f9d\u636e\u7a33\u5b9a\u7684\u6e90\u58a8\u8ff9\u4e2d\u4f4d\u9ad8\u5ea6\u3001\u663e\u5f0f\u5b57\u53f7\u4e0e\u53ef\u590d\u7528\u7684\u540c\u4fee\u8ba2\u5b57\u53f7\u5386\u53f2\u786e\u5b9a\uff1b\u660e\u663e\u51e0\u4f55\u4fee\u6b63\u53ef\u91cd\u65b0\u6821\u51c6',
        'ceiling derived from minimum source ink height, explicit sizes and the same revision\'s prior fit':'ceiling derived from stable median source ink height, explicit sizes and reusable same-revision history; a substantial geometry correction permits recalibration',
        '\u540c\u4e00\u975e\u96f6 ID \u548c revision\u3001\u4e14\u65b0\u6587\u672c\u4e0e\u65e7\u6587\u672c\u76f8\u540c\u6216\u662f\u5176\u7d2f\u8ba1\u6269\u5c55\u65f6\uff0c\u5b57\u53f7\u6700\u591a\u4fdd\u6301\u6216\u7f29\u5c0f\uff0c\u4e0d\u56e0 OCR \u77e9\u5f62\u53d8\u5927\u3001\u79fb\u52a8\u6216\u6700\u7ec8\u5e27\u518d\u6b21\u5230\u8fbe\u800c\u653e\u5927\u3002':'\u540c\u4e00\u975e\u96f6 ID \u548c revision \u7684\u6d41\u5f0f\u7247\u6bb5\u4fdd\u6301\u53c2\u8003\u5b57\u53f7\uff0c\u5b8c\u6574\u7ed3\u679c\u518d\u7edf\u4e00\u62df\u5408\uff1b\u7ea6 1px \u7684\u51e0\u4f55\u6296\u52a8\u4e0d\u6539\u53d8\u5b57\u53f7\uff0c\u660e\u663e\u7684\u51e0\u4f55\u4fee\u6b63\u53ef\u6062\u590d\u5408\u7406\u5b57\u53f7\u3002',
        'Same-object/revision cumulative text can shrink to fit but does not grow again between stream fragments.':'Same-object/revision streaming preserves reference size and paints a fitting prefix, then fits the complete group at final output. Tiny geometry noise preserves font history; substantial geometry correction allows recalibration.',
        '\u65b0\u589e `font_intrinsic_px` \u4e0e `lines[].drawable`\u3002':'\u65b0\u589e `font_intrinsic_px` \u4e0e `lines[].drawable`\u3002`fits=true` \u8868\u793a\u53ef\u9760\u7ea6\u675f\u884c\u5df2\u62df\u5408\uff0c\u5f31\u5f02\u5e38\u884c\u4ecd\u53ef\u80fd `drawable=false`\uff0c\u9010\u884c\u53ef\u89c1\u6027\u5e94\u68c0\u67e5\u8be5\u5b57\u6bb5\u3002',
        'Native diagnostics add `font_intrinsic_px` and `lines[].drawable`.':'Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. `fits=true` means reliable constraint rows fit; a weak outlier can still have `drawable=false`, so inspect per-row visibility.',
        '\u624b\u52a8 Windows / Pixel \u6a21\u5f0f\u660e\u786e\u8d70 CPU\uff1b\u5176\u4ed6\u8bed\u8a00\u7ee7\u7eed\u4f7f\u7528\u5df2\u6709\u672c\u5730\u8bc6\u522b\u3002':'\u624b\u52a8 Windows / Pixel \u6a21\u5f0f\u660e\u786e\u8d70 CPU\uff1b\u81ea\u52a8\u6a21\u5f0f\u68c0\u6d4b\u5230\u7ecf\u5178\u82f1\u8bed\u50cf\u7d20\u753b\u9762\u4e14\u4fbf\u643a\u8bc6\u522b\u53ef\u7528\u65f6\u4f18\u5148 CPU Pixel \u8def\u5f84\uff08`pixel_priority`\uff09\uff1b\u5176\u4ed6\u8bed\u8a00\u7ee7\u7eed\u4f7f\u7528\u5df2\u6709\u672c\u5730\u8bc6\u522b\u3002',
        'Explicit Windows / Pixel modes use CPU, as do other languages.':'Explicit Windows / Pixel modes use CPU. Auto also prioritizes the CPU Pixel route for detected classic English pixel frames when the portable engine is available (`pixel_priority`); other languages use existing local OCR.',
        'disabled/ready/active/not_installed/failed/cpu_mode/unsupported_language':'disabled/ready/active/not_installed/failed/cpu_mode/pixel_priority/unsupported_language',
        '\u8bf7\u6c42\u4ec5 `image_path/language`\uff0c\u56fe\u7247\u5fc5\u987b\u5904\u4e8e':'\u8bc6\u522b\u8bf7\u6c42\u4ec5 `image_path/language`\uff1b`warmup()` \u53d1\u9001 `{"warmup":true}`\uff0c\u4ec5\u7528\u5408\u6210\u5f20\u91cf\u9a8c\u8bc1\u6a21\u578b\u548c CUDA\uff0c\u4e0d\u91c7\u5c4f\u3001\u4e0d\u8054\u7f51\uff1b`cancel()` \u53ef\u4e2d\u6b62 helper\uff0c\u53d6\u6d88\u7684\u5b9e\u4f8b\u4e0d\u53ef\u590d\u7528\u3002\u56fe\u7247\u5fc5\u987b\u5904\u4e8e',
        'Requests contain only `image_path/language`, with images restricted':'Recognition requests contain only `image_path/language`; `warmup()` sends `{"warmup":true}` using synthetic tensors without capture/network; `cancel()` interrupts the helper and the cancelled instance cannot restart. Images are restricted',
        '\u4e0d\u66ff\u4ee3\u5f53\u524d0.01.15→0.01.27\u5bf9\u7167':'\u4e0d\u66ff\u4ee3\u968f\u672c\u7248\u63d0\u4f9b\u76840.01.15→0.01.25\u5386\u53f2\u5b9e\u6d4b\uff1b0.01.27\u8c03\u5ea6\u6a21\u62df\u5355\u5217',
        'for this release versus 0.01.15':'for the historical 0.01.25 versus 0.01.15 measurements, with a separate 0.01.27 scheduling simulation',
        'prepares useful background references, asks the model':'reads available background references without waiting for web search, asks the model',
        'The optional context layer uses the single DeepSeek server-side search tool; the subsequent translation request has no tools.':'The optional background context layer uses the single DeepSeek server-side search tool; display translation requests have no tools and do not wait for new search.',
        '`ContextAgent.resolve` \u6309\u6e38\u620f\u8eab\u4efd':'`ContextAgent.peek/refresh` \u8ba9\u663e\u793a\u8bfb\u53d6\u5df2\u6709\u53c2\u8003\u3001\u6210\u529f\u8bd1\u6587\u540e\u540e\u53f0\u5237\u65b0\uff1b\u5185\u90e8 `resolve` \u6309\u6e38\u620f\u8eab\u4efd',
        '`ContextAgent.resolve` shares in-flight Futures':'`ContextAgent.peek/refresh` reads available notes and refreshes after successful display; internal `resolve` shares in-flight Futures',
        'Fit independently, then use the smallest fitting font among compatible body-text peers; unchanged text, coordinates, source rows and full-width spacing':'At final output, fit compatible body peers together; exclude qualifying weak continuation constraints, preserve unfit weak source rows, retain rectangles and full-width spacing',
        '\u539f\u751f\u7ebf\u7a0b\u5148\u62df\u5408\u5168\u90e8\u53ef\u89c1 Region\uff0c\u518d\u8bc6\u522b\u540c\u98ce\u683c\u8fde\u7eed\u6b63\u6587\u7ec4\u5e76\u91c7\u7528\u6210\u5458\u4e2d\u6700\u5c0f\u53ef\u5bb9\u7eb3\u5b57\u53f7\uff0c\u6700\u540e\u63d0\u4ea4\u7ed8\u5236\u3002':'\u539f\u751f\u7ebf\u7a0b\u5728 final \u5b8c\u6210\u65f6\u8054\u5408\u62df\u5408\u540c\u98ce\u683c\u8fde\u7eed\u6b63\u6587\u7ec4\uff0c\u666e\u901a\u957f\u884c\u7ea6\u675f\u5171\u4eab\u5b57\u53f7\uff0c\u7b26\u5408\u6761\u4ef6\u7684\u5f31\u7eed\u884c\u4e0d\u5355\u72ec\u538b\u5c0f\u6574\u7ec4\uff1b\u6d41\u5f0f\u9636\u6bb5\u5148\u663e\u793a\u53ef\u5bb9\u7eb3\u524d\u7f00\u3002',
        'The native thread fits all visible regions, chooses the smallest fitting font for compatible continuous body-text peers, then commits painting.':'At final completion, the native thread jointly fits compatible body peers; ordinary long rows constrain the group while qualifying weak continuations do not alone shrink it. Streaming first paints a fitting prefix.',
    }
    for old,new in corrections.items():text=text.replace(old,new)
    for sentence in ('`fits=true` \u8868\u793a\u53ef\u9760\u7ea6\u675f\u884c\u5df2\u62df\u5408\uff0c\u5f31\u5f02\u5e38\u884c\u4ecd\u53ef\u80fd `drawable=false`\uff0c\u9010\u884c\u53ef\u89c1\u6027\u5e94\u68c0\u67e5\u8be5\u5b57\u6bb5\u3002',
                     ' `fits=true` means reliable constraint rows fit; a weak outlier can still have `drawable=false`, so inspect per-row visibility.'):
        while sentence+sentence in text:text=text.replace(sentence+sentence,sentence)
    write(path,text)

install_zh='''## 0.01.27 \u53ef\u9009 CUDA \u7ec4\u4ef6\u5b89\u88c5

CUDA \u8fd0\u884c\u7ec4\u4ef6\u72ec\u7acb\u4e8e\u57fa\u7840\u7a0b\u5e8f\uff0c\u7ea6 2.1 GiB\uff0c\u53e6\u6709\u7ea6 31 MB \u7684\u6a21\u578b\uff1b\u5b9e\u9645\u5206\u53d1\u5927\u5c0f\u4ee5\u6e05\u5355\u4e3a\u51c6\u3002\u7528\u6237\u663e\u5f0f\u6267\u884c `vendor/python/python.exe tools/setup_cuda_ocr.py` \u624d\u4e0b\u8f7d\u548c\u5b89\u88c5\u5230\u9879\u76ee\u5185 `vendor/cuda` / `models/cuda`\uff1b`--verify` \u68c0\u67e5\u5df2\u5b89\u88c5\u7248\u672c\u4e0e\u6a21\u578b\u54c8\u5e0c\uff0c\u4e0d\u7b49\u540c\u771f\u5b9e GPU \u63a8\u7406\u6d4b\u8bd5\u3002\u4e0d\u4f1a\u4fee\u6539\u5168\u5c40 PATH/CUDA\uff0c\u4e0d\u5728\u666e\u901a\u8bbe\u7f6e\u5f00\u5173\u65f6\u81ea\u52a8\u5b89\u88c5\u3002\u7f3a\u7ec4\u4ef6\u4ecd\u53ef\u7528 CPU\u3002

\u7b2c\u4e09\u65b9\u7248\u672c\u3001SHA \u4e0e\u8bb8\u53ef\u5206\u522b\u89c1 `requirements-cuda.lock`\u3001`CUDA_DEPENDENCY_MANIFEST.json`\u3001`third_party/cuda/` \u548c `models/cuda/LICENSE`\u3002\u4e3b\u8fdb\u7a0b\u4ec5\u4f7f\u7528\u53d7\u9650\u56fe\u7247/JSON IPC\uff0c\u4e0d\u52a0\u8f7d\u6df1\u5ea6\u5b66\u4e60\u5305\u3002\u8fd0\u884c\u5e93 arena \u9884\u7b97\u4e0d\u5305\u542b\u9a71\u52a8\u53ca\u6240\u6709\u4e34\u65f6\u7f13\u51b2\uff1b\u6574\u673a nvidia-smi \u6570\u503c\u4e0d\u662f\u672c\u8fdb\u7a0b\u663e\u5b58\u7528\u91cf\u3002
'''
install_en='''## 0.01.27 Optional CUDA component installation

CUDA components are separate from the base program: approximately 2.1 GiB plus about 31 MB of models, with actual distribution size in the manifest. Explicitly run `vendor/python/python.exe tools/setup_cuda_ocr.py` to download/install into project-local `vendor/cuda` / `models/cuda`. `--verify` checks installed versions/model hashes, not real GPU inference. It does not modify global PATH/CUDA or install automatically when a settings switch changes. CPU remains available without these components.

Versions, hashes and licenses are in `requirements-cuda.lock`, `CUDA_DEPENDENCY_MANIFEST.json`, `third_party/cuda/` and `models/cuda/LICENSE`. The main process only uses bounded image/JSON IPC and does not import deep-learning packages. Arena budgets exclude driver and some temporary overhead; desktop-wide nvidia-smi usage is not this process's memory consumption.
'''
add(DOCS/'DEPENDENCIES.md',install_zh);add(DOCS/'en/DEPENDENCIES.md',install_en)
runtime_zh='''## 0.01.27 CUDA \u8fd0\u884c\u65f6\u4e0e\u9884\u70ed\u5951\u7ea6

\u5f53\u524d\u53ef\u9009\u7ec4\u4ef6\u9501\u5b9a ONNX Runtime GPU 1.32.0\u3001RapidOCR 3.10.0\u3001CUDA 13.x runtime / cuDNN 9.x\u3002\u672c\u673a RTX 3070 / \u9a71\u52a8 617.42 \u5df2\u9a8c\u8bc1\uff1b\u5176\u4ed6\u7ec4\u5408\u4e0d\u80fd\u636e\u6b64\u89c6\u4e3a\u517c\u5bb9\u3002\u6a21\u578b\u4e0e\u8f6e\u5b50 SHA \u56fa\u5b9a\uff1bprovider arena \u9884\u7b97\u62c6\u5206\u4e3a\u68c0\u6d4b/\u8bc6\u522b\u4e24\u90e8\u5206\uff0c\u9ed8\u8ba4\u5408\u8ba1 1 GiB\uff0c\u53e6\u6709\u9a71\u52a8\u548c\u8fd0\u884c\u5e93\u5185\u5b58\u3002

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` \u4fdd\u6301\u5e95\u5c42\u8c03\u7528\u9ed8\u8ba4\u4e0d\u542f\u7528\u7684\u517c\u5bb9\u884c\u4e3a\uff1bApp \u6309\u7528\u6237\u914d\u7f6e\u9ed8\u8ba4\u542f\u7528\uff0c\u5e76\u53ef\u4ea4\u63a5\u5df2\u7ecf\u9884\u70ed\u7684 `CudaOcr` \u5b9e\u4f8b\u3002`App._prepare_cuda()` \u7684\u540e\u53f0\u7ebf\u7a0b\u53ea\u8c03\u7528\u672c\u5730 `warmup()`\uff0c\u4e0d\u91c7\u5c4f\u6216\u8bf7\u6c42 API\uff1b\u540c helper \u53ef\u4f9b\u540e\u7eed OCR \u590d\u7528\u3002\u9884\u70ed\u4e0d\u4fdd\u8bc1\u6bcf\u4e2a\u65b0\u56fe\u50cf\u5f62\u72b6\u6ca1\u6709\u9996\u6b21\u63a8\u7406\u5f00\u9500\u3002
'''
runtime_en='''## 0.01.27 CUDA runtime and prewarm contracts

Optional components lock ONNX Runtime GPU 1.32.0, RapidOCR 3.10.0, CUDA 13.x runtime / cuDNN 9.x. RTX 3070 / driver 617.42 was verified locally; this does not certify other combinations. Wheel/model hashes are fixed. Detection and recognition provider arenas share the configured budget, totaling 1 GiB by default, with additional driver/runtime memory.

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` retains disabled-by-default low-level call compatibility; App passes the enabled user-setting default and may transfer a prewarmed `CudaOcr` instance. `App._prepare_cuda()` runs local `warmup()` in a background thread without screen capture or API requests, reusing the helper for later OCR. Prewarming does not eliminate first-inference cost for every new image shape.
'''
for en in (False,True):
    base=DOCS/'en' if en else DOCS
    for name in ('DEPENDENCIES.md','API.md','UI_INTERFACES.md'):
        add(base/name,runtime_en if en else runtime_zh)

interfaces_zh='''## 0.01.27 \u540e\u53f0\u8bed\u5883\u63a5\u53e3

| \u65b9\u6cd5 | \u5951\u7ea6 |
|---|---|
| `ContextAgent.peek(key)` | \u53ea\u8bfb\u5df2\u5b8c\u6210\u540c\u8303\u56f4\u53c2\u8003\uff1b\u4e0d\u7b49\u5f85 Future\uff1b\u4e0d\u53ef\u7528\u65f6\u8fd4\u56de\u7a7a\u53c2\u8003 |
| `ContextAgent.refresh(key, request, check_open, on_done=...)` | \u5c1d\u8bd5\u542f\u52a8\u5355\u4e2a\u540e\u53f0\u7ebf\u7a0b\uff0c\u65e0\u961f\u5217\uff1b\u8fd4\u56de\u662f\u5426\u542f\u52a8\u3002\u5f15\u64ce\u5148\u5360\u5171\u4eab\u7f51\u7edc\u69fd\uff0c`on_done` \u5728\u53d6\u6d88/\u5f02\u5e38/\u6b63\u5e38\u8def\u5f84\u7edf\u4e00\u5f52\u8fd8 |
| `ContextAgent.close()` | \u5728\u5f15\u64ce\u53d6\u6d88 transport \u540e\u5173\u95ed\u5e76 join\uff1b\u4e0d\u5f97\u6301\u5f15\u64ce\u9501\u7b49\u5f85 |
| `ContextAgent.resolve(...)` | \u5185\u90e8/\u517c\u5bb9\u540c\u6b65\u5355 flight \u539f\u8bed\uff1b\u5b9e\u65f6\u8bd1\u6587\u5165\u53e3\u4e0d\u518d\u540c\u6b65\u8c03\u7528\u5b83 |
| `status().background_active` | \u540e\u53f0\u5de5\u4f5c\u662f\u5426\u5b58\u5728\uff1b\u4e0e\u663e\u793a\u7ed3\u679c\u72ec\u7acb |
'''
interfaces_en='''## 0.01.27 Background context interfaces

| Method | Contract |
|---|---|
| `ContextAgent.peek(key)` | Read completed same-scope reference without waiting on a Future; empty reference when unavailable |
| `ContextAgent.refresh(key, request, check_open, on_done=...)` | Attempt one background thread, no queue; returns whether started. Engine reserves shared network capacity first; `on_done` releases it after success/error/cancellation |
| `ContextAgent.close()` | Close and join after engine transport cancellation; do not wait while holding the engine lock |
| `ContextAgent.resolve(...)` | Internal/compatible synchronous single-flight primitive, no longer called synchronously by the live translation entry |
| `status().background_active` | Background work state, separate from display result |
'''
add(DOCS/'CONTEXT_AGENT.md',interfaces_zh);add(DOCS/'en/CONTEXT_AGENT.md',interfaces_en)

cuda_contract_zh='''## 0.01.27 CUDA \u6a21\u5757\u4e0e IPC

| \u6a21\u5757 / \u7c7b | \u8bed\u8a00 | \u804c\u8d23 |
|---|---|---|
| `cuda_ocr.py` / `CudaOcr` | Python / MIT | \u672c\u5730 JSON IPC \u5ba2\u6237\u7aef\uff1b\u9690\u85cf helper \u8fdb\u7a0b\u3001\u56fe\u7247\u8def\u5f84\u3001\u54cd\u5e94\u9650\u989d\u3001\u751f\u547d\u5468\u671f\uff0c\u4e0d\u5728 GUI \u5bfc\u5165\u6df1\u5ea6\u5b66\u4e60\u5e93 |
| `tools/cuda_ocr_helper.py` / `Engine` | \u72ec\u7acb Python helper | RapidOCR / ONNX Runtime CUDA\u3001PP-OCRv6-small \u68c0\u6d4b\u4e0e\u8bc6\u522b\uff1b\u9a8c\u8bc1\u5b9e\u9645 CUDA kernel \u6267\u884c\u8bc1\u636e |
| `cuda_settings_ui.py` / `CudaControls` | Python / Tk | \u9996\u6b21\u8bed\u8a00\u9875\u4e0e\u666e\u901a\u8bbe\u7f6e\u5171\u4eab\u5f00\u5173\u3001\u7ebf\u6027\u7cfb\u6570\u6ed1\u6761\u53ca\u663e\u5b58\u9884\u7b97\uff1b\u4e0d\u63a2\u6d4b/\u4e0b\u8f7d\u6a21\u578b |
| `OcrCore` | Python | `auto` \u4e14 en/ja/zh \u65f6\u5c1d\u8bd5 GPU\uff0c\u5931\u8d25\u540e\u540c\u5e27\u56de\u9000\u5df2\u6709 CPU \u8def\u5f84\uff1b\u8fd4\u56de\u5b9e\u9645 `cuda_status` |

`CudaOcr(root, memory_mb=1024, quality=75)`\uff1b`available()` \u4ec5\u68c0\u67e5\u5fc5\u8981\u6587\u4ef6\uff1b`recognize(image, language='en')` \u4e32\u884c\u4ea4\u6362\uff1b`close()` \u5173\u95ed helper \u5e76\u6e05\u7406\u4e34\u65f6\u56fe\u7247\u3002\u8bf7\u6c42\u4ec5 `image_path/language`\uff0c\u56fe\u7247\u5fc5\u987b\u5904\u4e8e helper \u5141\u8bb8\u7684\u672c\u5730\u4e34\u65f6\u76ee\u5f55\uff0cstdin \u547d\u4ee4\u4e0d\u6267\u884c\u4e3a\u4ee3\u7801\u3002\u54cd\u5e94\u6709 `lines/ocr_ms/cuda`\uff0c\u6700\u591a 512 \u884c\u3001\u603b\u6587\u672c 64000 \u5b57\u7b26\u3001\u5b8c\u6574\u54cd\u5e94 1 MiB\uff1b\u5750\u6807\u987b\u4f4d\u4e8e\u56fe\u7247\u5185\uff0c\u7f6e\u4fe1\u5ea6\u4e3a\u6709\u9650 0–100 \u6570\u503c\u3002GPU \u63a5\u53d7\u6761\u4ef6\u5305\u62ec `CUDAExecutionProvider` \u548c `kernels_verified=true`\uff0c\u4e0d\u662f\u4ec5\u6839\u636e provider \u5217\u8868\u5224\u65ad\u3002

\u72b6\u6001\u5305\u62ec `disabled/ready/active/not_installed/failed/cpu_mode/unsupported_language`\uff1b`ready` \u4e0d\u4ee3\u8868\u5df2\u5b8c\u6210\u63a8\u7406\u3002\u4f9d\u8d56\u4e0e\u6a21\u578b\u6309\u7248\u672c\u548c SHA \u9501\u5b9a\uff0c\u89c1 `requirements-cuda.lock`\u3001`CUDA_DEPENDENCY_MANIFEST.json`\u3001`models/cuda/manifest.json`\u3002\u6a21\u578b/\u7ec4\u4ef6\u7684\u6388\u6743\u58f0\u660e\u7531\u53d1\u884c\u6e05\u5355\u63d0\u4f9b\uff1b\u5b89\u88c5\u6216\u9a8c\u6536\u5931\u8d25\u5fc5\u987b\u7ef4\u6301 CPU \u8def\u5f84\uff0c\u4e0d\u80fd\u4f2a\u62a5 GPU \u52a0\u901f\u3002
'''
cuda_contract_en='''## 0.01.27 CUDA modules and IPC

| Module / class | Language | Responsibility |
|---|---|---|
| `cuda_ocr.py` / `CudaOcr` | Python / MIT | Local bounded JSON IPC client, hidden helper, image paths and lifecycle; no deep-learning imports in the GUI |
| `tools/cuda_ocr_helper.py` / `Engine` | Separate Python helper | RapidOCR / ONNX Runtime CUDA, PP-OCRv6-small detection/recognition, verification of executed CUDA kernels |
| `cuda_settings_ui.py` / `CudaControls` | Python / Tk | Shared first-run/settings switch, linear quality slider and memory budget; no probing/downloads |
| `OcrCore` | Python | Attempt GPU in Auto for en/ja/zh; same-frame CPU fallback on failure, actual `cuda_status` |

`CudaOcr(root, memory_mb=1024, quality=75)` exposes `available()` (files only), serialized `recognize(image, language='en')` and `close()` (helper/temp-image cleanup). Requests contain only `image_path/language`, with images restricted to the allowed temporary root; stdin is data, never code. Responses contain `lines/ocr_ms/cuda`, at most 512 rows, 64000 total text characters and 1 MiB response size; rectangles must fit the image and confidence must be finite in 0–100. Acceptance requires `CUDAExecutionProvider` and `kernels_verified=true`, rather than provider availability alone.

States: `disabled/ready/active/not_installed/failed/cpu_mode/unsupported_language`; ready is not proof of completed inference. Versions and hashes are locked in `requirements-cuda.lock`, `CUDA_DEPENDENCY_MANIFEST.json` and `models/cuda/manifest.json`. Distribution manifests carry component/model licensing. Installation/verification failure must preserve CPU fallback rather than claiming GPU acceleration.
'''
for en in (False,True):
    base=DOCS/'en' if en else DOCS
    for name in ('API.md','INPUT_INTERFACES.md','ARCHITECTURE.md'):
        add(base/name,cuda_contract_en if en else cuda_contract_zh)

diagram_zh='''## 0.01.27 \u5b9e\u9645\u8fd0\u884c\u7ed3\u6784

```mermaid
flowchart LR
 UI[App / CudaControls \u4e3b\u7ebf\u7a0b] --> OCR[OcrCore \u91c7\u96c6\u8bc6\u522b\u7ebf\u7a0b]
 OCR --> GPU[CudaOcr JSON IPC]
 GPU --> HELP[\u72ec\u7acb CUDA helper / PP-OCRv6-small]
 OCR --> CPU[Windows / Tesseract CPU \u56de\u9000]
 OCR --> V[VisionCore \u9ad8\u7f6e\u4fe1\u76f4\u8bd1\u6216\u53ef\u9009\u6838\u9a8c]
 V --> T[TranslationEngine \u5e76\u53d1\u8bd1\u6587]
 CACHE[ContextAgent \u5df2\u5b8c\u6210\u8303\u56f4\u7f13\u5b58] --> T
 T --> D[OverlayState / C++ \u539f\u4f4d\u7ed8\u5236\u7ebf\u7a0b]
 T -. \u6210\u529f\u8bd1\u6587\u540e\u95f2\u4f59\u5171\u4eab\u69fd .-> BG[\u5355\u540e\u53f0\u8bed\u5883\u7ebf\u7a0b / \u65e0\u961f\u5217]
 BG --> CACHE
 T --> DB[SQLite \u538b\u7f29\u6863\u6848 / \u9501\u4fdd\u62a4]
```

CUDA helper \u72ec\u7acb\u4e8e\u4e3b GUI\uff1bCPU \u56de\u9000\u6cbf\u7528\u539f\u8bc6\u522b\u6d41\u7a0b\u3002\u540e\u53f0\u8bed\u5883\u6700\u591a\u4e00\u4e2a\u7ebf\u7a0b\u5e76\u5171\u4eab\u7f51\u7edc\u9650\u989d\uff0c\u4e0d\u4e3a\u6bcf\u4e2a\u6587\u5b57\u6846\u53e6\u5f00\u641c\u7d22\u8fdb\u7a0b\u3002\u663e\u793a\u5c42\u53ea\u6536\u5230\u8bd1\u6587\u548c\u672c\u5730\u51e0\u4f55\u3002
'''
diagram_en=diagram_zh.replace('0.01.27 \u5b9e\u9645\u8fd0\u884c\u7ed3\u6784','0.01.27 Runtime structure').replace('App / CudaControls \u4e3b\u7ebf\u7a0b','App / CudaControls main thread').replace('OcrCore \u91c7\u96c6\u8bc6\u522b\u7ebf\u7a0b','OcrCore capture / OCR thread').replace('\u72ec\u7acb CUDA helper','Separate CUDA helper').replace('CPU \u56de\u9000','CPU fallback').replace('VisionCore \u9ad8\u7f6e\u4fe1\u76f4\u8bd1\u6216\u53ef\u9009\u6838\u9a8c','VisionCore trusted rows or optional verification').replace('TranslationEngine \u5e76\u53d1\u8bd1\u6587','TranslationEngine concurrent display').replace('ContextAgent \u5df2\u5b8c\u6210\u8303\u56f4\u7f13\u5b58','ContextAgent completed scoped cache').replace('C++ \u539f\u4f4d\u7ed8\u5236\u7ebf\u7a0b','C++ rendering thread').replace('\u6210\u529f\u8bd1\u6587\u540e\u95f2\u4f59\u5171\u4eab\u69fd','after success / spare shared slot').replace('\u5355\u540e\u53f0\u8bed\u5883\u7ebf\u7a0b / \u65e0\u961f\u5217','One context worker / no queue').replace('SQLite \u538b\u7f29\u6863\u6848 / \u9501\u4fdd\u62a4','SQLite compressed archive / locked')
diagram_en=diagram_en[:diagram_en.index('CUDA helper \u72ec\u7acb')]+'The CUDA helper is separate from the GUI. Background context uses at most one thread and shared network capacity, never a search process per text box. Display receives only translations and local geometry.\n'
add(DOCS/'ARCHITECTURE.md',diagram_zh);add(DOCS/'en/ARCHITECTURE.md',diagram_en)

for path, block in ((ROOT/'CHANGELOG.md', '# 0.01.27 — 2026-11-18\n\n'+CUDA_ZH+CONTEXT_ZH+FONT_ZH), (DOCS/'en/CHANGELOG.md','# 0.01.27 — 2026-11-18\n\n'+CUDA_EN+CONTEXT_EN+FONT_EN)):
    if not path.read_text(encoding='utf-8-sig').startswith('# 0.01.27'):
        write(path,block+'\n'+path.read_text(encoding='utf-8-sig'))

update=json.loads((DOCS/'UPDATE.json').read_text(encoding='utf-8-sig'))
update.update(version=VERSION,release_folder=VERSION,notes='Optional CUDA OCR, post-display background context and group font fitting. Historical measurements remain labeled; current probes are separate.')
write(DOCS/'UPDATE.json',json.dumps(update,ensure_ascii=False,indent=2))
test=json.loads((DOCS/'TEST_REPORT.json').read_text(encoding='utf-8-sig'))
if test.get('version')!='0.01.27':
    write(DOCS/'TEST_REPORT_0.01.26.json',json.dumps(test,ensure_ascii=False,indent=2))
    test={'schema':2,'version':VERSION,'date':'2026-11-18','validation_status':'pending_integrated_validation',
          'scope':'Current feature checks are partial; final integration, native rebuild, GPU checks and packages remain separately reportable.',
          'automated_batches':[{'passed':130,'failed':0,'scope':'Context/background scheduling, translation and archive checks only','report':'reports/context-latency27.json'}],
          'full_suite_reexecuted':False,'native_and_dependencies':'New C++ build and optional CUDA dependency audit required; no inherited binary-identity claim.',
          'historical_evidence':['TEST_REPORT_0.01.26.json','TEST_REPORT_0.01.25.json'],
          'performance_measurement_version':'0.01.25','performance_rebenchmarked':False,
          'current_simulation':'reports/context-latency27.json','documentation':{'manual_chapters_each_language':18,'static_check':'reports/manual-html-check.json'}}
    write(DOCS/'TEST_REPORT.json',json.dumps(test,ensure_ascii=False,indent=2))
for name in ('PERFORMANCE_REPORT.json','HIGHLIGHT_FIX_REPORT.json'):
    path=DOCS/name;data=json.loads(path.read_text(encoding='utf-8-sig'))
    data.update(distributed_with_version=VERSION,measurement_version='0.01.25',rebenchmarked=False,distribution_note=EN_NOTE,
                current_version_offline_probe=json.loads((ROOT/'reports/context-latency27.json').read_text(encoding='utf-8')))
    write(path,json.dumps(data,ensure_ascii=False,indent=2))

# SVG remains code-native and script-free. Update existing visual labels and
# direction semantics; cached reference is read without waiting on web search.
path=DOCS/'PROJECT_GUIDE.html';text=path.read_text(encoding='utf-8').replace('0.01.26','0.01.27')
text=re.sub(r'<main><p style="padding:16px[\s\S]*?</p>', '<main><p class="sub">'+ZH_NOTE+'</p>', text, count=1)
for old,new in {'\u6574\u5e27\u53d1\u73b0 / \u5c40\u90e8\u8272\u5dee\u4e0e\u7cbe\u8bfb':'CUDA auto / CPU \u56de\u9000 / \u539f\u56fe\u6846',
                'OcrCore / helper · Python+C++':'OcrCore / CudaOcr · Python',
                '\u5df2\u6d4b\u884c\u5019\u9009 / \u539f\u56fe\u5750\u6807':'JSON IPC / GPU helper \u6216 CPU',
                '\u80cc\u666f\u8bf7\u6c42\u5171\u4eab / \u6709\u754c\u6765\u6e90':'\u5b8c\u6210\u8bd1\u6587\u540e\u540e\u53f0\u5237\u65b0 / \u65e0\u961f\u5217',
                '\u5386\u53f2\u6458\u5f55 / \u53ef\u9009\u80cc\u666f\u641c\u7d22':'\u5386\u53f2\u6458\u5f55 / \u5df2\u5b8c\u6210\u80cc\u666f\u53c2\u8003',
                '\u641c\u7d22\u6458\u8981\u3001\u6765\u6e90\u4e0d\u8fdb\u5165\u8bd1\u6587':'\u9996\u6587\u4e0d\u7b49\u641c\u7d22 / \u540e\u7eed\u8bed\u53e5\u590d\u7528',
                '\u540c\u6bb5\u5b57\u53f7\u4e00\u81f4 / \u957f\u884c\u5171\u540c\u7f29\u5c0f':'\u6574\u7ec4\u62df\u5408 / \u77ed\u5c3e\u884c\u4e0d\u538b\u57ae\u6b63\u6587',
                '\u5df2\u6709\u6d4b\u91cf':'\u5386\u53f2\u6d4b\u91cf'}.items():text=text.replace(old,new)
write(path,text)
for name in ('build_html_docs.py','build_english_docs.py','build_delivery.py'):
    path=ROOT/'tools'/name;text=path.read_text(encoding='utf-8').replace('0.01.26','0.01.27')
    text=text.replace('History + optional web references','History + completed web references').replace('Whole-frame OCR, then refinement','CUDA auto / CPU fallback / refinement')
    text=text.replace('No reasoning or sources in overlay','Post-display background refresh')
    text=text.replace('One union frame; black masked gaps','CUDA helper or Windows / Tesseract').replace('Parallel ink refinement:1–8 workers','JSON IPC; local source geometry')
    text=text.replace('Scoped zlib history + server research','Scoped history; completed web notes').replace('Shared context; no overlay metadata','Refresh after display; no waiting queue')
    # Publication must be explicit; generating docs never switches root entry.
    if name=='build_delivery.py' and "if args.publish_root:" not in text:
        text=text.replace("args=parser.parse_args()","parser.add_argument('--publish-root',action='store_true');args=parser.parse_args()")
        text=re.sub(r"(?m)^(\(ROOT\.parent/'OPEN_FIRST.html'\).*write_text\(.*)$",r'if args.publish_root:\n    \1',text)
    write(path,text)

# Preserve embedded historical screenshots and all measurement values.
from markdown_it import MarkdownIt
md=MarkdownIt('commonmark',{'html':False}).enable('table')
for name in ('PERFORMANCE_REPORT.html','HIGHLIGHT_FIX_REPORT.html','PERFORMANCE_REPORT.en.html','HIGHLIGHT_FIX_REPORT.en.html'):
    path=DOCS/name;text=path.read_text(encoding='utf-8')
    text=text.replace(ZH_OLD,ZH_NOTE).replace(EN_OLD,EN_NOTE)
    if 'id="probe27"' not in text:text=text.replace('0.01.26','0.01.27')
    if 'id="probe27"' not in text:
        section='<section id="probe27">'+md.render(PROBE_EN if '.en.' in name else PROBE_ZH)+'</section>'
        if '</header>' in text:text=text.replace('</header>','</header>'+section,1)
        else:text=text.replace('</h1>','</h1>'+section,1)
    write(path,text)
print('Updated 0.01.27 source docs and static report distribution labels; historical measurements preserved.')
