# NKC_Galgame_Translator 0.01.27 · Fresh performance evidence

**A better experience. Less waiting.**

Fresh comparison with 0.01.15, measured 2026-11-18T18:29:09+0800. These are image-to-OcrCore results, not translation latency.

## Scope and protocol

Three alternating-order rounds; each scene/release uses a fresh worker, three cold samples total and 15 samples per warm path. Cold includes constructor/native/helper/model initialization; excludes Python startup and file loading; OS file cache is not flushed. Changed background means one corner pixel changes and text stays unchanged: whole-frame misses are asserted, subregion caches remain eligible. Cache revisits are separate.

Actual auto routing: .15 default CPU paths; .27 CUDA enabled at quality 75, 1024 MiB, with classic English pixel-frame CPU priority. This is a product/system comparison, not an isolated GPU-vs-CPU algorithm experiment. UI capture ran concurrently; the NEEDY cold maximum of 21.886 s is retained, without causal attribution.

| Scene | Version / backend | Cold median ms | Changed-background median ms | Identical revisit ms | Character accuracy |
|---|---|---:|---:|---:|---:|
| spacerogue-game.png | 0.01.15 / portable-tesseract-pixel | 615.119 | 321.146 | 327.417 | 98.347% |
| spacerogue-game.png | 0.01.27 / portable-tesseract-pixel | 654.230 | 317.192 | 7.716 | 98.347% |
| status.png | 0.01.15 / windows-ocr | 40.032 | 23.722 | 23.721 | 40.625% |
| status.png | 0.01.27 / portable-tesseract-pixel | 546.764 | 205.891 | 7.504 | 100.000% |
| cargo.png | 0.01.15 / portable-tesseract-pixel | 338.523 | 123.446 | 123.027 | 47.561% |
| cargo.png | 0.01.27 / portable-tesseract-pixel | 451.943 | 123.234 | 2.561 | 85.366% |
| needy-caution-full.png | 0.01.15 / portable-tesseract | 517.906 | 257.437 | 257.287 | 1.613% |
| needy-caution-full.png | 0.01.27 / rapidocr-cuda | 3286.928 | 226.868 | 20.321 | 98.387% |

## Accuracy and tradeoffs

Accuracy is 100 × (1 − Levenshtein edits / labelled characters), with NFKC, whitespace removal and curly-quote normalization; case remains significant. It measures source transcription, not translation meaning. Space Rogue (356 characters) default-auto changes 81.461% → 95.506%; the separate forced-pixel .15 control is 83.989%. NEEDY (248 characters): .15 auto 1.613%, .27 CPU-only control 57.661%, .27 CUDA auto 98.387%. The .15 Windows Japanese OCR control fails because that language is absent; failure is not scored as zero accuracy.

More accurate paths can cost more: Status changed-background median rises from 23.722 to 205.891 ms and cold CUDA initialization is slower. The story scene keeps 98.347% accuracy. Cache speedups and single quality settings are not universal performance promises.

## Real API callbacks and unmeasured display

The offline OCR comparison makes zero API requests and excludes capture, cloud transcription, translation, SSE and presentation. Fresh real-API observations are scoped separately. Historical .25 observations or simulated SSE are not substituted.

The complete Space Rogue source image is loaded before timing and sent through each release's actual pixel OCR. A declared test adapter selects only the left story region [0,70,450,440] for tracking and a real streaming API request. The image is not cropped. Timing starts immediately before pipeline.start and ends when translation callbacks are consumed from the event queue. No visible window or overlay is used; capture, painting, web context, AI vision and DWM/monitor presentation are excluded. Native-paint times are null, not zero.

| Pair | Version | Result | First callback ms | Final callback ms | Requests |
|---|---|---|---:|---:|---:|
| 1 | 0.01.15 | complete | 2179.033 | 2561.680 | 1 |
| 1 | 0.01.27 | complete | 1202.929 | 1618.103 | 1 |
| 2 | 0.01.27 | complete | 1308.167 | 1689.562 | 1 |
| 2 | 0.01.15 | complete | 1628.940 | 2011.547 | 1 |
| 3 | 0.01.15 | complete | 1529.235 | 1863.335 | 1 |
| 3 | 0.01.27 | complete | 1489.160 | 1982.674 | 1 |

Release defaults for stabilization and polling are retained. Observation tick is 40ms in .15 and 16ms in .27. Prompts also differ (229 versus 258 input tokens). Sequential provider/network variation is uncontrolled; these few pairs are descriptive, not a statistically established provider speedup. Pair3 final callback is slower in .27: 1982.674ms versus 1863.335ms. This is a fixed-image real-API callback test, not native painting or a running-game overlay certification.

| Version | Poll interval ms | Settle ms | Observation tick ms | Model |
|---|---:|---:|---:|---|
| 0.01.15 | 250 | 450 | 40 | deepseek-flash |
| 0.01.27 | 50 | 80 | 16 | deepseek-flash |

Total actual session requests: 6.

All six source-text hashes match. Provider/model response variation and version-specific prompts remain part of this system-level observation.

| Pair / version | Prompt tokens | Completion tokens |
|---|---:|---:|
| 1 / 0.01.15 | 229 | 39 |
| 1 / 0.01.27 | 258 | 39 |
| 2 / 0.01.27 | 258 | 39 |
| 2 / 0.01.15 | 229 | 39 |
| 3 / 0.01.15 | 229 | 39 |
| 3 / 0.01.27 | 258 | 34 |


## GPU controls and limits

Quality 0–100 (default 75) sets the detector resolution cap, quantized to 32 pixels; small images may be equivalent and accuracy is not monotonic. Memory 256–16384 MiB (default 1024) budgets detector/recognizer arenas, not all process/driver allocations. Auto supports CUDA en/ja/zh with CPU priority for classic English pixel frames; manual Windows/Pixel modes stay on CPU. A model score of 95 is not a measured 95% accuracy promise.

[Full plots, distributions and same-image OCR evidence](../PERFORMANCE_REPORT.en.html)

[Teacher review portal](../teacher-review27/index.html)
