# NKC_Galgame_Translator · Real-time game translation · 0.01.27

<!-- teacher-review27 -->
[Teacher review: complete bilingual manuals, fresh .15 → .27 measurements and UI gallery](../teacher-review27/index.html).

## 0.01.27 Group fitting and short continuation rows

Continuous body text uses median source-row ink height as a stable reference. In a group of at least three rows with at least two wide body rows forming a majority, a very short continuation or unusually shallow ink row does not alone shrink the whole paragraph. Within one region, overflowing continuation text can move complete clusters into measured spare width on the immediately preceding row: at most 64 candidates, retaining at least one cluster on the continuation. No row rectangle expands. A weak row that still cannot fit preserves original pixels. Text never transfers between regions; ordinary/medium-width long translations still constrain the shared font size.

Streaming paints the prefix fitting the current reference size while retaining cumulative full text; final output triggers group fitting and full-width spacing. Heading, column, source-style/size, fixed-size and explicit-cap boundaries remain. Some weak boxes can retain untranslated source, and a stream tail can wait for final output. This is a rendering fix, not an OCR or semantic-accuracy claim.

No new setting or ABI 2/export-signature change. Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. `fits=true` means reliable constraint rows fit; a weak outlier can still have `drawable=false`, so inspect per-row visibility. This version's C++ core requires a new build/audit; the old native audit does not certify its binary.

## 0.01.27 Display does not wait for web reference

`TranslationEngine.translate()` reads only completed `ContextAgent.peek(key)` reference and immediately sends a tool-free translation request using current source, supplied context and available history. Only after successful translation and network-slot release does `refresh()` attempt background research. New notes benefit later sentences, never revise an already displayed translation or enter overlay events.

At most one background task and no waiting queue. The key includes game, executable identity, source/target languages and supplied context; 32 cached entries, 900 seconds with a summary and 30 seconds for empty/failed references. Background work shares concurrency, request/token accounting and cancellation, yields to waiting display jobs and does not use the sole slot when concurrency is one. Remaining budget favors translation. Closing cancels transport and joins the background worker.

Research failure cannot discard successful output. Background authentication/balance errors become unavailable with cooldown; errors in display requests still surface normally. `searching` denotes background work; `searched` requires final server-source evidence. Source/history/pages/notes remain untrusted JSON data: no local tools, automatic returned-URL fetches or credentials in prompts.

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

Read game text where it appears. Windows10/11 x64.

## Multiple selections and automatic font styles

Choose a game window and click **Select region**. Drag repeatedly to add **1–8 non-overlapping rectangles**. Press **Enter to confirm**, Backspace or right-click to undo the last rectangle, or Esc to cancel without changing the previous selection. Minimum rectangle: 20 × 20 pixels. Combined bounds: at most 4096 pixels per axis. Keep each complete paragraph inside one rectangle with a small margin. Selections follow the game client, clip on resize and reset to the whole client when choosing a different game window. Selections last for the current UI session.

One captured frame serves all selections. Gaps between rectangles are blacked out before OCR or optional AI image reading. Grouping and tracking do not cross selection boundaries. Adding regions does not start independent OCR processes or change translation concurrency. Use windowed mode when needed.

In **Settings → Translation appearance**, enable **Match the source font style automatically (target-language support)**, save and restart translation. Local screenshot evidence approximates pixel, serif, sans-serif or monospaced style. Each box checks the installed font against the target script and actual translated characters. No font downloads are needed. This option defaults to off; disabling it restores the manual font. Size fitting and minimum/maximum sizes remain independent settings.

This matches broad style, not the original font file. Decorative text, complex backgrounds, short words and OCR mistakes can affect classification. Missing glyphs trigger an installed compatible fallback; if none exists, the original remains visible. Automatic coverage checking conservatively supports BMP characters. A box containing supplementary-plane characters or emoji retains the source; manual font mode remains available with Windows fallback.

The latest measured performance evidence compares 0.01.15 with 0.01.25; 0.01.27 did not remeasure those historical samples. [Report](../PERFORMANCE_REPORT.html).

## Placement and streaming

Output keeps source rectangles, physical rows and ink positions. Final short text adjusts character spacing; long text shrinks down to 8 pixels. If it still cannot fit, the original image remains visible. Streaming uses natural spacing and adjusts final spacing once. Grouping supplies translation context; `_source_rows` preserves original display rows.

Only the selected foreground HWND/PID receives click-through overlays. Focus loss, stop and stale revisions remove them. Buffered painting reduces flicker, without promising perfect results on every font or animated scene.

## Getting started

