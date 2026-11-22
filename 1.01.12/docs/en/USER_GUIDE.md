# User guide · 0.01.27

## 0.01.27 Group fitting and short continuation rows

Continuous body text uses median source-row ink height as a stable reference. In a group of at least three rows with at least two wide body rows forming a majority, a very short continuation or unusually shallow ink row does not alone shrink the whole paragraph. Within one region, overflowing continuation text can move complete clusters into measured spare width on the immediately preceding row: at most 64 candidates, retaining at least one cluster on the continuation. No row rectangle expands. A weak row that still cannot fit preserves original pixels. Text never transfers between regions; ordinary/medium-width long translations still constrain the shared font size.

Streaming paints the prefix fitting the current reference size while retaining cumulative full text; final output triggers group fitting and full-width spacing. Heading, column, source-style/size, fixed-size and explicit-cap boundaries remain. Some weak boxes can retain untranslated source, and a stream tail can wait for final output. This is a rendering fix, not an OCR or semantic-accuracy claim.

No new setting or ABI 2/export-signature change. Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. `fits=true` means reliable constraint rows fit; a weak outlier can still have `drawable=false`, so inspect per-row visibility. This version's C++ core requires a new build/audit; the old native audit does not certify its binary.

## 0.01.27 CUDA recognition and actual fallback

The first-run language page and regular settings share CUDA controls. `cuda_enabled` defaults to true. CUDA is attempted only in **Auto OCR mode** for English, Japanese or Chinese. Explicit Windows / Pixel modes use CPU. Auto also prioritizes the CPU Pixel route for detected classic English pixel frames when the portable engine is available (`pixel_priority`); other languages use existing local OCR. Missing components, incompatible hardware, invalid models or failed inference fall back to Windows / Tesseract with actual status. Installed files do not prove GPU execution. A failed OCR instance does not repeatedly retry CUDA; stop and restart after changing settings.

| Setting | Default | Range and meaning |
|---|---|---|
| `cuda_enabled` | `true` | Enable/disable; no automatic component downloads |
| `cuda_quality` | `75` | 0–100, performance to accuracy; linearly adjusts detector input limit with 32-pixel quantization |
| `cuda_memory_mb` | `1024` | 256–16384 MiB inference arena budget; does not force allocation of 1 GiB; runtime/driver overhead is additional |

The detector long-side limit is approximately `768 + 11.52 × cuda_quality`, rounded to a multiple of 32; 75 selects 1632 pixels. Only larger images are downscaled, so settings can be equivalent for small images. The slider is not an accuracy percentage and does not guarantee monotonically better accuracy or speed. The model is PP-OCRv6-small. Consult this version's GPU/dependency results rather than assuming every NVIDIA GPU works.

With optional cloud image refinement enabled, CUDA rows with confidence at least 95 and no rejection marker can proceed directly to translation; other rows remain on the verification path. **95 is a model-score threshold, not a measured 95% accuracy promise.** Local CUDA OCR uploads no image; cloud refinement remains a separate opt-in image-transfer path.

## Select the actual game window

1. Start `Windose.exe` and wait for the NEEDY GIRL OVERDOSE game window, then refresh the window list.
2. Choose an entry such as **Windose · Windose.exe · PID 123**. Windows assigns the PID and it may change on restart. A folder window with the same title belongs to `explorer.exe` and is excluded. Selection uses window/process identity, not a title or game-engine allowlist; ordinary English applications remain selectable.
3. Choose the entire game window or draw 1–8 regions, start translation, and return to the game. Selection rechecks HWND/PID. After closing or restarting the game, refresh and select its new window.
4. Status names the target and distinguishes waiting in the background, minimized, hidden, closed or replaced windows from recognition, no text found, AI waiting and displayed translations. **Waiting for the window means its game image is not currently being processed.** Restore and bring the selected game to the foreground to continue; the translator does not steal focus.

The application now uses a compact API toolbar instead of a large content-area icon, title and slogan. Its window/taskbar icon remains. Actual errors stay visible until stopping or restarting, rather than being overwritten by routine status updates.


Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

## A game-translation harness: understanding and display

NKC_Galgame_Translator places the model inside a bounded game-translation workflow. The program owns source text and coordinates, context references, budgets, object revisions and original-position rendering; the model provides understanding and translated text. Quality comes first: validate text and geometry before optimizing caches and scheduling. Additional recognition or online research may add waiting time.

| Layer | Modules | Responsibility | Boundary |
|---|---|---|---|
| Perception | `OcrCore`, helper, `RegionRefiner` | Whole-image discovery, refinement of located regions, measured words and ink | No invented coordinates or arbitrary unknown tiles |
| Context | `ContextArchive`, `ContextAgent` | Compressed history, terms and optional DeepSeek web references | Notes, sources, reasoning and progress never become overlay text |
| Translation | `TranslationEngine` | Current source plus bounded references; text-only streaming, concurrency and budget | No layout commands or local code execution |
| Display | `OverlayState`, C++ `fixed_layout.h` | Revision checks, original rows, consistent paragraph font, full-width spacing, streamed masks | Does not substitute background notes for the current translation |

Enable online background research in **Settings → Context and display layers**, save and restart translation. Public builds default to off. Only the supported official DeepSeek `deepseek-flash` server search extension is declared; other compatible providers retain ordinary translation. The model decides whether to search. A setting being enabled is not proof that search ran: status distinguishes received sources, no search and failures. Cached background references do not replace translation requests. See [context interfaces and limits](CONTEXT_AGENT.md).

One continuous body-text group shares a font size. At completion, character spacing can still expand to fill each original row. If a long row needs a smaller automatic font, the group shrinks together rather than enlarging another row. Headings, different source sizes, columns and font styles remain independent. Text that cannot fit at the minimum size retains the original. Font consistency cannot repair incorrectly measured OCR geometry.

