# SPDX-License-Identifier: MIT
"""One-time migration of reviewed 0.01.23 documentation to the 0.01.24 tree."""
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
assert ROOT.name=='0.01.24'
marker=ROOT/'reports/docs24-prepared.json'
assert not marker.exists(), 'Documentation migration already applied'

zh_user='''## \u591a\u533a\u57df\u4e0e\u81ea\u52a8\u5b57\u4f53

\u5728\u5c4f\u5e55\u7ffb\u8bd1\u9875\u9009\u62e9\u6e38\u620f\u7a97\u53e3\uff0c\u70b9\u51fb“\u6846\u9009\u533a\u57df”\u3002\u8fde\u7eed\u62d6\u52a8\u6dfb\u52a0 **1–8 \u4e2a\u4e0d\u91cd\u53e0\u77e9\u5f62**\uff1b\u6309 **Enter \u786e\u8ba4**\uff0c\u6309\u9000\u683c\u6216\u53f3\u952e\u64a4\u9500\u6700\u540e\u4e00\u4e2a\uff0cEsc \u53d6\u6d88\u5e76\u4fdd\u7559\u539f\u9009\u62e9\u3002\u6bcf\u6846\u81f3\u5c11 20 × 20 \u50cf\u7d20\uff1b\u5408\u5e76\u5916\u63a5\u77e9\u5f62\u6bcf\u8f74\u4e0d\u8d85\u8fc7 4096 \u50cf\u7d20\u3002\u8bf7\u628a\u4e00\u6574\u6bb5\u6587\u5b57\u7559\u5728\u540c\u4e00\u6846\u5185\uff0c\u5e76\u7559\u5c11\u91cf\u8fb9\u8ddd\u3002\u533a\u57df\u968f\u6e38\u620f\u5ba2\u6237\u533a\u79fb\u52a8\uff0c\u7f29\u653e\u540e\u88c1\u5230\u5ba2\u6237\u533a\uff1b\u66f4\u6362\u6e38\u620f\u7a97\u53e3\u540e\u6062\u590d\u6574\u4e2a\u5ba2\u6237\u533a\u3002\u9009\u533a\u4ec5\u5728\u672c\u6b21\u754c\u9762\u4f1a\u8bdd\u4fdd\u7559\u3002

\u591a\u4e2a\u9009\u533a\u4f7f\u7528\u540c\u4e00\u5e27\u6355\u83b7\uff0c\u6846\u5916\u95f4\u9699\u5148\u906e\u6210\u9ed1\u8272\u518d\u8fdb\u5165 OCR \u6216\u53ef\u9009 AI \u56fe\u50cf\u7cbe\u8bfb\uff1b\u8bed\u53e5\u56e2\u548c\u5bf9\u8c61\u5173\u8054\u4e0d\u8de8\u9009\u533a\u3002\u6846\u9009\u4e0d\u540c\u533a\u57df\u4e0d\u4f1a\u5206\u522b\u542f\u52a8\u591a\u4e2a OCR \u8fdb\u7a0b\uff0c\u4e5f\u4e0d\u6539\u53d8\u7ffb\u8bd1\u5e76\u53d1\u4e0a\u9650\u3002\u5168\u5c4f\u6e38\u620f\u5efa\u8bae\u5207\u6362\u7a97\u53e3\u6a21\u5f0f\u3002

\u6253\u5f00“\u8bbe\u7f6e → \u8bd1\u6587\u5916\u89c2 → \u6309\u539f\u6587\u81ea\u52a8\u9009\u62e9\u76f8\u4f3c\u98ce\u683c\u5b57\u4f53\uff08\u652f\u6301\u76ee\u6807\u8bed\u8a00\uff09”\uff0c\u4fdd\u5b58\u540e\u91cd\u65b0\u5f00\u59cb\u7ffb\u8bd1\u3002\u7a0b\u5e8f\u6839\u636e\u539f\u6587\u5b57\u5f62\u8fd1\u4f3c\u9009\u62e9\u50cf\u7d20\u3001\u886c\u7ebf\u3001\u65e0\u886c\u7ebf\u6216\u7b49\u5bbd\u98ce\u683c\uff0c\u5e76\u9010\u6846\u68c0\u67e5\u5b57\u4f53\u662f\u5426\u652f\u6301\u76ee\u6807\u8bed\u8a00\u4e0e\u5f53\u524d\u8bd1\u6587\u5b57\u5f62\u3002\u65e0\u9700\u4e0b\u8f7d\u5b57\u4f53\u3002\u9ed8\u8ba4\u5173\u95ed\uff0c\u5173\u95ed\u65f6\u4ecd\u4f7f\u7528\u624b\u52a8\u5b57\u4f53\u3002\u81ea\u52a8\u5b57\u53f7\u53ca\u4e0a\u4e0b\u9650\u72ec\u7acb\u8bbe\u7f6e\uff0c\u8fc7\u957f\u8bd1\u6587\u7ee7\u7eed\u5728\u5141\u8bb8\u8303\u56f4\u5185\u7f29\u5c0f\u3002

\u5b57\u4f53\u5339\u914d\u4e0d\u7b49\u4e8e\u8fd8\u539f\u6e38\u620f\u5b57\u4f53\uff1b\u88c5\u9970\u5b57\u3001\u590d\u6742\u80cc\u666f\u3001\u77ed\u8bcd\u548c\u8bef\u8bc6\u522b\u53ef\u80fd\u5f71\u54cd\u98ce\u683c\u5224\u65ad\u3002\u5b57\u5f62\u4e0d\u5168\u65f6\u6539\u7528\u5df2\u5b89\u88c5\u4e14\u8986\u76d6\u8bd1\u6587\u7684\u540e\u5907\u5b57\u4f53\uff1b\u6ca1\u6709\u5408\u9002\u5b57\u4f53\u65f6\u4fdd\u7559\u539f\u6587\u3002\u5f53\u524d\u81ea\u52a8\u8986\u76d6\u68c0\u67e5\u4fdd\u5b88\u652f\u6301 BMP \u5b57\u7b26\uff1b\u542b\u8865\u5145\u5e73\u9762\u5b57\u7b26\u6216 emoji \u7684\u8be5\u6846\u4fdd\u7559\u539f\u6587\uff0c\u53ef\u5207\u56de\u624b\u52a8\u5b57\u4f53\u4f7f\u7528 Windows \u5b57\u4f53\u56de\u9000\u3002
'''
en_user='''## Multiple selections and automatic font styles

Choose a game window and click **Select region**. Drag repeatedly to add **1–8 non-overlapping rectangles**. Press **Enter to confirm**, Backspace or right-click to undo the last rectangle, or Esc to cancel without changing the previous selection. Minimum rectangle: 20 × 20 pixels. Combined bounds: at most 4096 pixels per axis. Keep each complete paragraph inside one rectangle with a small margin. Selections follow the game client, clip on resize and reset to the whole client when choosing a different game window. Selections last for the current UI session.

One captured frame serves all selections. Gaps between rectangles are blacked out before OCR or optional AI image reading. Grouping and tracking do not cross selection boundaries. Adding regions does not start independent OCR processes or change translation concurrency. Use windowed mode when needed.

In **Settings → Translation appearance**, enable **Match the source font style automatically (target-language support)**, save and restart translation. Local screenshot evidence approximates pixel, serif, sans-serif or monospaced style. Each box checks the installed font against the target script and actual translated characters. No font downloads are needed. This option defaults to off; disabling it restores the manual font. Size fitting and minimum/maximum sizes remain independent settings.

This matches broad style, not the original font file. Decorative text, complex backgrounds, short words and OCR mistakes can affect classification. Missing glyphs trigger an installed compatible fallback; if none exists, the original remains visible. Automatic coverage checking conservatively supports BMP characters. A box containing supplementary-plane characters or emoji retains the source; manual font mode remains available with Windows fallback.
'''
zh_api='''## 0.01.24 \u63a5\u53e3\u589e\u91cf

| \u63a5\u53e3/\u5b57\u6bb5 | \u8f93\u5165\u3001\u8fd4\u56de\u4e0e\u7ea6\u675f |
|---|---|
| `selection_regions.capture_plan(value)` | `None`\u3001\u65e7\u5355\u77e9\u5f62 `(x,y,w,h)` \u6216 1–8 \u77e9\u5f62\u5217\u8868\uff1b\u8fd4\u56de\u4e0d\u53ef\u53d8 `CapturePlan(bounds, regions)`\uff1b\u5750\u6807\u4e3a\u6574\u6570\uff0c\u62d2\u7edd bool\u3001\u91cd\u53e0\u548c\u8d85\u9650\uff1b\u975e\u6cd5\u503c\u629b `ValueError` |
| `CapturePlan.bounds / regions` | bounds \u662f\u7edd\u5bf9\u5c4f\u5e55\u5916\u63a5\u77e9\u5f62\uff1bregions \u662f\u76f8\u5bf9\u8be5\u5916\u63a5\u77e9\u5f62\u7684\u4e0d\u53ef\u53d8\u5c40\u90e8\u77e9\u5f62\u5143\u7ec4\uff1b\u8054\u5408\u5bbd\u9ad8\u5404 ≤4096 |
| `client_selections(relative, client)` | \u6e38\u620f\u76f8\u5bf9\u5750\u6807\u88c1\u5230\u5f53\u524d\u5ba2\u6237\u533a\u5e76\u8f6c\u5c4f\u5e55\u5750\u6807\uff1b\u5168\u90e8\u5728\u5916\u8fd4\u56de None\uff1b\u4e0d\u6355\u83b7\u90bb\u8fd1\u5e94\u7528 |
| `OcrCore.set_capture_regions(regions)` | \u5728\u4e00\u6b21\u6355\u83b7\u524d\u8bbe\u7f6e\u5c40\u90e8\u9009\u533a\uff1b\u6539\u53d8\u8303\u56f4\u4f7f\u6355\u83b7\u5931\u6548\uff1b\u8303\u56f4\u8fdb\u5165\u6574\u5e27\u7f13\u5b58\u952e |
| `prepare_capture_image(image)` | \u8fd4\u56de\u8c03\u7528\u8005\u62e5\u6709\u7684 RGB PIL \u56fe\u50cf\uff1b\u6846\u5916\u95f4\u9699\u9ed1\u8272\uff0c\u4e0d\u4fee\u6539\u6e90\u56fe\uff1bVision \u4e0a\u4f20\u524d\u4e5f\u5e94\u7528\u6b64\u89c4\u5219 |
| `_selection_id` | \u672c\u5730\u6574\u6570\u8fb9\u754c\uff1b\u5e03\u5c40\u3001AI \u951a\u6846\u6574\u7406\u3001\u8ddf\u8e2a\u5747\u4e0d\u5f97\u8de8\u6b64\u8fb9\u754c\u5408\u5e76 |
| `SourceStyleMatcher.classify(image,line)` | \u56fe\u50cf\u5750\u6807 OCR \u884c → sans / serif / mono / pixel\uff1b\u5355\u6846\u6700\u591a 65536 \u50cf\u7d20\u300196 \u4e2a\u6e90\u5b57\u7b26\uff1b256 \u9879\u6709\u754c\u7f13\u5b58\uff0c\u65e0\u7f51\u7edc |
| `TargetFontSelector.choose(style,text)` | \u76ee\u6807\u8bed\u79cd\u6837\u672c + \u5b9e\u9645\u8bd1\u6587\u5b57\u7b26\u9a8c\u8bc1\uff1b\u8fd4\u56de `(family,pixel)` \u6216 None\uff1b\u6700\u591a4096\u4e2a\u4e0d\u540cBMP\u5b57\u7b26\uff0c256\u9879\u7f13\u5b58 |
| `set_auto_font_style(enabled,target)` | \u5e03\u5c14\u5f00\u5173\u4e0e\u76ee\u6807\u8bed\u8a00\u4ee3\u7801\uff1b\u505c\u6b62\u540e\u914d\u7f6e\uff1b\u624b\u52a8\u5b57\u4f53\u4e0d\u4e22\u5931 |
| `_source_font_style` | OCR \u672c\u5730\u6e90\u56fe\u8bc1\u636e\u9644\u52a0\u5143\u6570\u636e\uff1b\u4f20\u7ed9\u8bd1\u6587\uff0c\u4e0d\u4f5c\u4e3a\u6a21\u578b\u6307\u4ee4\u6216\u5916\u90e8\u5b57\u4f53\u8def\u5f84 |
| `gl_font_supports(family,text)` | C ABI \u65b0\u5bfc\u51fa\uff1b\u540d\u79f01–31 UTF-16\u5355\u4f4d\uff0c\u6587\u672c≤4096\uff1b\u786e\u8ba4\u5b89\u88c5\u5b57\u4f53\u5e76\u68c0\u67e5\u5b57\u5f62\uff0c\u8fd4\u56de1/0\uff1b\u8865\u5145\u5e73\u9762\u5b57\u7b26\u4fdd\u5b88\u8fd4\u56de0 |
| `gl_overlay_styled(ctx,regions,count,rows,row_count,offsets,origins,families,pixel_fonts)` | \u7ee7\u627f `gl_overlay_anchored` \u5e03\u5c40\uff1borigins\u8bca\u65ad\u65f6\u53efnull\uff1bfamilies/count\u3001pixel_flags/count\u5e76\u884c\u6570\u7ec4\uff0cflags\u96500/1\u3002\u9a8c\u8bc1\u5931\u8d25\u8fd4\u56de0\uff0c\u4e0d\u63d0\u4ea4\u90e8\u5206\u7ed3\u679c\u3002\u6cbf\u7528ABI2\u3001GLRegion56\u5b57\u8282 |

\u65b0\u589e\u914d\u7f6e `auto_font_style: bool = false`\uff0c\u5c5e\u4e8e\u5916\u89c2\u53c2\u6570\u3002\u539f\u6765\u7684\u624b\u52a8\u5b57\u4f53\u3001\u5b57\u53f7\u548c\u6d41\u5f0f\u884c\u4e3a\u63a5\u53e3\u517c\u5bb9\u3002\u6bcf\u6846\u5b57\u4f53\u5728\u539f\u751f\u6e32\u67d3\u7ebf\u7a0b\u7528\u4e8e\u6d4b\u91cf\u548c\u7ed8\u5236\uff1b\u50cf\u7d20\u98ce\u683c\u5173\u95ed\u5e73\u6ed1\uff0c\u5176\u4f59\u4f7f\u7528 ClearType\u3002Python/Tk \u4e3b\u7ebf\u7a0b\u4e0d\u76f4\u63a5\u6267\u884c OCR\u3002

\u5b57\u5f62\u68c0\u67e5\u4f9d\u636e [GetGlyphIndicesW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getglyphindicesw)\uff0c\u6e32\u67d3\u8d28\u91cf\u4f9d\u636e [CreateFontW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-createfontw)\u3002\u8fd9\u4e9b\u68c0\u67e5\u4e0d\u66ff\u4ee3\u590d\u6742\u6587\u5b57\u6392\u7248\u5f15\u64ce\u3002
'''
en_api='''## 0.01.24 interface additions

| Interface / field | Contract |
|---|---|
| `capture_plan(value)` | None, a legacy `(x,y,w,h)` rectangle or 1–8 non-overlapping integer rectangles; immutable `CapturePlan(bounds,regions)`; rejects bool, overlap and combined dimensions above4096 with ValueError |
| `client_selections(relative,client)` | Clip game-relative selections to the current client and convert to screen coordinates; None when all selections are outside |
| `OcrCore.set_capture_regions(regions)` | Set union-relative rectangles before capture; changes invalidate capture; scope is part of frame-cache identity |
| `prepare_capture_image(image)` | Owned RGB PIL copy; gaps blacked out before OCR and optional Vision upload; source unchanged |
| `_selection_id` | Local boundary identity retained by grouping, anchors and tracking |
| `SourceStyleMatcher.classify(image,line)` | Local source evidence → sans/serif/mono/pixel; at most65536 pixels and96 source characters per box; bounded256-entry cache |
| `TargetFontSelector.choose(style,text)` | Validate target-script samples plus actual characters; `(family,pixel)` or None; at most4096 distinct BMP characters,256 cache entries |
| `set_auto_font_style(enabled,target)` | Boolean flag and target language; configure while stopped; manual choice retained |
| `gl_font_supports(family,text)` | New C export; installed face,1–31 UTF-16 name units,≤4096 text units;1/0 result, conservative rejection of supplementary characters |
| `gl_overlay_styled(ctx,regions,count,rows,row_count,offsets,origins,families,pixel_fonts)` | Additive ABI2; same layout and source rows as anchored rendering, nullable origins for diagnostics, count parallel family names and0/1 pixel flags. Atomic rejection on invalid input. GLRegion remains56 bytes |

New setting: `auto_font_style: bool = false`. Per-box face and antialiasing quality are used consistently for measuring and painting. Pixel style uses unsmoothed rendering. Existing manual font, sizing and stream interfaces remain compatible.

See [GetGlyphIndicesW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getglyphindicesw) and [CreateFontW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-createfontw). Glyph coverage checks do not replace complex-script shaping.
'''
zh_arch='''## 0.01.24 \u7ed3\u6784\u589e\u91cf

```text
nkc_galgame_translator/
  selection_regions.py  Python: CapturePlan\u3001\u533a\u57df\u88c1\u5207\u3001\u906e\u7f69\u3001\u5206\u7ec4\u8fb9\u754c
  font_style.py         Python/Pillow: SourceStyleMatcher\u3001TargetFontSelector
  app.py                Python/Tk: \u8fde\u7eed\u6846\u9009\u3001\u786e\u8ba4/\u64a4\u9500\u3001\u7a97\u53e3\u8eab\u4efd
  ocr.py / vision_core.py Python: \u5355\u5e27\u906e\u7f69\u3001\u9009\u533a\u8fc7\u6ee4\u3001\u6e90\u5b57\u4f53\u5143\u6570\u636e
  pipeline.py / tracking.py Python: \u9009\u533a\u9694\u79bb\u3001\u6700\u65b0\u5e27\u3001\u5e76\u53d1\u7ffb\u8bd1
native/
  core.cpp / core.h     C++17/GDI: \u5b57\u5f62\u8986\u76d6\u9a8c\u8bc1\u3001\u9010\u6846\u5b57\u4f53\u5bfc\u51fa
  fixed_layout.h        C++17/GDI: \u540c\u5b57\u4f53\u6d4b\u91cf\u4e0e\u539f\u884c\u6392\u7248
```

\u4e00\u4e2a\u6355\u83b7\u7ebf\u7a0b\u670d\u52a1\u5168\u90e8\u9009\u533a\uff1b\u5df2\u6709 OCR helper \u548c\u6709\u754c\u7ec6\u5316\u6c60\u7ee7\u7eed\u590d\u7528\uff0c\u4e0d\u6309\u9009\u533a\u589e\u52a0 OCR \u8fdb\u7a0b\u6216\u7ebf\u7a0b\u3002\u5b57\u4f53\u98ce\u683c\u5206\u6790\u5728 OCR \u5de5\u4f5c\u7ebf\u7a0b\uff0c\u9009\u62e9\u5df2\u5b89\u88c5\u76ee\u6807\u5b57\u4f53\u53ca\u6e32\u67d3\u63d0\u4ea4\u5728\u663e\u793a\u8def\u5f84\uff1bGDI \u7ed8\u5236\u4ecd\u7531\u72ec\u7acb\u539f\u751f\u7ebf\u7a0b\u6267\u884c\u3002256 \u9879\u5b57\u4f53\u98ce\u683c/\u8986\u76d6\u7f13\u5b58\u5206\u522b\u6709\u754c\uff0c\u7cbe\u786e\u5e27\u7f13\u5b58\u8fd8\u5305\u542b\u9009\u533a\u548c\u81ea\u52a8\u5b57\u4f53\u5f00\u5173\u3002
'''
en_arch='''## 0.01.24 module additions

```text
nkc_galgame_translator/selection_regions.py  Python: immutable plans, clipping, masks, group boundaries
nkc_galgame_translator/font_style.py         Python/Pillow: SourceStyleMatcher, TargetFontSelector
nkc_galgame_translator/app.py                Python/Tk: repeated selection, confirm/undo, window identity
nkc_galgame_translator/ocr.py, vision_core.py Python: one masked frame, scope filtering, source style
nkc_galgame_translator/pipeline.py, tracking.py Python: selection isolation and concurrent translation
native/core.cpp, core.h          C++17/GDI: coverage checks and per-box font export
native/fixed_layout.h            C++17/GDI: consistent measurement and fixed-row drawing
```

All rectangles share one capture worker, the existing OCR helper and bounded refinement pool. No per-selection OCR processes or extra worker pools are created. Source style analysis runs in the OCR worker; target font choice occurs on the display path and native painting remains on its own thread. Style and coverage caches each hold at most256 entries. Frame cache identity includes selection scope and the automatic-style flag.
'''
zh_flow='''## 0.01.24 \u591a\u533a\u57df\u5de5\u4f5c\u6d41

```mermaid
flowchart TD
 A[\u8fde\u7eed\u62d6\u51fa1\u81f38\u4e2a\u6846] --> B[Enter\u786e\u8ba4 / \u6e38\u620f\u5ba2\u6237\u533a\u76f8\u5bf9\u5750\u6807]
 B --> C[\u5355\u6b21\u6355\u83b7\u9009\u533a\u5916\u63a5\u77e9\u5f62]
 C --> D[\u95f4\u9699\u53d8\u9ed1 / \u5355\u5e27OCR\u4e0e\u5e76\u884c\u7ec6\u5316]
 D --> E[\u9009\u533a\u5185\u8fc7\u6ee4 / \u5404\u533a\u72ec\u7acb\u8bed\u53e5\u56e2\u4e0e\u8ddf\u8e2a]
 D --> F[\u53ef\u9009\u6e90\u5b57\u4f53\u98ce\u683c\u4f30\u8ba1]
 E --> G[\u5e76\u53d1AI\u7ffb\u8bd1 / \u6d41\u5f0f\u4e8b\u4ef6]
 F --> H[\u76ee\u6807\u8bed\u8a00\u4e0e\u5f53\u524d\u5b57\u5f62\u68c0\u67e5]
 G --> H
 H --> I{\u5df2\u5b89\u88c5\u5b57\u4f53\u652f\u6301?}
 I -- \u662f --> J[\u539f\u4f4d\u7f6e / \u539f\u884c\u6392\u7248 / \u6709\u754c\u7f29\u5b57]
 I -- \u5426 --> K[\u4fdd\u7559\u539f\u6587]
```

AI \u56fe\u50cf\u7cbe\u8bfb\u4e5f\u53ea\u63a5\u6536\u9009\u533a\u50cf\u7d20\u4e0e\u9ed1\u8272\u95f4\u9699\uff0c\u53d6\u6d88\u6216\u6539\u53d8\u9009\u533a\u4f1a\u4f7f\u672a\u5b8c\u6210\u7ed3\u679c\u5931\u6548\u3002\u6bcf\u6846\u4f7f\u7528\u81ea\u5df1\u7684\u5b57\u4f53\u98ce\u683c\uff1b\u6d41\u5f0f\u8f93\u51fa\u6cbf\u7528\u539f\u6587\u5b57\u4f53\u62df\u5408\u89c4\u5219\uff0c\u79fb\u52a8\u4ecd\u7531\u539f\u751f\u7a97\u53e3\u951a\u70b9\u8ddf\u968f\u3002
'''
en_flow='''## 0.01.24 multi-region workflow

```mermaid
flowchart TD
 A[Drag1..8 rectangles] --> B[Enter / game-relative selections]
 B --> C[Capture one union frame]
 C --> D[Black gaps / whole-frame OCR and refinement]
 D --> E[Contained lines / isolated grouping and tracking]
 D --> F[Optional source style estimate]
 E --> G[Concurrent AI / stream events]
 F --> H[Target script and actual glyph checks]
 G --> H
 H --> I{Compatible installed font?}
 I -- Yes --> J[Original rows and position / bounded font fitting]
 I -- No --> K[Keep original]
```

Optional AI image reading receives selected pixels with black gaps. Scope changes invalidate pending recognition. Per-box style does not change anchored movement or fixed-source-row layout.
'''
addons={'USER_GUIDE.md':(zh_user,en_user),'CUSTOMER_GUIDE.md':(zh_user,en_user),
        'API.md':(zh_api,en_api),'INPUT_INTERFACES.md':(zh_api,en_api),
        'ARCHITECTURE.md':(zh_arch,en_arch),'WORKFLOWS.md':(zh_flow,en_flow),
        'UI_INTERFACES.md':(zh_user+'\n\u72b6\u6001\u5b57\u6bb5\uff1a`capture_region` \u4fdd\u5b58\u77e9\u5f62\u5143\u7ec4\uff1b`capture_region_target` \u4fdd\u5b58 HWND/PID\u3002Esc \u4e0d\u5199\u5165\u72b6\u6001\uff0cEnter \u539f\u5b50\u63d0\u4ea4\uff1b\u5207\u6362\u76ee\u6807\u540e\u6e05\u9664\u65e7\u9009\u533a\u3002\n',en_user+'\nState: `capture_region` stores rectangle tuples; `capture_region_target` stores HWND/PID. Esc leaves state unchanged; Enter commits together. A changed target clears the old selection.\n'),
        'LOCAL_TRANSLATION.md':('## 0.01.24 \u5916\u89c2\u53c2\u6570\n\n`auto_font_style=false`\uff1a\u53ef\u9009\u7684\u539f\u6587\u76f8\u4f3c\u98ce\u683c\u5339\u914d\uff0c\u4e0e `auto_font_size`\u3001\u5b57\u53f7\u4e0a\u4e0b\u9650\u72ec\u7acb\uff1b\u591a\u533a\u57df\u4e3a\u4f1a\u8bdd\u72b6\u6001\uff0c\u4e0d\u5199 API \u914d\u7f6e\u3002\u65b0\u8bd1\u6587\u4ecd\u7531 AI \u751f\u6210\u3002\n','## 0.01.24 appearance setting\n\n`auto_font_style=false` enables optional source-style approximation independently of size controls. Selections are session state, not API configuration. New translations remain AI-generated.\n'),
        'SECURITY.md':('## 0.01.24 \u533a\u57df\u4e0e\u5b57\u4f53\u8fb9\u754c\n\n\u533a\u57df\u5916\u63a5\u6846\u53ea\u7528\u4e8e\u672c\u673a\u6355\u83b7\u548c\u80cc\u666f\u4fee\u8865\u3002\u9009\u533a\u5916\u95f4\u9699\u5728 OCR \u548c\u53ef\u9009 Vision \u4e0a\u4f20\u524d\u53d8\u9ed1\uff1b\u53ea\u63a5\u53d7\u5b8c\u5168\u5305\u542b\u4e8e\u4e00\u4e2a\u9009\u533a\u7684\u884c\u3002\u5b57\u4f53\u53ea\u9009\u672c\u673a\u5b89\u88c5\u5b57\u4f53\uff0c\u68c0\u67e5\u76ee\u6807\u8bed\u79cd\u53ca\u5b9e\u9645\u5b57\u5f62\uff1b\u4e0d\u4e0b\u8f7d\u5b57\u4f53\u3001\u4e0d\u63a5\u6536\u6e38\u620f\u63d0\u4f9b\u7684\u5b57\u4f53\u8def\u5f84\u3002\u8303\u56f4\u3001\u6570\u91cf\u4e0e\u5b57\u7b26\u7f13\u5b58\u5747\u6709\u754c\u3002\n','## 0.01.24 selection and font boundaries\n\nThe union frame is retained locally for capture/background reconstruction. Gaps are blacked out before OCR or optional Vision upload. Only lines contained by one selection are admitted. Font selection uses installed faces, checks target-script and actual glyph coverage, and downloads no fonts. Geometry, counts and caches are bounded.\n'),
        'DEPENDENCIES.md':('## 0.01.24 \u4f9d\u8d56\u590d\u6838\n\n\u672c\u7248\u672a\u65b0\u589e\u7b2c\u4e09\u65b9\u5305\u6216\u5b57\u4f53\u5305\u3002\u5b57\u4f53\u98ce\u683c\u5206\u6790\u590d\u7528 Pillow13.0.0\uff1b\u5b89\u88c5\u5b57\u4f53\u4e0e\u5b57\u5f62\u68c0\u67e5\u4f7f\u7528 Windows GDI\u3002\u65b0\u589e\u539f\u751f\u5bfc\u51fa\u5df2\u91cd\u65b0\u7f16\u8bd1\uff0c\u4e0d\u80fd\u7528\u65e7 DLL \u4ee3\u66ff\u3002\u5b9e\u9645\u9501\u5b9a\u4f9d\u8d56\u53ca\u8bb8\u53ef\u89c1 DEPENDENCY_MANIFEST.json \u548c THIRD_PARTY_NOTICES.md\u3002\n','## 0.01.24 dependency review\n\nNo new third-party package or font bundle. Style analysis reuses Pillow13.0.0; installed-face and glyph checks use Windows GDI. Rebuild the native DLL for the additive exports. Dependency locks and third-party licenses remain applicable.\n'),
        'RELEASE.md':('## 0.01.24 \u53d1\u5e03\u5e03\u5c40\n\n`delivery/customer/` \u662f\u5ba2\u6237\u8d44\u6599\uff0c`delivery/release/` \u662f\u7a0b\u5e8f\u4e0e\u5bf9\u5e94\u6e90\u7801\u5305\uff0c`trial/nishokuchou-0.01.24-trial/` \u662f\u7a7a\u914d\u7f6e\u53ef\u8fd0\u884c\u7248\uff1b`demo/SpaceRogueClassic/` \u548c\u5f00\u53d1\u76ee\u5f55\u7684 `config/` \u4e3a\u79c1\u4eba\u52a0\u5bc6\u914d\u7f6e\uff0c\u4e0d\u5bf9\u5916\u5206\u53d1\u3002\u6253\u5f00 OPEN_FIRST.html \u67e5\u770b\u5165\u53e3\u3002\u6027\u80fd\u4e3b\u62a5\u544a\u660e\u786e\u6bd4\u8f830.01.15\u4e0e0.01.24\uff1b\u5386\u53f2\u62a5\u544a\u4fdd\u7559\u539f\u7248\u53f7\u3002\u9a8c\u6536\u8ba1\u6570\u4ee5 TEST_REPORT.json \u4e3a\u51c6\u3002\n','## 0.01.24 delivery layout\n\n`delivery/customer/` contains customer material; `delivery/release/` contains program/source archives; `trial/nishokuchou-0.01.24-trial/` is the runnable clean trial. `demo/SpaceRogueClassic/` and development `config/` are private. Open OPEN_FIRST.html. The current report compares0.01.15 with0.01.24; named historical reports retain their original versions. TEST_REPORT.json records actual validation.\n')}

