# NKC_Galgame_Translator 0.01.27 · Performance and recognition report

## 0.01.27 Separate measured CUDA OCR

This is a local OCR experiment on **one original fixed NEEDY GIRL OVERDOSE image**, `needy-caution-full.png`, nine body rows and 248 manually annotated characters. NVIDIA GeForce RTX 3070 (8 GiB), driver 617.42, PP-OCRv6-small, 1024 MiB arena budget, five warm rounds per setting, no cache/API. Profiling verifies 190 detector / 181 recognizer CUDA kernel events, not only provider names.

| Slider | Warm client median | Helper OCR median | Character accuracy | Edit differences |
|---|---:|---:|---:|---:|
| 0 | 135.433 ms | 113.767 ms | 97.581% | 6 / 248 |
| 75 | 210.820 ms | 189.260 ms | 98.387% | 4 / 248 |
| 100 | 242.650 ms | 220.524 ms | 96.774% | 8 / 248 |

Client time includes BMP writing, IPC and helper OCR, **excluding capture, translation requests, overlay and monitor presentation**. It is not 135–243ms end-to-end game translation. Approximately 3.23–3.31-second cold starts belong to the other window image run first, `needy-window-original25.png`; do not mix them with this table's warm rounds or attach unsupported accuracy to that image.

On the same 248-character material, 0.01.25 pure local OCR scored 57.661%; the 27 default scores 98.387%, a 40.726-percentage-point increase. The older 25 cloud-AI verified 100% result used a different network/cost/latency path; it is not a claim of 100% local CUDA accuracy. NFKC/whitespace-normalized edit distance measures transcription only, not Chinese translation meaning or all-game accuracy.

Higher settings are not monotonically more accurate: 100 scores below 75 here. A separate original Space Rogue image scores only 88.017% on GPU at 75, below its specialized pixel CPU route, so Auto prioritizes Pixel CPU for detected classic English pixel frames. Arena budget is not a total-process hard cap; nvidia-smi samples desktop-wide memory. End-to-end speed requires separate measurement.

## 0.01.27 Native font replay: separate display validation

Replay the saved 0.01.25 NEEDY nine-row geometry and the same translation through real GDI, composited using actual window-region masks on a flat source-colored panel. Version 0.01.26 uses 14px; 0.01.27 uses 19px. All nine rows draw and both retain 184 UTF-16 units. One cluster from the tiny continuation moves into measured spare width on the preceding row, without expanding row rectangles or moving text between separate objects.

This is native rendering of saved data, **not a running-game screenshot or evidence of better OCR, translation accuracy or latency**. 14px/19px denote GDI font size, not visible ink height. The focused GDI regression batch passed 66 tests; full acceptance remains in TEST_REPORT.json. Sources: `reports/font27-replay.json`, `reports/font27-replay-comparison.png`, `reports/font27-tests.log`.

## 0.01.27 Separate scheduling simulation, not live performance

`reports/context-latency27.json` uses httpx MockTransport and three fresh-engine samples per version: simulated reference delay 300ms and display delay 15ms. Median first display callback changes from **318.019ms** in 0.01.26 to **16.610ms** in 0.01.27. Order changes from context→display to display→context, with two accounted requests including one context request in both. No network, real API or game UI is used. This does not measure real OCR, GPU, network or end-to-end game latency.

The historical real-API, screenshot-accuracy and live-game measurements below remain 0.01.25 / 0.01.15 results. The 0.01.25 ten-second first output included both vision refinement and web context; the entire delay cannot be attributed to search. Consult final TEST_REPORT.json for this version's native/GPU and full regression scope; partial test counts are not full acceptance.

> Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

**A better experience. Less waiting.**

2026-11-18 · Comparison: this project’s 0.01.15 earlier baseline → 0.01.25 current framework. No commercial competitors were benchmarked. The baseline is an earlier application implementation, not raw third-party component performance.

[Interactive charts, original OCR frames and typography evidence](../PERFORMANCE_REPORT.en.html)

## Actual API and native-submission latency

Same machine and static original Space Rogue frame, fresh process and empty database per run, deepseek-flash, three sequential old/new pairs and 12 actual API requests. Each keeps its scheduling defaults: earlier 250ms polling/450ms settling, current 50/80ms.

| Metric / n=3 per version | 0.01.15 | 0.01.25 | Observed median time reduction |
|---|---:|---:|---:|
| First native submission | 1.815 s | 1.434 s | 21.0% |
| All final translations submitted | 2.430 s | 1.934 s | 20.4% |

| Pair | First native submission: 0.01.15 → 0.01.25 | All final submissions: 0.01.15 → 0.01.25 |
|---|---:|---:|
| 1 | 1.863 → 1.994 s | 2.430 → 2.495 s |
| 2 | 1.815 → 1.303 s | 2.236 → 1.912 s |
| 3 | 1.770 → 1.434 s | 2.433 → 1.934 s |

