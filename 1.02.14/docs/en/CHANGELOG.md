# 0.01.27 — 2026-11-18

<!-- teacher-review27 -->
## Documentation revision · 2026-11-18T18:36+08:00

Fresh 0.01.15 / 0.01.27 image-to-OCR comparison, separated cache/cold/warm/accuracy scopes, same-image OCR evidence, bilingual 18-chapter manuals and an offline teacher-review portal with a per-surface UI gallery. Real-API observations are independently scoped. No application binary or version change.


## 0.01.27 CUDA recognition and actual fallback

The first-run language page and regular settings share CUDA controls. `cuda_enabled` defaults to true. CUDA is attempted only in **Auto OCR mode** for English, Japanese or Chinese. Explicit Windows / Pixel modes use CPU, as do other languages. Missing components, incompatible hardware, invalid models or failed inference fall back to Windows / Tesseract with actual status. Installed files do not prove GPU execution. A failed OCR instance does not repeatedly retry CUDA; stop and restart after changing settings.

| Setting | Default | Range and meaning |
|---|---|---|
| `cuda_enabled` | `true` | Enable/disable; no automatic component downloads |
| `cuda_quality` | `75` | 0–100, performance to accuracy; linearly adjusts detector input limit with 32-pixel quantization |
| `cuda_memory_mb` | `1024` | 256–16384 MiB inference arena budget; does not force allocation of 1 GiB; runtime/driver overhead is additional |

The detector long-side limit is approximately `768 + 11.52 × cuda_quality`, rounded to a multiple of 32; 75 selects 1632 pixels. Only larger images are downscaled, so settings can be equivalent for small images. The slider is not an accuracy percentage and does not guarantee monotonically better accuracy or speed. The model is PP-OCRv6-small. Consult this version's GPU/dependency results rather than assuming every NVIDIA GPU works.

With optional cloud image refinement enabled, CUDA rows with confidence at least 95 and no rejection marker can proceed directly to translation; other rows remain on the verification path. **95 is a model-score threshold, not a measured 95% accuracy promise.** Local CUDA OCR uploads no image; cloud refinement remains a separate opt-in image-transfer path.
## 0.01.27 Display does not wait for web reference

`TranslationEngine.translate()` reads only completed `ContextAgent.peek(key)` reference and immediately sends a tool-free translation request using current source, supplied context and available history. Only after successful translation and network-slot release does `refresh()` attempt background research. New notes benefit later sentences, never revise an already displayed translation or enter overlay events.

At most one background task and no waiting queue. The key includes game, executable identity, source/target languages and supplied context; 32 cached entries, 900 seconds with a summary and 30 seconds for empty/failed references. Background work shares concurrency, request/token accounting and cancellation, yields to waiting display jobs and does not use the sole slot when concurrency is one. Remaining budget favors translation. Closing cancels transport and joins the background worker.

Research failure cannot discard successful output. Background authentication/balance errors become unavailable with cooldown; errors in display requests still surface normally. `searching` denotes background work; `searched` requires final server-source evidence. Source/history/pages/notes remain untrusted JSON data: no local tools, automatic returned-URL fetches or credentials in prompts.
## 0.01.27 Group fitting and short continuation rows

Continuous body text uses median source-row ink height as a stable reference. In a group of at least three rows with at least two wide body rows forming a majority, a very short continuation or unusually shallow ink row does not alone shrink the whole paragraph. Within one region, overflowing continuation text can move complete clusters into measured spare width on the immediately preceding row: at most 64 candidates, retaining at least one cluster on the continuation. No row rectangle expands. A weak row that still cannot fit preserves original pixels. Text never transfers between regions; ordinary/medium-width long translations still constrain the shared font size.

Streaming paints the prefix fitting the current reference size while retaining cumulative full text; final output triggers group fitting and full-width spacing. Heading, column, source-style/size, fixed-size and explicit-cap boundaries remain. Some weak boxes can retain untranslated source, and a stream tail can wait for final output. This is a rendering fix, not an OCR or semantic-accuracy claim.

No new setting or ABI 2/export-signature change. Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. This version's C++ core requires a new build/audit; the old native audit does not certify its binary.

# 0.01.26 — 18 November 2026

Compact API toolbar, executable-aware game selection and explicit waiting/processing states. Window icon and existing settings/history are retained. Native library and dependencies are unchanged; speed/accuracy evidence remains measured on 0.01.25.

# Release history

## 0.01.25 · 18 November 2026

- Game-translation harness with separate perception, context, translation and display contracts.
- Optional bounded DeepSeek server-side background research, isolated from displayed text.
- Stable reference glyph fitting and shared font sizes for compatible adjacent body-text objects; full-width final spacing remains.
- Quality-first testing now includes NEEDY GIRL OVERDOSE; current reports distinguish OCR from complete translation latency.
- Updated Chinese/English manuals, layered diagrams, interfaces and documented limits. Actual validation is recorded in the release test report.

## 0.01.24 · 18 November2026