# Current document headings and a compatibility stamp are updated; historical
# measurements and upstream license text keep their original identities.
reviewed=[]
for path in (ROOT/'docs').rglob('*.md'):
    if 'PERFORMANCE_REPORT' in path.name:continue
    english=path.parent.name=='en' or path.name.endswith('.en.md')
    japanese=path.name.endswith('.ja.md')
    text=path.read_text(encoding='utf-8-sig')
    lines=text.splitlines()
    if lines and lines[0].startswith('#'):
        lines[0]=re.sub(r'0\.01\.\d{2}','0.01.24',lines[0])
    text='\n'.join(lines)+'\n'
    stamp=('Compatibility review: 0.01.24 · 18 November2026. Historical sections retain their original version numbers.' if english else '\u5bfe\u5fdc\u7248\u78ba\u8a8d\uff1a0.01.24\u30fb2026\u5e7411\u670818\u65e5\u3002\u904e\u53bb\u306e\u8a18\u9332\u306f\u5143\u306e\u7248\u756a\u53f7\u3092\u4fdd\u6301\u3057\u307e\u3059\u3002' if japanese else '\u9002\u7528\u7248\u672c\uff1a0.01.24 · \u6587\u6863\u590d\u6838\uff1a2026-11-18\u3002\u5386\u53f2\u8bb0\u5f55\u4fdd\u7559\u539f\u7248\u53f7\u3002')
    first,separator,rest=text.partition('\n')
    addon=addons.get(path.name,('',''))[int(english)]
    text=first+'\n\n'+stamp+'\n\n'+addon+'\n'+rest.lstrip()
    text=text.replace('trial/nishokuchou-0.01.23-trial','trial/nishokuchou-0.01.24-trial')
    path.write_text(text,encoding='utf-8');reviewed.append(str(path.relative_to(ROOT)))