The current version is slower in the first pair, and all successful samples are retained. Network/provider load and OCR/output text are uncontrolled; n=3 does not support p95 or a fixed-speedup claim. Median first OCR readiness is **0.540 → 0.661 s**; it includes first helper-process and coordination overhead, not only the OCR function.

Measured path: fixed original pixels already in memory → OCR/tracking/settling → actual streamed API → native GDI paint completion. Excludes screen capture, reconstruction from captured backgrounds, game foreground behavior, DWM composition, monitor scanout and web context. This is not screen-to-monitor latency. The failed e2e-baseline15-a.json probe has no confirmed paint and is excluded from successful samples.

## Recognition accuracy: three identical original frames

**83.99% → 95.51%** · **+11.52 percentage points** · 356 annotated characters; edit differences **57 → 16**。

| Scene | Zoned character accuracy | Edit differences |
|---|---:|---:|
| Cargo price table | 47.56% → 85.37% | 43 → 12 |
| Status menu | 68.75% → 100.00% | 10 → 0 |
| Storyline | 98.35% → 98.35% | 4 → 4 |

The compare22.py manual-zone method is retained: 100×(1−Levenshtein edit distance/reference characters), NFKC, whitespace removal, curly-quote normalization, case retained and (y,x) order. This is not localization IoU, semantic translation accuracy or all-game success. The status menu improves from 68.75% to 100%, a gain of 31.25 percentage points; storyline accuracy does not improve on these annotations. Errors are retained.

## Single Japanese frame: visual review

For nine body rows / 248 characters in one original NEEDY GIRL OVERDOSE frame: 0.01.15 local 1.61% → 0.01.25 local 57.66%; the current saved AI transcription has zero edit differences on these 248 characters (100%). This evaluates source transcription, not 100% semantic Chinese translation accuracy or a rate for arbitrary games. It is separate from the English three-frame set. Report generation makes no new API requests.

## Typography and Harness separation

In the current synthetic native GDI regression, four neighboring body rows are all 29px, with zero font-size spread and all source-box fit checks passing. This is not a game frame, and no equivalent 0.01.15 font comparison is provided. Neighboring body text with similar source heights shares a size group; original boxes/rows and adjustable spacing are preserved, with consistent shrinking within configured bounds.

The Harness orchestrates recognition, object revisions, cancellation, budgets and in-place display; models handle understanding and translation. ContextAgent is a restricted background-understanding subtask with optional DeepSeek server-side search. Bounded summaries, sources and execution status inform context. The display layer uses a separate translation-only stream, excluding reasoning, tool records and search citations. Web/history content is untrusted; no arbitrary filesystem, shell or URL-fetch tools are exposed. Context shares budgets/concurrency/token statistics, with caching and timeouts.

Quality assistance adds requests and waiting. The latency comparison disables web context and does not represent every assistance feature enabled. Public defaults leave web context off; settings allow changing it.


## Live windowed game: one quality-assisted sample

Actual NEEDY GIRL OVERDOSE capture + local OCR + AI image review + web context + translation: first native submission **10.172 s**; final narrative submission **10.822 s**. A separate live screenshot confirms visible translations with Japanese removed: nine body rows at 14px, heading at 19px and Cancel at 16px retain their source hierarchy. One search in the latest context subtask, two across the session; actual status searched.

This single quality-assisted run exceeds 10 seconds and is separate from the three static English pairs; the 1.434-second median does not apply. Timing ends at native submission, not monitor presentation. The demo uses windowed mode; exclusive-fullscreen compatibility depends on the game and system.


## Named components and changes

CPython3.14.10/Tk9.0: Harness scheduling, deduplication, cancellation and layers; Tesseract5.5.4/tesserocr2.13.0/Pillow13.0.0: whole-frame structure, local RGB/multicolor recognition, columns and source-pixel anchors; HTTPX0.28.1/DeepSeek-compatible API: bounded SSE and shared budgets; C++17/Win32/GDI: peer font size, spacing and buffered/reused drawing; SQLite/zlib: translation and compressed-context archive. Each version uses its own implementation, native DLL and scheduling defaults; this is not raw third-party framework benchmarking.

Earlier excessive OCR threading and fine-grained splitting could fragment phrases, increase scheduling costs and over-specialize rules to a few pages. This is described as scene-specific over-tuning / heuristic-overfitting risk; no training/validation statistics establish model overfitting. Current processing preserves whole-frame structure, then uses bounded concurrency for defined objects.

## Reproduction and evidence

Run from the release root: `vendor/python/python.exe tools/build_quality_report25.py`。

The generator only reads saved evidence and does not contact APIs. Source manifests, hashes, paired samples and OCR boxes are in the report JSON. Optional live original/translated screenshots require explicit --game-before / --game-after arguments; unconfirmed exclusive-fullscreen overlays must not be presented as visible translations.