- Repeated1–8 region selection with isolated grouping and masked gaps.
- Optional approximate source font styles with target/actual glyph checks.
- Report baseline0.01.15; all current manuals, interfaces and diagrams reviewed.

# Change history

Compatibility review: 0.01.25 · 18 November 2026. Historical sections retain their original version numbers.


## 0.01.23 · Mixed colors and selected rows · 18 November 2026

Documentation correction: the default performance report, Chinese/English performance chapters and customer entry now show the 0.01.23 measurements. The 0.01.15 to 0.01.22 report is retained under explicit `PERFORMANCE_REPORT_0.01.22.*` filenames. Added current-report version checks; synchronized all release, trial and private copies.

Local RGB background-distance normalization supports ordinary text, selected backgrounds and colored text, including near-equal luminance colors. Existing whole-frame detections are retained. Only measured local rows are supplemented, and actual word boxes keep labels separate from prices. The original frame remains unchanged.

A bounded 16 MiB / 64-entry exact-RGB crop cache reuses unchanged recognition without reusing absolute coordinates. Text, color, size and language changes invalidate reuse. No additional OCR threads or game-specific word correction tables were added.

On three Space Rogue Classic screenshots (356 annotated characters), zoned character accuracy changes from 89.61% in 0.01.22 to 95.51% in 0.01.23 (37 to 16 edits). These are image replay results, not general-game or translation-semantic accuracy. New/changed frames have additional processing cost; identical frames retain whole-frame caching. See the [performance report](../PERFORMANCE_REPORT.html).

## 0.01.22 · 18 November 2026

Exact whole-frame OCR cache, in-flight partial sharing, confirmed capture-time settling, 50/80 ms defaults and 8 ms UI polling. Same-PC performance/accuracy report and a separate public trial folder.

## 0.01.21 · 2026-11-17

Parallel full-frame OCR, bounded regional OCR LRU, response/resource presets, 16 ms stream UI, 60-second keep-alive and first-token metrics.

## 0.01.20 · 2026-11-17

Overlays follow game-client movement, including late streamed text; transient move/resize captures retry.


Added desktop screenshot inclusion, fixed/automatic font sizes and range controls, HWND-only OCR capture, and persistent saved-key placeholders.

## 0.01.19 · 2026-11-17

- AI-only new translations; historical dictionaries retained as references.
- Whole-frame OCR followed by parallel ink/separator refinement and column-aware prose groups.
- Opaque Aero backgrounds exclude original ink while preserving source rows.
- Losslessly compressed context events and atomic per-game/pair timestamp indexes.
- Configurable refinement workers/history budgets and a recent translation/context viewer.
- Older release directories remain intact; current verification is reported separately.

# Change history

## 0.01.18 · 2026-11-16

- Preserve physical source rows/footprints, start from source font size, distribute final character spacing and shrink long output inside the original bounds. Impossible fits preserve source pixels. Add gl_overlay_fixed without changing GLRegion ABI 2.

- Keep table/list entries at independent positions when local layout evidence supports them; retain numeric columns as source pixels and layout evidence.
- Separate distant cells using actual recognized geometry, keeping each overlay inside its own source bounds instead of estimating positions from string length.
- Update both manuals, structure/workflow diagrams and granular interfaces; current verification is recorded in TEST_REPORT.json.



## 0.01.17 · 2026-11-16

- Added bounded pre-translation checks for numeric/symbol text, isolated keys, explicit HUD codes and repeated-glyph noise such as `Siiius`, without rejecting normal uppercase menus or unknown names.
- Unchanged raw output does not receive a decorated overlay; final identity results clear previous coverage and block late partial output.
- Confirm whole coverage rectangles together, including persistent tiny shifts. Preserve unchanged published OCR rows during image-reading waits only with exact current pixel/geometry/color evidence.
- Route low-color colored HUDs through automatic pixel recognition while honoring the selected OCR mode. Native painting reuses a bitmap and commits background/text together.
- Updated bilingual manuals, diagrams and interfaces. Current test/release evidence is recorded separately in TEST_REPORT.json.

## 0.01.16 · 2026-11-15

- Separate continuous-prose OCR row endings from translation presentation. Locally evidenced paragraphs reflow display text while independent paragraphs, lists and buttons retain boundaries; source strings and dictionary/cache identities remain unchanged.
- Correct premature wrapping at an earlier space in mixed Latin/CJK output, with common punctuation, bracket and UTF-16 boundary handling. Overlay rectangles do not expand; measurement and drawing share font metrics.
- Apply the same display path to cached and cumulative streamed translations. Retain suspect-OCR source-pixel preservation and the same-revision no-enlargement font rule.
- Update Chinese and English manuals, structure/workflow diagrams and interface specifications. This version's TEST_REPORT.json records regression scope, native rebuild and controlled layout evidence; fixtures are not presented as a real-game online translation run.

## 0.01.15 · 2026-11-15