1. Extract the complete `NKC_Galgame_Translator-0.01.27-windows-x64.zip` into a writable directory and run the executable. Keep its companion files.
2. Choose Chinese, English or Japanese on first launch, then read and explicitly accept the disclaimer and complete MIT. Use the prominent **API configuration · 3 slots** entry. Saving does not send a request. Windows CurrentUser DPAPI encrypts keys.
3. Select the game window, language pair, optional profile and context; choose a game region and start translation. Without a usable API, only existing records can be browsed; no new translation is generated.
4. Settings expose OCR refinement workers, AI concurrency, history budgets, fonts, source labels and brackets. Stop and await in-flight work before changing network settings.
5. The dictionary page retains term/import management and adds a history viewer for the latest 24 translation/context records. Imported terms are references, not an offline translator.

## Context compression and time

Full events are stored losslessly with zlib in SQLite table `ai_context_events`. The next prompt receives bounded excerpts, default 6000 characters and up to 24 recent records. This is not an AI-written semantic summary and does not recursively embed previous prompts. SQLite is authoritative; an atomic `updated.json` sidecar is only a status index.

Release folders retain the `0.xx.xx` naming convention, with dates in documentation and archive metadata rather than repeatedly renaming a running directory. Preserve old databases and configuration when migrating. DPAPI credentials may not decrypt under another Windows account or computer. Public packages exclude private keys, histories and game screenshots.

## Limits and privacy

Unlimited requests removes only the software request-count cap. Provider credit/rate limits, concurrency, timeouts and retries still apply. A finite quota of zero prohibits new requests. Failed/truncated output is not a successful archive entry. Source text, manual context and selected historical references are sent to the selected API; optional image reading additionally uploads the selected game crop and is off by default. Model text is never executed.

## Documentation

[User guide](USER_GUIDE.md), [architecture](ARCHITECTURE.md), [workflow](WORKFLOWS.md), [API](API.md), [settings and archive](LOCAL_TRANSLATION.md), [dependencies](DEPENDENCIES.md), [release validation](RELEASE.md). Current results are in [TEST_REPORT.json](../TEST_REPORT.json). Synthetic-window and screenshot regression tests are not universal live-game/API validation.

The project-level `Start.ps1` selects the latest complete release and prefers its private demo when available. Use `-Public` for public configuration. Machine-readable release/date metadata: [UPDATE.json](../UPDATE.json).

## 0.01.20 · Screenshots and font size · 2026-11-17

Open Settings → Translation appearance, save, then restart translation.

| Setting | Default | Contract |
|---|---|---|
| `capture_translations` | true | Include overlays in desktop screenshots/recording; disable to use Windows capture exclusion |
| `auto_font_size` | true | Start from source glyph height and shrink within the configured range; streaming revisions never grow |
| `overlay_font_size` | 24 | Fixed size when automatic fitting is off, 8–512 physical pixels |
| `overlay_font_min` | 8 | Automatic lower bound, 8–512 |
| `overlay_font_max` | 72 | Automatic upper bound, 8–512, at least the lower bound |

Fixed size never shrinks. If content cannot fit at the fixed size or automatic lower bound, the original remains visible. Source rectangles and physical rows remain unchanged; completed text adjusts character spacing within each row.

When screenshots include translations, OCR uses Windows Graphics Capture on the selected game HWND only. Overlay windows never enter OCR; no periodic hiding or capture-affinity toggling occurs. In-game screenshots and recorders targeting only the game HWND may still omit overlays; use desktop screenshots/display recording. Windows may show its capture border. Capture failure reports an error; disable inclusion to use the previous desktop capture path.

Saved API keys show twelve constant placeholder dots even on focus. The visual label is never an input value and never contains the decrypted credential. Typing, choosing an empty slot, changing the endpoint or checking Clear hides it; blank input on the same endpoint preserves the encrypted key.

Python API: `NativeCore.set_overlay_options(*, auto_font_size=True, overlay_font_size=24, overlay_font_min=8, overlay_font_max=72, capture_translations=True)`; forwarded by OcrCore/VisionCore. C export: `int gl_overlay_options(void*, int automatic, int size, int minimum, int maximum, int screenshots)`. Flags must be 0/1, sizes 8–512 and minimum≤maximum. Invalid input returns 0 without mutation. Equal options preserve fit; changed options refit asynchronously. ABI remains 2; Python requires the new export. Unbound diagnostic overlays remain capture-excluded. Hide/rebind closes the capture session.

`native/window_capture.h` uses C++/WinRT and system Direct3D 11 (hardware, with WARP fallback), BGRA and two frame-pool buffers. Window limits: 8192 per axis and 16777216 pixels; output limits: 4096 per axis. DWM physical bounds control cropping; mismatched scaling is rejected and resizing discards the old frame. No new third-party dependencies, borderless-capture permission requests or system privacy changes.

References: [Windows Graphics Capture](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture), [SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity).
