# Settings and compressed context archives · 0.01.27

## 0.01.27 CUDA recognition and actual fallback

The first-run language page and regular settings share CUDA controls. `cuda_enabled` defaults to true. CUDA is attempted only in **Auto OCR mode** for English, Japanese or Chinese. Explicit Windows / Pixel modes use CPU. Auto also prioritizes the CPU Pixel route for detected classic English pixel frames when the portable engine is available (`pixel_priority`); other languages use existing local OCR. Missing components, incompatible hardware, invalid models or failed inference fall back to Windows / Tesseract with actual status. Installed files do not prove GPU execution. A failed OCR instance does not repeatedly retry CUDA; stop and restart after changing settings.

| Setting | Default | Range and meaning |
|---|---|---|
| `cuda_enabled` | `true` | Enable/disable; no automatic component downloads |
| `cuda_quality` | `75` | 0–100, performance to accuracy; linearly adjusts detector input limit with 32-pixel quantization |
| `cuda_memory_mb` | `1024` | 256–16384 MiB inference arena budget; does not force allocation of 1 GiB; runtime/driver overhead is additional |

The detector long-side limit is approximately `768 + 11.52 × cuda_quality`, rounded to a multiple of 32; 75 selects 1632 pixels. Only larger images are downscaled, so settings can be equivalent for small images. The slider is not an accuracy percentage and does not guarantee monotonically better accuracy or speed. The model is PP-OCRv6-small. Consult this version's GPU/dependency results rather than assuming every NVIDIA GPU works.

With optional cloud image refinement enabled, CUDA rows with confidence at least 95 and no rejection marker can proceed directly to translation; other rows remain on the verification path. **95 is a model-score threshold, not a measured 95% accuracy promise.** Local CUDA OCR uploads no image; cloud refinement remains a separate opt-in image-transfer path.

Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

## 0.01.27 context boundary

The optional background context layer uses the single DeepSeek server-side search tool; display translation requests have no tools and do not wait for new search. Both layers share request/concurrency/token accounting. Source text, excerpts, pages and notes remain untrusted. Returned links are never fetched by the client and cannot change source geometry. See [CONTEXT_AGENT.md](CONTEXT_AGENT.md) for exact payload, metadata, timeout and cache contracts.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## 0.01.27 appearance setting

`auto_font_style=false` enables optional source-style approximation independently of size controls. Selections are session state, not API configuration. New translations remain AI-generated.

The historical filename is retained for links. Translation generation is AI-only; local OCR, input gates and record browsing remain.

## Numeric settings

| Key | Range | Default |
|---|---|---|
| `context_max_chars` | 512–16000 | 6000 |
| `context_history_records` | 1–64 | 24 |
| `ocr_refine_workers` | 1–8 | 4 |
| `vision_interval_ms` | 1000–60000 | 3000 |
| `translation_workers` | 1–16 | 8 |
| `tracking_workers` | 1–4 | 2 |
| `max_tracked_objects` | 1–32 | 32 |
| `capture_interval_ms` | 50–2000 | 50 |
| `settle_ms` | 0–3000 | 80 |
| `track_missing_frames` | 0–30 | 10 |
| `ocr_min_confidence` | 0–100 | 55 |
| `max_requests` | 0–10000 | 80 |
| `request_timeout` | 1–120 | 30 |
| `max_retries` | 0–2 | 1 |
| `max_output_tokens` | 32–4096 | 512 |
| `max_input_chars` | 64–16000 | 4000 |

Integer settings reject bool, floats, NaN and infinity; control strings accept at most six decimal digits. Booleans require actual bool values. `max_concurrency` follows `translation_workers`. Font families require 1–31 UTF-16 units without controls; interface languages are zh-CN/en/ja and OCR modes auto/native/pixel.

## Storage and prompt budgets

`ContextArchive` stores JSON events of at most 1MiB using lossless zlib level 6 in `ai_context_events(id,scope_key,created_at,payload,raw_bytes)`, indexed by scope and descending ID. Corrupt records are skipped without overwriting them; decompression is bounded to 1MiB and rejects trailing data. History queries allow 1–64 records, default 24. Prompt limits do not truncate stored events.

Model reference JSON contains `kind`, `user_context`, `terms`, `recent_translations`; the complete serialized string stays within `context_max_chars`. At most 32 matched terms use 256-character fields; history source/result excerpts use 512 characters and context 200. Stored `prompt_context` is not recursively fed back. This combines lossless storage compression with bounded extractive selection, not semantic AI summarization.

After success, `data/contexts/<scope_id>/updated.json` atomically updates schema, scope_id, records, updated_at, raw_bytes, compressed_bytes, prompt_max_chars, compression, database, table and timezone. It contains no source/result text or key; SQLite contains the actual records. Compressed history is not encrypted: compression is not confidentiality.

## 0.01.22 · Faster response · 18 November 2026

Choose **Faster response** at the top of Settings, save, then restart translation. New installations use these defaults. Existing custom settings survive upgrades; the private Space Rogue demo explicitly applies this preset.

| Setting | Faster response (new default) | Balanced resources |
|---|---:|---:|
| Capture interval | 50 ms | 250 ms |
| Text settling | 80 ms | 450 ms |
| Translation workers | 8 | 4 |
| Regional OCR workers | 4 | 2 |
| Missing frames retained | 10 | 2 |

Nominal miss retention remains 500 ms; CPU-bound frame time changes the actual duration. Each field remains adjustable. Increase settling for typewriter dialogue to avoid extra intermediate requests, or lower concurrency if the provider returns 429. Request budgets are independent of presets.

Pixel mode scans the same whole frame with isolated AUTO and SPARSE_TEXT engines concurrently. Results always merge in primary/supplemental order before regional refinement. A 256-entry cache reuses refinement text only when crop pixels, dimensions, language, raw text and confidence match. Current-frame coordinates always win; changed evidence invalidates the entry and failed reads are never cached. This is an OCR cache, not local translation generation.

The UI consumes stream events every 8 ms while active and every 80 ms when idle. Worker threads never touch Tk. Idle HTTP connections are retained for up to 60 seconds, with redirects and environment proxies still disabled. Servers may close them sooner; no fixed internet latency is promised.

See the [performance report](PERFORMANCE_REPORT.md) for measurements, cold-start costs and measurement boundaries. Source-row fitting, click-through overlays, movement tracking and stale-result rejection remain in place.
