# 0.01.27 Separate measured CUDA OCR

This is a local OCR experiment on **one original fixed NEEDY GIRL OVERDOSE image**, `needy-caution-full.png`, nine body rows and 248 manually annotated characters. NVIDIA GeForce RTX 3070 (8 GiB), driver 617.42, PP-OCRv6-small, 1024 MiB arena budget, five warm rounds per setting, no cache/API. Profiling verifies 190 detector / 181 recognizer CUDA kernel events, not only provider names.

| Slider | Warm client median | Helper OCR median | Character accuracy | Edit differences |
|---|---:|---:|---:|---:|
| 0 | 135.433 ms | 113.767 ms | 97.581% | 6 / 248 |
| 75 | 210.820 ms | 189.260 ms | 98.387% | 4 / 248 |
| 100 | 242.650 ms | 220.524 ms | 96.774% | 8 / 248 |

Client time includes BMP writing, IPC and helper OCR, **excluding capture, translation requests, overlay and monitor presentation**. It is not 135–243ms end-to-end game translation. Approximately 3.23–3.31-second cold starts belong to the other window image run first, `needy-window-original25.png`; do not mix them with this table's warm rounds or attach unsupported accuracy to that image.

On the same 248-character material, 0.01.25 pure local OCR scored 57.661%; the 27 default scores 98.387%, a 40.726-percentage-point increase. The older 25 cloud-AI verified 100% result used a different network/cost/latency path; it is not a claim of 100% local CUDA accuracy. NFKC/whitespace-normalized edit distance measures transcription only, not Chinese translation meaning or all-game accuracy.

Higher settings are not monotonically more accurate: 100 scores below 75 here. A separate original Space Rogue image scores only 88.017% on GPU at 75, below its specialized pixel CPU route, so Auto prioritizes Pixel CPU for detected classic English pixel frames. Arena budget is not a total-process hard cap; nvidia-smi samples desktop-wide memory. End-to-end speed requires separate measurement.