- Added conservative local English UI OCR checks: multiple strong misreading signals preserve the original game pixels instead of drawing the faulty recognized string.
- Rejected text does not reach translation-cache lookup, the translation LLM, learning progress or dictionary writes. Other accepted boxes continue; later acceptable recognition can resume translation.
- Quality state prevents stale overlays and late streaming chunks from returning over rejected text. The 0.01.14 unlimited-request option and existing modes remain.
- Updated the Chinese and English manuals, architecture, workflows and granular API documentation. Current validation is recorded in TEST_REPORT.json.

## 0.01.14 · 15 November 2026

- Added an independent Unlimited API requests switch. It removes the per-engine request-count cap while translation, image-reading and retry attempts continue to be counted. Concurrency, timeouts, input/output bounds and offline rules remain active.
- `unlimited_requests` is a strict Boolean and defaults to false in public builds. Turning it off restores the saved `max_requests` limit; zero still forbids new API requests.
- `get_stats().requests_remaining` is `None` (JSON `null`) while unlimited, alongside the new `unlimited_requests` state. The 512-success initial collection target is independent.
- Stop translation and wait for outstanding work before saving. Updated all three interface languages and the complete Chinese/English manuals, contracts and workflows. Current validation is recorded in TEST_REPORT.json.

## 0.01.13 · 15 November 2026

- Smart mixed routing is enabled by default after collection: reuse exact dictionary/cache results at any length, then use local rules for eligible short single-line text; complex text and local misses go to the LLM. The short-text limit defaults to 32 characters and is adjustable from 1 to 256. Local-only mode never goes online; explicit aggressive mode and active automatic collection take precedence.

- Added Auto/Windows/Pixel local OCR on one fixed BGRA frame via gl_ocr_bgra. AI stability follows local text-anchor pixel signatures, so animation outside text does not repeatedly cancel recognition.
- Continuous pixel-font paragraphs no longer split every four rows. New limits are 32 rows / 4000 characters / 4096 pixels; hard breaks, row-sized fonts and visual boundaries remain, while compact button runs stay independent.
- Added automatic initial collection for a new game, default 512 complete successes and zero to disable. Persistent progress and concurrency reservations do not replace request budgets. Explicit continuous aggressive mode takes priority.
- Added optional AI image reading, off by default, sending only the selected game-region image and recognized text to the active slot under the shared request budget. Three disclaimers move to 2026-11-15-r3.
- Added real pixel-image and paragraph regression evidence. Only this version's TEST_REPORT.json establishes current acceptance; historical totals are not reused.

## 0.01.12 · 15 November 2026

- Added installed-system-font selection for overlays. Measurement, wrapping and rendering use the same font family; streamed output retains the existing size-stability rules.
- Source-language labels and outer brackets are independently configurable. Defaults preserve `[英语：translation]`. The mixed-language-only option shows source labels only when the visible objects contain at least two distinct foreign source-language bases after excluding the target language.
- Label changes reformat already available text, including when objects appear/disappear, without another LLM request or changes to object IDs, revisions, dictionaries or cache keys.
- Added Chinese, English and Japanese application interfaces. First-run language selection precedes agreement/API guidance; supported Windows display language supplies the initial choice and explicit selection is saved. Later language saves refresh the interface immediately.
- Added a complete English disclaimer plus original MIT text and a complete offline English manual. Chinese and English manuals include structure/workflow SVGs, granular API contracts, dependencies and license material.
- Added `gl_set_font`, `NativeCore.set_overlay_font` and `OcrCore` forwarding. GLRegion remains ABI 2/56 bytes but requires the new matching DLL export. Snapshots report configured and actual font faces.
- Appearance settings are saved while translation is stopped and apply on the next screen session. Appearance-only saves retain the engine and session request budget. New measured acceptance results belong to this version's TEST_REPORT.json; old test counts are not reused as a pass result.

## 0.01.11 · 14 November 2026

Improved first-window/API/manual-translation/dictionary workflows and busy-state handling. Separated fixed system instructions from JSON user data; bounded HTTP/SSE, OCR IPC, dictionary and native inputs. Bound DPAPI credentials to complete endpoints, rejected unsupported local/device paths and restricted OCR input to BMP/raw RGB. Disabled inherited environment proxies and HTTP redirects. Added sanitized startup diagnostics and native hardening flags.

Updated the isolated runtime and dependency baseline, wheel hash locks, software inventory, original notices, source acquisition material and release verification. Fixed Tk9/WinRT language-enumeration MTA lifetime and OCR model loading in Unicode paths. Public packages excluded personal game recordings and one-time shutdown scripts. Completed offline documentation and a local-dictionary UI demo; that historical fixture did not call a real API.

## 0.01.10

Added the Settings page, configurable concurrency from 1 to 16, a separate shared dictionary, CSV/TSV/JSON/TMX import, number templates and complete phrase composition. Aggressive mode requests the LLM for each new translation and learns successful results. This release remains in its own folder.

Earlier evidence belongs to its corresponding release. Memory injection is absent in this release, and old screenshots are not substituted for new acceptance evidence.