# The README introduces current behavior; detailed history stays in CHANGELOG.
for path,english in [(ROOT/'README.md',False),(ROOT/'docs/en/README.md',True)]:
    text=path.read_text(encoding='utf-8')
    anchor='## Placement and streaming' if english else '## \u539f\u4f4d\u6392\u7248'
    tail=text[text.index(anchor):]
    intro=('# Nishokuchou · Real-time game translation0.01.24\n\nRead game text where it appears. Windows10/11 x64.\n\n'+en_user+'\nCurrent performance evidence compares0.01.15 with0.01.24. [Report](../PERFORMANCE_REPORT.html).\n\n' if english else '# \u4e8c\u8272\u8776·\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd10.01.24\n\n\u770b\u61c2\u6e38\u620f\uff0c\u5c31\u5728\u539f\u4f4d\u3002Windows10/11 x64\u3002\n\n'+zh_user+'\n\u5f53\u524d\u6027\u80fd\u62a5\u544a\u4ee50.01.15\u4e3a\u5bf9\u7167\uff0c\u89c1[\u5b9e\u6d4b\u5bf9\u6bd4](docs/PERFORMANCE_REPORT.html)\u3002\n\n')
    path.write_text(intro+tail,encoding='utf-8')
for path,english in [(ROOT/'CHANGELOG.md',False),(ROOT/'docs/en/CHANGELOG.md',True)]:
    original=path.read_text(encoding='utf-8')
    entry=('## 0.01.24 · 18 November2026\n\n- Repeated1–8 region selection with isolated grouping and masked gaps.\n- Optional approximate source font styles with target/actual glyph checks.\n- Report baseline0.01.15; all current manuals, interfaces and diagrams reviewed.\n\n' if english else '## 0.01.24 · 2026-11-18\n\n- \u8fde\u7eed\u5212\u5b9a1–8\u9009\u533a\uff0c\u95f4\u9699\u906e\u7f69\u4e0e\u5206\u533a\u5206\u7ec4\u3001\u8ddf\u8e2a\u3002\n- \u53ef\u9009\u539f\u6587\u5b57\u4f53\u98ce\u683c\u8fd1\u4f3c\u5339\u914d\uff0c\u68c0\u67e5\u76ee\u6807\u8bed\u8a00\u53ca\u5b9e\u9645\u8bd1\u6587\u5b57\u5f62\u3002\n- \u6027\u80fd\u62a5\u544a\u5bf9\u7167\u56fa\u5b9a\u4e3a0.01.15\uff1b\u540c\u6b65\u5168\u90e8\u5f53\u524d\u624b\u518c\u3001\u63a5\u53e3\u4e0e\u56fe\u793a\u3002\n\n')
    path.write_text('# '+('Release history' if english else '\u7248\u672c\u8bb0\u5f55')+'\n\n'+entry+original,encoding='utf-8')
