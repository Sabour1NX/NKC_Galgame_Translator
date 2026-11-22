# NKC_Galgame_Translator baseline framework 0.01.15 versus tuned framework 0.01.22

Measured 18 November 2026. Baseline means the oldest retained product build before this response-tuning work, not an untouched third-party framework. Same CPython 3.14.10, Tkinter/Tk 9.0, Tcl 9.0.4, C++17/Win32/GDI/WinRT, Tesseract 5.5.4/tesserocr 2.13.0, httpx 0.28.1, Pillow 13.0.0 and English model files. Pixel OCR only; no Windows OCR or real LLM benchmark. No competitor measurements.

## Measured changes

| Revisiting an identical image | Baseline ms | Tuned ms | Equivalent speed ratio | Equivalent speed increase |
|---|---:|---:|---:|---:|
| 剧情页 | 360.791 | 9.440 | 38.22× | +3721.9% |
| 状态菜单 | 86.569 | 7.713 | 11.22× | +1022.4% |
| 货物价格表 | 137.993 | 2.733 | 50.49× | +4949.1% |

Each OCR case has 12 A→B→A measurements. The headline maximum is the cargo-table cache-hit case, 50.5× / +4949.1%. This is OCR result retrieval only, not live translation throughput or game FPS. Ratio = old latency / new latency; increase = (ratio−1)×100%. The raw JSON includes all timings, cold single observations and sampled memory.

Synthetic first callback: 703.87→185.45 ms, +279.5% equivalent speed, 73.7% less time. Fixed 80 ms provider, zero-cost OCR, no real network/rendering. Shared follower partial: 497.88→82.63 ms; provider emits at 80 ms and completes 400 ms later. The old engine's local paths are disabled with a fresh database to compare network misses, not local-cache response.

Region-aligned character accuracy: 83.99%→89.61% (+5.62 percentage points); 57→37 edits across 356 normalized reference characters. Error count falls 35.1%. Improvement comes from cargo column separation; story and status accuracy are unchanged. This includes spatial grouping/reading order, not merely glyph classification or translation meaning. The interactive report displays original screenshots and actual OCR boxes, including remaining misses.

## Tuning techniques

Parallel whole-frame AUTO/SPARSE discovery with isolated engines and deterministic merge; measured columns/ink before bounded regional refinement; exact frame cache (16 entries/128 MiB accounted budget) and 256 crop refinements; capture/settle 250/450→50/80 ms; confirmed capture-time credit; streaming UI 8 ms; connection reuse and in-flight partial sharing. Historical translation records remain context in the AI-only current version.

## Limits and earlier mistakes

Changed-frame status OCR is slower in 0.01.22. Increasing regional workers from 4 to 8 makes cargo recognition about 1.7% slower and sampled memory about 35% higher, while story is slightly faster. All 1/2/4/8-worker text/box hashes match. This does not demonstrate that more threads degrade current recognition content.

Earlier user feedback concerned fragmented text, unstable layout and scene-specific rule tuning. We describe this as scenario-adaptation overfitting risk; no model was retrained and no cross-game holdout evaluation proves statistical model overfitting. Whole-frame-first discovery, bounded pools and stable ordering address fragmentation. Thread study: 6 measured runs per scene after warmup, refinement cache cleared, helper-only timings excluding IPC/postprocessing. Three screenshots from one game are not a general-game accuracy claim.

Public evidence now includes requested Space Rogue screenshots, but no game program, credentials or private translation records. See [interactive report](../PERFORMANCE_REPORT_0.01.22.html) and [raw measurements](../PERFORMANCE_REPORT_0.01.22.json).