The current live-game target is NEEDY GIRL OVERDOSE, focusing on small Japanese text, multicolor panels and paragraph sizing. Existing Space Rogue captures remain regression fixtures. Consult this release's test and performance reports for the actual coverage and limitations; a single scene is not an all-game claim.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## Multiple selections and automatic font styles

Choose a game window and click **Select region**. Drag repeatedly to add **1–8 non-overlapping rectangles**. Press **Enter to confirm**, Backspace or right-click to undo the last rectangle, or Esc to cancel without changing the previous selection. Minimum rectangle: 20 × 20 pixels. Combined bounds: at most 4096 pixels per axis. Keep each complete paragraph inside one rectangle with a small margin. Selections follow the game client, clip on resize and reset to the whole client when choosing a different game window. Selections last for the current UI session.

One captured frame serves all selections. Gaps between rectangles are blacked out before OCR or optional AI image reading. Grouping and tracking do not cross selection boundaries. Adding regions does not start independent OCR processes or change translation concurrency. Use windowed mode when needed.

In **Settings → Translation appearance**, enable **Match the source font style automatically (target-language support)**, save and restart translation. Local screenshot evidence approximates pixel, serif, sans-serif or monospaced style. Each box checks the installed font against the target script and actual translated characters. No font downloads are needed. This option defaults to off; disabling it restores the manual font. Size fitting and minimum/maximum sizes remain independent settings.

This matches broad style, not the original font file. Decorative text, complex backgrounds, short words and OCR mistakes can affect classification. Missing glyphs trigger an installed compatible fallback; if none exists, the original remains visible. Automatic coverage checking conservatively supports BMP characters. A box containing supplementary-plane characters or emoji retains the source; manual font mode remains available with Windows fallback.

Updated 2026-11-17. Configure a usable API slot, select a game window, language pair, optional profile and capture region, then start and return to the game. Interface language is independent of game languages; first launch preselects the Windows language and settings can switch Chinese, English or Japanese. Agreement acceptance remains explicit.

## Recognition and placement

The complete selected image is recognized before bounded workers refine discovered ink regions. Include a complete dialogue panel for column and paragraph evidence. Automatic/standard/pixel modes remain available. Separate columns, strong visual rules, prices and menus form boundaries. Uncertain or unrecognized text keeps its original pixels; whole-frame discovery cannot guarantee every game font is recognized.

Aero rendering prioritizes original background structure: a glyph mask uses foreground-color and antialias evidence, and only masked pixels receive local neighbor-guided repair. RGB outside the mask remains byte-identical in the background layer; there is no whole-row blur or added highlight. The background is fully opaque before translation is drawn. When glyphs cannot be distinguished reliably from similarly colored artwork, original pixels are retained and that translation is suppressed. Hidden detail can only be approximated.

Physical row bounds remain fixed, with gaps/prices untouched. Long output shrinks and shorter final output adjusts spacing; Windows may substitute unavailable font families.

## AI and history

Every new valid translation uses the API. Historical terms, translations and manual context are reference data rather than locally substituted answers. Without an API, existing records can be browsed but new translations cannot be generated. An unchanged translated object keeps its display; identical concurrent requests can share in-flight work. A subsequent manual submission calls AI again.

The dictionary page retains term/import tools and adds the latest 24 translation/context records. Stored events contain full source, result, context, model and time. Explicit profiles and language pairs scope histories; unnamed games use the selected executable identity.

## Settings

OCR refinement defaults to 4 workers (1–8), translation to 8 (1–16), matching to 2 (1–4). Threads do not promise linear speedups. Context defaults to 6000 characters (512–16000) and 24 recent records (1–64). These limits bound the next prompt excerpts, not the stored full history.

Source labels, mixed-foreign-language labels and brackets are separately selectable. Unlimited requests only removes the count cap; finite zero disallows requests. Stop and await in-flight work before applying network/worker changes.

## Files and troubleshooting

`data/codebook.sqlite3` stores translations and compressed contexts. `data/contexts/<scope_id>/updated.json` records status with `+08:00` timestamps; backing up only the JSON does not back up the records. Old version folders remain intact. Close the app before copying its database or use SQLite backup.

Stop/close removes overlays, mouse input passes through, and focus loss hides them. If output is absent, check target/region, foreground state, API credentials, quota and controlled errors. Pixel mode may help pixel fonts. Optional AI image reading requires actual provider/model image support; a model name alone is not proof of that capability. Failure retains local recognition.

[Full settings](LOCAL_TRANSLATION.md) · [API](API.md) · [Import](DICTIONARIES.md) · [Privacy](SECURITY.md)

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

## 0.01.23 · Mixed colors and selected rows · 18 November 2026

Local RGB background-distance normalization supports ordinary text, selected backgrounds and colored text, including near-equal luminance colors. Existing whole-frame detections are retained. Only measured local rows are supplemented, and actual word boxes keep labels separate from prices. The original frame remains unchanged.

A bounded 16 MiB / 64-entry exact-RGB crop cache reuses unchanged recognition without reusing absolute coordinates. Text, color, size and language changes invalidate reuse. No additional OCR threads or game-specific word correction tables were added.

See the [performance and recognition report](../PERFORMANCE_REPORT.en.html) for the fresh 0.01.15 versus 0.01.27 same-image comparison and separately scoped real-API observations. Local OCR, first translation callback and final translation callback are separate metrics. This fresh run does not measure native painting or monitor presentation; callback arrival is not screen visibility and 150ms is not an end-to-end ceiling. NEEDY GIRL OVERDOSE is the current live-game test target, emphasizing small Japanese text and multicolor panels. Image replays, synthetic layout cases and real API tests are labeled separately; they do not certify the entire game.