for name in ('build_html_docs.py','build_english_docs.py','build_delivery.py','check_manuals.py'):
    path=ROOT/'tools'/name
    text=path.read_text(encoding='utf-8').replace('0.01.23','0.01.24')
    if name=='build_delivery.py':
        text=text.replace('## Make it yours',en_user+'\n## Make it yours')
    path.write_text(text,encoding='utf-8')
path=ROOT/'nkc_galgame_translator/__init__.py';path.write_text(path.read_text(encoding='utf-8').replace('0.01.23','0.01.24'),encoding='utf-8')
config=ROOT/'config/example.json';values=json.loads(config.read_text(encoding='utf-8-sig'));values['auto_font_style']=False;config.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
update=ROOT/'docs/UPDATE.json';values=json.loads(update.read_text(encoding='utf-8'));values.update(version='0.01.24',previous_version='0.01.23',performance_baseline='0.01.15',documentation_review='2026-11-18',features=['multi_region_selection','source_style_font_matching']);update.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Existing SVGs remain offline, with current region/font stages added in labels.
path=ROOT/'docs/PROJECT_GUIDE.html';text=path.read_text(encoding='utf-8').replace('0.01.23','0.01.24').replace('\u9009\u62e9\u7a97\u53e3\u3001\u8bed\u8a00\u4e0e\u9009\u533a','\u9009\u62e9\u7a97\u53e3\u3001\u8bed\u8a00\u4e0e1–8\u9009\u533a').replace('\u6574\u4f53\u8bc6\u522b\u540e\u5e76\u884c\u7ec6\u5316','\u591a\u533a\u57df\u5355\u5e27\u8bc6\u522b\u540e\u5e76\u884c\u7ec6\u5316').replace('\u7eaf AI \u7ffb\u8bd1\uff0c','\u76f8\u4f3c\u98ce\u683c\u5b57\u4f53\u3001\u76ee\u6807\u5b57\u5f62\u68c0\u67e5\uff0c\u7eaf AI \u7ffb\u8bd1\uff0c');path.write_text(text,encoding='utf-8')
marker.write_text(json.dumps({'version':'0.01.24','reviewed_markdown':reviewed,'unchanged_legal_terms':True},indent=2),encoding='utf-8')
print('Reviewed',len(reviewed),'Markdown documents; updated generators and version metadata.')
