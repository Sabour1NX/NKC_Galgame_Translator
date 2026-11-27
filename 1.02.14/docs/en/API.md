# Detailed interface specification — 0.01.27

## 0.01.27 CUDA runtime and prewarm contracts

Optional components lock ONNX Runtime GPU 1.32.0, RapidOCR 3.10.0, CUDA 13.x runtime / cuDNN 9.x. RTX 3070 / driver 617.42 was verified locally; this does not certify other combinations. Wheel/model hashes are fixed. Detection and recognition provider arenas share the configured budget, totaling 1 GiB by default, with additional driver/runtime memory.

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` retains disabled-by-default low-level call compatibility; App passes the enabled user-setting default and may transfer a prewarmed `CudaOcr` instance. `App._prepare_cuda()` runs local `warmup()` in a background thread without screen capture or API requests, reusing the helper for later OCR. Prewarming does not eliminate first-inference cost for every new image shape.

## 0.01.27 CUDA modules and IPC

| Module / class | Language | Responsibility |
|---|---|---|
| `cuda_ocr.py` / `CudaOcr` | Python / MIT | Local bounded JSON IPC client, hidden helper, image paths and lifecycle; no deep-learning imports in the GUI |
| `tools/cuda_ocr_helper.py` / `Engine` | Separate Python helper | RapidOCR / ONNX Runtime CUDA, PP-OCRv6-small detection/recognition, verification of executed CUDA kernels |
| `cuda_settings_ui.py` / `CudaControls` | Python / Tk | Shared first-run/settings switch, linear quality slider and memory budget; no probing/downloads |
| `OcrCore` | Python | Attempt GPU in Auto for en/ja/zh; same-frame CPU fallback on failure, actual `cuda_status` |

`CudaOcr(root, memory_mb=1024, quality=75)` exposes `available()` (files only), serialized `recognize(image, language='en')` and `close()` (helper/temp-image cleanup). Recognition requests contain only `image_path/language`; `warmup()` sends `{"warmup":true}` using synthetic tensors without capture/network; `cancel()` interrupts the helper and the cancelled instance cannot restart. Images are restricted to the allowed temporary root; stdin is data, never code. Responses contain `lines/ocr_ms/cuda`, at most 512 rows, 64000 total text characters and 1 MiB response size; rectangles must fit the image and confidence must be finite in 0–100. Acceptance requires `CUDAExecutionProvider` and `kernels_verified=true`, rather than provider availability alone.

States: `disabled/ready/active/not_installed/failed/cpu_mode/pixel_priority/unsupported_language`; ready is not proof of completed inference. Versions and hashes are locked in `requirements-cuda.lock`, `CUDA_DEPENDENCY_MANIFEST.json` and `models/cuda/manifest.json`. Distribution manifests carry component/model licensing. Installation/verification failure must preserve CPU fallback rather than claiming GPU acceleration.

## 0.01.27 Display does not wait for web reference

`TranslationEngine.translate()` reads only completed `ContextAgent.peek(key)` reference and immediately sends a tool-free translation request using current source, supplied context and available history. Only after successful translation and network-slot release does `refresh()` attempt background research. New notes benefit later sentences, never revise an already displayed translation or enter overlay events.

At most one background task and no waiting queue. The key includes game, executable identity, source/target languages and supplied context; 32 cached entries, 900 seconds with a summary and 30 seconds for empty/failed references. Background work shares concurrency, request/token accounting and cancellation, yields to waiting display jobs and does not use the sole slot when concurrency is one. Remaining budget favors translation. Closing cancels transport and joins the background worker.

Research failure cannot discard successful output. Background authentication/balance errors become unavailable with cooldown; errors in display requests still surface normally. `searching` denotes background work; `searched` requires final server-source evidence. Source/history/pages/notes remain untrusted JSON data: no local tools, automatic returned-URL fetches or credentials in prompts.

## 0.01.27 Group fitting and short continuation rows

Continuous body text uses median source-row ink height as a stable reference. In a group of at least three rows with at least two wide body rows forming a majority, a very short continuation or unusually shallow ink row does not alone shrink the whole paragraph. Within one region, overflowing continuation text can move complete clusters into measured spare width on the immediately preceding row: at most 64 candidates, retaining at least one cluster on the continuation. No row rectangle expands. A weak row that still cannot fit preserves original pixels. Text never transfers between regions; ordinary/medium-width long translations still constrain the shared font size.

Streaming paints the prefix fitting the current reference size while retaining cumulative full text; final output triggers group fitting and full-width spacing. Heading, column, source-style/size, fixed-size and explicit-cap boundaries remain. Some weak boxes can retain untranslated source, and a stream tail can wait for final output. This is a rendering fix, not an OCR or semantic-accuracy claim.

No new setting or ABI 2/export-signature change. Native diagnostics add `font_intrinsic_px` and `lines[].drawable`. `fits=true` means reliable constraint rows fit; a weak outlier can still have `drawable=false`, so inspect per-row visibility. This version's C++ core requires a new build/audit; the old native audit does not certify its binary.

## 0.01.27 window identity and runtime status

`window_metadata(hwnd, paths=None)` returns `hwnd,pid,title,process_path,exe_name,class_name`; list refresh shares process-path queries by PID. `translation_target(row)` filters metadata, without a game-title/engine allowlist. Explorer, desktop, taskbar, shell/helper windows and the application's overlay are excluded. Entries display “title · executable · PID”.

`App.chosen_window()` rereads metadata and validates HWND/PID, rejecting stale identities and shell/helper targets. `window_state(hwnd, expected_pid)` returns `closed / replaced / minimized / hidden / background / active`, without opening the process. `App._refresh_running_status()` runs at most once per second and combines target state with pipeline events to distinguish waiting, recognition, no text, AI requests and displayed translations. Actual errors stay latched until stopping/restarting. A status label is not evidence of completed translation: background/minimized targets and invisible selections are not captured for translation. Language settings, 1–8 selections, screenshot options, fonts and character spacing remain unchanged.


Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

## 0.01.27 perception candidates and image reading

`OcrCore.recognize_image` / `capture_ocr` may additionally return up to 128 `vision_anchors`: `text,x,y,w,h,bg,fg,confidence,_source_ink,_vision_only=True`. Low-confidence candidates provide geometry only to explicitly enabled AI image reading. They never enter ordinary rendered translations or success history. Normal local lines retain the configured confidence threshold (default 55). Selection filtering and coordinate conversion apply to candidates too.

The independent helper's `find_text_surfaces`, `surface_rows`, `read_text_surfaces` and `merge_surface_detections` follow whole-frame discovery with measured flat-panel RGB normalization and physical-row rereading. There are no game-specific coordinates. Oversized filled button blocks are excluded as text rows. Limits remain 512 ordinary lines, 128 candidates, 64000 combined characters and a 1 MiB JSON response; text, finite confidence and geometric bounds are validated.

Optional Vision includes the complete selected game-region image and up to 32 enlarged small-text crops from that same region. Additional crops have an aggregate 2-million-pixel and 4 MiB raw PNG budget; the original image retains existing image/HTTP limits. The model rereads locally anchored source text and cannot invent coordinates. Missing reliable local geometry leaves the source intact. A similar model name does not prove image-input support. Background search and image reading are independent settings; search does not replace OCR.

## 0.01.27 layer and font contracts

[CONTEXT_AGENT.md](CONTEXT_AGENT.md) specifies research payloads, source metadata, caches and statistics. `TranslationEngine.translate(...)` keeps its signature; `on_chunk` still carries cumulative translated text only. Reasoning, background notes and search sources never become Pipeline translation-display events. Geometry and physical rows come from local observations, not model output.

| Native output/process | Contract |
|---|---|
| `regions[].font_px` in `gl_overlay_snapshot()` | Actual GDI em size in physical pixels, not visible ink height or typographic points |
| `regions[].font_peers` | New read-only integer: count of Regions sharing the current body-text font, default 1; not OCR rows or API requests |
| `prepareFixedOverlay` | Fixed `国Ag` reference anchors the em ceiling; one font covers all physical rows, whose widths/heights are still checked individually |
| `harmonizeFixedFonts` | At final output, fit compatible body peers together; exclude qualifying weak continuation constraints, preserve unfit weak source rows, retain rectangles and full-width spacing |
| Peer boundary | Ink heights differ by ≤25%; gap≤max(4,0.65×minimum ink height); left-edge difference≤min(12,max(3,0.4×minimum ink height)); same face/style/explicit cap and close colors; at least one row width≥8×ink height |
| Fixed font mode | No automatic shared shrink; keep the selected size and preserve source where it cannot fit |
| Streaming | A revision's font only stays or shrinks; stale revisions cannot repaint; completed rows retain full-width character spacing |

ABI 2, GLRegion/GLSourceRow layouts and existing exported signatures are unchanged. The additive diagnostic JSON field does not alter the binary input structure. Installed-font/target-glyph checks remain in the measurement/render path. Font fitting cannot invent correct OCR geometry.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## Selection and font interfaces

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

Version 0.01.20 uses AI-only translations, whole-frame discovery with parallel refinement, column-aware prose groups, compressed context and automatic timestamps. Fixed source rows, shrink/spacing, object revisions, three DPAPI slots and bounded SSE remain. GLRegion stays ABI 2 (56 bytes); gl_overlay_fixed is unchanged.

## Native C ABI

Authoritative declarations: `native/core.h`; implementation: `native/core.cpp`; consumer: `nkc_galgame_translator/native.py`. Exports use `extern "C" __declspec(dllexport)`. Python uses `ctypes.CDLL` with explicit argument/result types. Win64 has a unified calling convention; 32-bit Python cannot load the DLL.

```cpp
struct GLRegion {
    int32_t x, y, width, height;
    uint32_t background, foreground;
    int32_t font_size, final;
    const wchar_t* text;
    uint64_t track_id, revision;
};
uint32_t gl_abi_version();
void* gl_create();
void gl_destroy(void* context);
const char* gl_languages();
const char* gl_capture_ocr(void* context, int x, int y,
                         int width, int height, const wchar_t* language);
const char* gl_capture_frame(void* context, int x, int y, int width, int height);
const char* gl_ocr_bgra(const uint8_t* pixels, int length, int width, int height, const wchar_t* language);
int gl_copy_frame(void* context, uint8_t* destination, int capacity);
void gl_reset(void* context);
int gl_overlay(void* context, const GLRegion* regions, int count);
int gl_set_font(void* context, const wchar_t* family);
const char* gl_overlay_snapshot(void* context);
void gl_hide(void* context);
void gl_set_target(void* context, uintptr_t window, uint32_t process_id);
const char* gl_error();
```

The context is opaque, created/destroyed exactly once by this DLL. A direct caller must finish other calls before destroying it. `GLRegion.text` is at byte offset 32, `track_id` at 40 and `revision` at 48; the structure has no custom packing. Validate ABI 2 and presence of both `gl_set_font` and `gl_ocr_bgra` before use. A matching number alone is insufficient for the new wrapper.

Coordinates are physical pixels on the virtual desktop; negative monitor coordinates are valid. Capture must be wholly inside the virtual desktop and at most 4096×4096; WinRT may impose a smaller `MaxImageDimension`. Colors are Win32 COLORREF, `0x00bbggrr`; Python accepts RGB triples converted/clamped to 0–255. Input text is caller-owned NUL-terminated UTF-16. `gl_overlay` copies text and regions before returning; caller buffers may then be freed. Font input is copied as well.

Returned JSON/error strings are borrowed thread-local UTF-8 buffers. Copy/decode before the next call on that thread; never free them. `gl_error` describes a failed call, not proof of a previous success. `gl_copy_frame` writes caller-provided top-to-bottom BGRA bytes and requires capacity at least `width*height*4`.

| Export | Success | Failure or lifecycle rule |
|---|---|---|
| `gl_abi_version` | 2 | Check before passing a structure. |
| `gl_create` | Non-null context | Null; inspect `gl_error`. |
| `gl_destroy` | No return | Caller drains concurrent calls. |
| `gl_languages` | JSON language-tag array | JSON error, not integer status. |
| `gl_capture_ocr` | OCR JSON with screen-coordinate boxes | JSON error. |
| `gl_capture_frame` | `changed/capture_ms` JSON, pixels retained in context | JSON error. |
| `gl_copy_frame` | Bytes copied | 0 for invalid context/buffer/capacity/frame; does not promise to change last error. |
| `gl_reset` | Clears frame-dedup state | Null context is a no-op. |
| `gl_overlay` | 1: latest snapshot accepted for drawing | 0 with `gl_error`; success is not synchronous paint completion. |
| `gl_set_font` | 1: family accepted | 0 without changing the previous family/state. |
| `gl_overlay_snapshot` | Most recently completed render JSON | JSON error for invalid context. No capture/network call. |
| `gl_hide` | Empty snapshot and cleared font history | No status code. Different from short-term-history-preserving empty overlay. |
| `gl_set_target` | Updates HWND/PID and clears overlay | Null context is a no-op. Zero target is diagnostic-only; normal use binds a game. |
| `gl_error` | Borrowed UTF-8 error | No fixed numeric error enumeration. |

`gl_overlay` accepts 0–512 regions. Count zero hides current windows while retaining short history. Invalid individual width/height (nonpositive or above 8192) or coordinate addition overflow is skipped by C++; Python rejects such batches before submission. Nonzero IDs cannot repeat in one snapshot. Per-region text is limited to 64,000 UTF-16 units, the batch to 1,048,576. `font_size` is 0–512, zero requesting automatic fitting. `final=0` masks only current laid-out text; a nonzero final flag covers the whole region.

### Font selection

`NativeCore.set_overlay_font(family: str) -> None` and `OcrCore.set_overlay_font(family) -> None` forward to `gl_set_font`. Python requires a nonempty, not-all-whitespace string of at most 31 UTF-16 units and rejects Unicode Cc/Cf/Cs characters. It preserves the string; UI trimming occurs before the call. Invalid input raises `ValueError`; a closed context or native rejection raises controlled `RuntimeError`. The new export is checked before context creation.

The C export reads the NUL-terminated name, permits 1–31 UTF-16 units, and rejects null/empty/all-Unicode-whitespace input, C0/C1 controls and unpaired surrogates. A valid supplementary character occupies two units. A direct C caller must provide a valid readable pointer. Native checks cannot validate arbitrary addresses.

The initial family is `Microsoft YaHei UI`. An identical name is a no-op and preserves fitting history. A new name is applied asynchronously to current pending regions, clears prior fitting history and redraws. GDI uses the same family for measuring and painting. A syntactically accepted name does not guarantee that Windows has that font; the OS can substitute another face or missing glyphs.

### Wrapper lifetime, capture and MTA

`NativeCore` provides `languages`, `capture_ocr`, `capture_bgra`, `recognize_bgra`, `reset`, `show_overlay`, `set_overlay_font`, `overlay_snapshot`, `hide_overlay`, `set_target` and `close`. It loads an absolute validated local DLL with search flags `0x900` (DLL directory and System32 only). `_capture_lock` serializes capture/copy/reset. A condition/reference count pins active calls so closing cannot destroy the context underneath them; overlay drawing does not hold the capture lock. JSON errors/empty responses become `RuntimeError`.

`languages()` is synchronous to its caller but executes on a process-owned single persistent MTA executor. Submission is serialized instead of accumulating an unbounded executor queue; thread-local JSON is decoded inside that worker while the operation is pinned. The worker survives individual `NativeCore.close()` calls and is joined at process exit. This avoids the Tk STA conflict and repeated last-MTA teardown invalidating WinRT activation caches. Direct C callers own COM/WinRT initialization and its lifetime themselves.

### Stable rendering and diagnostics

Nonzero `track_id` and `revision` tie font state to a text object, not array index. A changed ordering or another object's disappearance does not transfer its font size. ID 0 is diagnostic/index-based and is refitted without persistent history. Same-object/revision streaming preserves reference size and paints a fitting prefix, then fits the complete group at final output. Tiny geometry noise preserves font history; substantial geometry correction allows recalibration. Wrap and fit use the selected GDI face.

Missing objects' windows are destroyed promptly, while up to 64 `revision/text/fontPixels/missingSince` history records (no HWND/HFONT) remain for up to three seconds. Reappearing matching IDs/revisions with continuously extending text can reuse the previous upper font-size bound. Expired/over-capacity records are removed during later rendering. Explicit hide, target change, font-family change or context destruction clears relevant history.

`gl_overlay_snapshot` returns a sequence and regions from the latest completed drawing, potentially behind the latest submission. Top-level `font_family` is present even before rendering and reports the configured family. Region `font_face` reports the actual GDI `GetTextFaceW` result; names can be localized. Other fields include bounds, `font_px`, `fits`, `final`, `text_units`, IDs/revisions and line `y/width/height/start/length`. Bounds are screen coordinates, line y is relative to its window, and text_units counts UTF-16 units. No source/translation body or pixels are returned. A failed fit at minimum size may still report `fits=false`.

## OCR observations and window branding

```json
{"changed": true, "capture_ms": 2.4, "ocr_ms": 18.5,
 "lines": [{"text":"Start", "x":320, "y":610, "w":140, "h":36,
            "bg":[20,20,20], "fg":[245,245,245]}]}
```

Times are milliseconds and example numbers are not performance guarantees. `changed=false` plus `lines=[]` denotes frame deduplication, not disappeared text. Portable backends may add engine/confidence/min_confidence/rejected_lines fields; consumers allow compatible extra fields. Input validation details are in the input/IPC chapter.

```python
configure_process_identity() -> bool
install_window_icon(window, root: str | Path) -> Path
window_icon_handles(window) -> dict[str, int]
```

These `nkc_galgame_translator.branding` functions set AppUserModelID `Nishokuchou.GameRealtimeTranslator` before the first Tk window, install `root/assets/taiji.ico` for the window/default future top levels, and read small/large `WM_GETICON` handles for diagnosis. Identity failure raises OSError; a missing icon raises FileNotFoundError. Returned icon handles belong to the window and must not be destroyed by callers; zero means unavailable. Tk's no-argument iconbitmap query may be empty despite a valid ICO, so verification uses handles. PyInstaller embeds the same ICO; SVG/PNG/multisize ICO and `tools/generate_icon.py` remain in source.

## Pipeline and display contracts

```python
Pipeline(core, engine, emit, *, interval=.25, settle=.45,
         merge_lines=True, tracking_workers=2, translation_workers=4,
         max_objects=32, max_missing=2,
         show_source_label=True, show_translation_brackets=True,
         source_label_mixed_only=False, warmup_scope=None)
pipeline.start(region_provider, game, source, target, context='')
pipeline.get_stats() -> dict
pipeline.stop()
pipeline.join(timeout=2) -> bool
pipeline.alive -> bool
label_translation(text, source, final=True, *,
                  show_source_label=True, show_translation_brackets=True) -> str
```

The region provider runs on the capture thread and returns `(x,y,width,height)` or None. It must be thread-safe and must not manipulate Tk. Re-check after OCR rejects a moved/unfocused frame. The core supplies capture/reset/hide methods and is normally bound through `set_target`. `emit` must be fast and thread-safe, typically a queue put, never synchronously block on UI work. Some events are emitted under a state lock.

Each Pipeline starts once. `alive/join` cover capture/coordinator, not all submitted HTTP jobs. Stop prevents new tasks, changes generation and hides output; already sent work can finish but its stale results are rejected. Old jobs continue occupying bounded pool slots rather than creating an unbounded replacement backlog.

| Event `(kind,generation,payload)` | Payload and interpretation |
|---|---|
| `objects` | List of `{track_id,revision,line}` current observations; precedes translation for that revision. |
| `translation` | `(track_id,line,original_text,done)`. `line.text` is cumulative, display-formatted text; `line.final=done`. |
| `line_error` | `(track_id,revision,message)`. Remove only that object's failed output; unavailable API also preserves source. |
| `timing` | OCR observation, capture/OCR timings and recognized lines. |
| `clear` | None. Stop/focus/error generation change clears presentation. |
| `error` | Controlled failure string; capture pipeline stops. |

Line data contains `text,x,y,w,h`, usually colors/source language and optional font size. Display events carry `_revision/final`; OverlayState adds `_track_id`. `_capture_origin` survives dialogue grouping. The original text is undecorated. Empty partial output always stays empty. When brackets are enabled the closing bracket is added only on final output. The two display booleans default true, remain independent, and never alter engine input, dictionary content or cache keys. Manual text translation remains undecorated.

OverlayState retains accepted geometry for at most 64 IDs, rejects vanished/old revisions and late partials after completion. A two-pixel deadband absorbs small noise; small dimension/position changes need repeated confirmation, while substantial movement follows promptly. Missing objects hide immediately; matching ID/revision can recover short geometry history. New revisions/clear do not reuse it. After a changed frame at most two unchanged polls reuse OCR as confirmation (`advance_missing=False`), without another OCR or translation. Capacity-one observation queues may replace confirmations with newer real frames.

Pipeline statistics are `objects`, `pending`, `inflight`, `queue_drops`, `observation_queue`, `tracking_workers`, `translation_workers`. Capture is one region; matching workers are 1–4, translation workers 1–16, object capacity 1–32. Queue replacement means keeping a fresher observation, not losing all object state.


### Show source labels only for mixed foreign languages

`show_source_label` is the master switch. The strict boolean `source_label_mixed_only` defaults to false; its checkbox is disabled when the master switch is off. The effective policies are: master off → no labels; master on/mixed-only off → always label; both on → label only when the current visible OCR objects contain at least two distinct foreign source-language bases after excluding the target-language base. `en-US` and `en` count together, as do `zh-Hans` and `zh-CN`. For a Chinese target, English alone hides source labels; English plus Japanese enables them. Counting follows recognized object languages, independently of the application interface language.

Object appearance/disappearance and scene changes reformat accumulated translations without another LLM call or changes to object IDs, revisions, dictionaries or cache keys. Brackets stay independent, so `[translation]` remains possible without a source label. Preview shows single-language and mixed-language samples locally without network access. The four basic formatting combinations apply when source labeling is effective; this additional policy decides when it is effective.

## TranslationEngine

```python
TranslationEngine(config, db_path, *, client=None)
translate(game, source_lang, target_lang, text, on_chunk=None, context='', *, warmup_scope=None) -> str
get_context_status(game, source_lang, target_lang, *, warmup_scope=None) -> dict
list_translation_history(game, source_lang, target_lang, *, warmup_scope=None, limit=24) -> list[dict]
set_term(game, source_lang, target_lang, source, target) -> None
list_terms(game, source_lang, target_lang) -> list[dict]
delete_term(game, source_lang, target_lang, source) -> bool
list_profiles() -> list[str]
remember_profile(game) -> None
import_terms(entries, game, source_lang, target_lang, shared=False, replace=False) -> dict
get_stats() -> dict
close() -> None
```

Translation is synchronous on a worker; callbacks receive cumulative full text and must not modify Tk. Every new nonempty cross-language task calls AI. Only identical scope/identity/text/context/model/endpoint work currently in flight shares a Future; followers receive the final result. A completed result is never the local answer for a subsequent call. Empty text returns empty and same-language calls return input; the GUI disallows identical languages.

Inputs normalize NFC, CRLF and surrounding whitespace; reject NUL, lone surrogates and controls except CR/LF/TAB. Profiles allow 256 characters, source defaults to 4000 (maximum 16000), manual context 2000, and language codes use a bounded 1–64-character grammar. Missing keys raise controlled TranslationError without network/local substitution. BudgetExceeded means the count cap; TranslationCancelled means shutdown. Injected clients belong to the caller; only internally created clients are closed by the engine.

Reference selection takes the engine lock; HTTP does not hold it. A complete success and its compressed event commit in one transaction. Failure/truncation does not become successful history; shared followers do not duplicate events. `warmup_scope` retains its old parameter name only for game identity. `get_warmup_status()` reports disabled/ai_only and `explain_local()` produces no local translation. Old policy flags do not reactivate expert/hybrid/aggressive/warmup routing.

Term/profile CRUD remains local and validated. Game terms allow 5000 entries, with 256-character fields. Imports maintain references, not executable `{n}` templates or composition rules. Shared dictionaries can still be managed, but current prompt extraction uses matching terms from the current named game; shared-table translation is not implemented.

## Compressed context API

```python
ContextArchive(db, folder, database_name, max_chars=6000, history_records=24)
prompt(scope, identity, text, context) -> str
record(scope, identity, source, translation, context, prompt_context, model) -> None
history(scope, identity=None, limit=24) -> list[dict]
status(scope, identity=None) -> dict
update_manifest(scope, identity=None) -> None
decode_event(blob: bytes) -> dict
```

The caller owns locking/transactions for the supplied SQLite connection. Scope is `(game,src_lang,dst_lang)`; SHA256 scope keys include identity for unnamed games. Record JSON fields are `schema,source,translation,context,prompt_context,model,created_at`. Full events use zlib level 6, bounded to 1MiB before/after decompression; timestamps carry Asia/Shanghai `+08:00`. Invalid compressed/schema records are skipped on history reads without overwriting them. History is newest first, limit 1–64.

Status returns `scope_id,records,updated_at,raw_bytes,compressed_bytes,directory,prompt_max_chars,compression`; directory is a private local path. Prompt JSON contains `kind,user_context,terms,recent_translations`, within the total character budget. Up to 32 matched terms use 256-character fields; recent source/result excerpts use 512 and context 200. Prior prompt_context is never recursively included. Full stored events remain intact; compression is neither encryption nor AI-written summarization.

The atomic sidecar `folder/<scope_key>/updated.json` adds schema/database/table/timezone to statistics, without source/result/key text. SQLite remains authoritative; sidecar I/O failures increment manifest_errors without rolling back committed data. Engine statistics expose the AI route and context budgets/errors, never event bodies.

## ConfigStore and credentials

```python
ConfigStore(root: str | Path)
load() -> dict
save(config: dict, api_key: str | None = None) -> dict
save_api_slot(index: int, base_url: str, model: str,
              api_key: str | None = None, *, activate=True,
              offline_only=False, allow_key_reuse=False) -> dict
credential_error: str
```

Root is the installation directory, independent of cwd. Operations use an instance RLock, not a cross-process writer lock; avoid simultaneous writers to one configuration directory. JSON/ciphertext are capped at 1 MiB; JSON also limits nesting to 32 and nodes to 10,000, rejecting duplicate keys and nonfinite numbers.

Load merges example and local preferences, ignoring any example key. An unreadable ordinary JSON raises controlled `ConfigStoreError`; it is not silently overwritten. Credential corruption/missing pointer/binding failure returns an empty runtime key and a controlled `credential_error`, enabling offline recovery. Save persists ordinary preferences and trusted stored pointers; caller-forged `credential_id/api_slots/active_api_slot` and `config.api_key` do not revive credentials. A new key must use the explicit argument.

Slot index must be a real int 0–2. `api_key=None` retains the key only for an already bound unchanged address; an empty string explicitly clears that slot; a new string creates a fresh ID and endpoint binding. `activate=True` activates and persists offline mode; false leaves the current active slot/mode unchanged. Successful slot setup sets `api_setup_complete=true`. Trusted internal callers may explicitly use `allow_key_reuse=True` to rebind a readable old key; UI/imported data must not silently enable this option.

Runtime `api_slots` contains three `{base_url,model,has_api_key}` records. Only the top-level active `api_key` is plaintext; do not print or serialize the complete returned object. Persisted slots instead contain `{base_url,model,credential_id}`, with an active index 0–2. Ciphertext is magic `NKC-DPAPI\x01` followed by CurrentUser DPAPI bytes. Its internal object has `format='nkc-api-credentials'`, version 1, `active_id`, `keys`, `endpoints`; random 32-character lowercase hex IDs connect keys to canonical full base URLs.

A key is usable only when its readable ID has an endpoint equal to the canonical slot address. Editing JSON cannot redirect an old key. Legacy unbound ciphertext is retained but disabled. Legacy plaintext is encrypted/read-back verified before removal, but remains unbound and needs re-entry. Bad connection metadata recovers to editable public defaults without binding the old key to them. Preference saves do not invent bindings.

Commit order is: write/verify a journal with old+new encrypted keys and bindings → atomically replace JSON pointers → best-effort compact orphaned encrypted records. Same-directory temporary files are flushed/fsynced before `os.replace`. JSON commit is the activation point. Failures are controlled and do not deliberately discard the previous source. DPAPI uses `CRYPTPROTECT_UI_FORBIDDEN`, without elevation or OS permission prompts. This is not protection from malicious software already running as the same Windows account.

## Configuration schema

Current ranges/defaults are in [LOCAL_TRANSLATION.md](LOCAL_TRANSLATION.md) and config/example.json. Existing API slots, DPAPI, appearance/languages and request limits remain. New settings: ocr_refine_workers, context_max_chars, context_history_records. Old strategy fields are compatibility data, not active routes.

## HTTP validation and OpenAI-compatible protocol

Pure functions in `security.py` are `validate_api_url`, `validate_model`, `normalize_api_key`, `validate_language`, raising fixed-message `SecurityValidationError`. They do no I/O/DNS. Engine/config layers convert errors to their controlled exception types.

| Input | Rules |
|---|---|
| URL | At most 2,048 chars; public HTTPS; lowercase/IDNA host, trailing host dot/default 443/trailing path slash normalized. Ports 1–65535. Reject userinfo, query, fragment, backslash, whitespace, Cc/Cs/Cf and decoded path controls. |
| Host | Reject localhost/.localhost/.local/.internal, single-label or malformed names, non-public/reserved/private IP literals and mixed numeric encodings. No DNS resolution or rebinding prevention. |
| Model | Nonempty string, at most 256 original chars, outer whitespace trimmed; reject Cc/Cs/Cf. |
| Key | Visible ASCII, at most 8,192 normalized chars; trim surrounding ordinary whitespace, placeholder becomes empty; reject internal spaces/non-ASCII/controls. |
| Language | ASCII BCP47-like segments, at most 64 chars, regex stated above. |

POST `{base_url}/chat/completions` with TLS verification, `Authorization: Bearer <key>`, `Accept: text/event-stream`, `Accept-Encoding: identity`, JSON content type. Owned HTTPX clients use `trust_env=False`, ignoring proxy/CA environment injection, and `follow_redirects=False`; every request also disables redirects. No automatic provider/slot failover. Pool/semaphore capacity is max_concurrency. A caller-supplied client owns its transport/lifetime but requests still disallow redirects.

The text-translation request contains exactly one fixed system message and one JSON-string user record with `source_language`, `target_language`, `context`, `text`. External input never creates another system message. The model is asked to translate text, preserve formatting/placeholders, and treat all record values as untrusted data. The key is not in the prompt. This translation-only request has no tools or output executor. The separate optional context request declares the single server-side search tool documented in CONTEXT_AGENT.md. Other fields are `stream=true`, `stream_options={include_usage:true}`, configured `max_tokens`, `temperature=0`, `thinking={type:'disabled'}`; compatible providers may differ in support.

New requests send normalized source text; terms and history are reference data, not local substitution. JSON escaping/data separation reduces role confusion but is not proof against every semantic prompt injection. A malicious instruction in game text remains data to translate and has no local command execution path.

### SSE and completion

The bounded parser incrementally checks raw transport chunks in at most 4,096-byte scanning pieces, decodes strict UTF-8 and recognizes CR/LF/CRLF across chunks. It rejects non-identity Content-Encoding before reading the body. Limits: 128 KiB per physical line, 20,000 lines, 8,192 data events, 256 KiB cumulative data bytes per event, 2 MiB response including ignored/comments/blank lines, and 64,000 cumulative output characters. Output rejects NUL, unpaired surrogates and non-CR/LF/TAB controls.

Comments and non-data fields are ignored. Blank lines dispatch multi-line data joined with LF. JSON events must be objects without error; content is read from `choices[0].delta.content`, and independent usage can update accounting. Wrong types, nontext content, empty choices, invalid UTF-8 or excessive nesting are not accepted as complete output. Invalid/negative/noninteger/out-of-int64 usage values become zero.

Success requires nonempty text, `finish_reason='stop'`, a complete `[DONE]` event and intact terminology placeholders. HTTP failures show fixed status explanations, never raw bodies. Truncated/length-ended/oversized/encoding-failed streams are not cached; upper layers remove partial overlays on failure. Timeouts use HTTP phase limits and per-attempt deadline checks on received blocks/lines; connect is at most min(8, configured timeout). Zero to two extra retries cover transport/timeouts and HTTP 408/429/500/502/503/504. Every retry reserves another request; backoff may emit empty output to clear the prior partial. Limits are not a currency cap.

## Storage compatibility

Existing glossary/translations/translation_scopes/game_profiles/shared_glossary tables remain as historical data; new successes update translations and append ai_context_events. Old learning tables remain to avoid destructive migrations but do not route translations. Tables use parameterized SQL and engine locking. No stored result directly substitutes for a new AI call.

## Diagnostics and related interfaces

`local_file_path(value)->Path` accepts only ordinary local files; detailed rules are in the input chapter. `PortableOcr.recognize(image)->dict` owns a hidden helper, private frame.bmp and bounded JSON protocol. `startup_record(error)->dict` returns schema/time/fixed message/error class/privacy plus at most eight basename/line/function frames. Identifier fields are sanitized and capped at 100 characters; no exception body, source lines, locals, complete paths or environment are recorded. `write_startup_report(root,error)->Path|None` atomically writes `startup-error.log` or returns None if unwritable without recursively logging its own failure.

The UI and input chapters specify remaining callback, file, image and lifecycle contracts. Report only reviewed/redacted evidence; never serialize an entire runtime configuration for debugging.


## Local interface-language API (i18n.py)

These methods translate application-owned UI strings only. Game source/results, keys and dictionary cells must not be passed through this localizer. There is no network call.

```python
detect_system_language(langid=None) -> str
initial_language(config, *, interactive=True) -> str
translate(value, language='zh-CN')
localize_widgets(root, language) -> None
agreement_text(language) -> str
class LanguageLabels(dict): ...
```

| API | Contract |
|---|---|
| `detect_system_language` | Calls `GetUserDefaultUILanguage`, selecting Chinese/English/Japanese by primary language ID. Does not inspect region, keyboard, IP or network. Unsupported IDs, non-Windows hosts, invalid supplied ID types or unavailable system calls yield `en`. An explicit int ID supports deterministic no-UI checks. |
| `initial_language` | Interactive startup uses a supported saved value only when `app_language_selected is True`; otherwise it uses OS preselection. The noninteractive test/guidance-suppressed path uses a supported saved value, otherwise `zh-CN`. No persistence or consent side effect. |
| `translate` | Converts controlled strings and named status templates through a local catalog; substitutions never evaluate code. Empty/non-string values pass through; unsupported language falls back to `zh-CN`. Not a general game-translation API. |
| `localize_widgets` | Tk-main-thread update of labels/buttons, tabs, column headings and window titles. It leaves Entry/Text bodies and data cells intact. App explicitly refreshes controlled status variables and agreement content separately. |
| `LanguageLabels` | Dict iteration remains canonical; item/get lookup additionally recognizes English/Japanese display aliases and returns stable translation-language codes. |
| `agreement_text` | English/Japanese select their disclaimers plus the original MIT; other values select Chinese. Display changes never write agreement version/acceptance time. |

`App.tr(value)` uses the current UI language. `show_language_setup()` creates/reuses the first-language dialog. `apply_ui_language(code)` validates the code and immediately refreshes widgets/status/agreement; unsupported codes raise `UIValidationError`. It does not accept an agreement. `open_manual()->bool` opens the local bundled HTML with the Windows default browser: Chinese uses PROJECT_MANUAL.html; English/Japanese use PROJECT_MANUAL.en.html. Missing files/open failures return false and show a controlled status. The settings entry point owns idle-time persistence; font/label appearance still applies when the next screen session starts.


## Continuous pixel-font paragraphs and buttons

Adjacent single OCR rows can form a complete paragraph when they share language, left alignment, similar height/colors and a tight line gap. Source text and one newline per row remain intact for tracking, translation input and cache identity. Production rendering retains the original physical row rectangles/count; paragraph grouping supplies context and does not authorize free-wrapping across those rows. Version 0.01.13 removed the arbitrary four-row split. Groups are bounded by 32 rows, 4000 characters including inserted newlines and a 4096-pixel union; a limit splits groups without truncating source text. Existing multiline objects are preserved. Font size remains based on the original row height rather than the complete paragraph height.

Large gaps, indentation, language/style changes and an intervening second column stop a group. A run consisting entirely of compact labels no wider than six times each row's height stays as separate objects, conservatively protecting menu buttons. Recognized noise in right-side artwork cannot be absorbed into a left paragraph. The Space Rogue geometry fixture verifies a ten-row left paragraph and a five-row lower dialogue as two objects. This verifies grouping, not spelling accuracy or universal game-layout compatibility.


## Fixed-image OCR and local pixel mode

```cpp
const char* gl_ocr_bgra(const uint8_t* pixels, int length, int width,
                      int height, const wchar_t* language);
```

This synchronous context-free entry recognizes supplied pixels without capturing or modifying frame hashes. Input is tightly packed BGRA, four bytes per pixel; length must exactly equal width*height*4. Dimensions are 1–4096, additionally limited by Windows OCR MaxImageDimension. The caller retains pixels/language during the call and supplies a valid MTA lifetime. Success is borrowed thread-local UTF-8 JSON with changed=true, capture_ms=0, ocr_ms, engine=windows-ocr and image-relative lines/colors; failure is an error object. Copy/decode before the next JSON-returning native call on that thread; never free it. GLRegion remains ABI 2/56 bytes, but both gl_set_font and gl_ocr_bgra exports are now required, so older DLLs cannot be mixed.

```python
NativeCore.recognize_bgra(bgra: bytes, width: int, height: int,
                          language: str='en') -> dict
OcrCore(dll_path=None, min_confidence=55, mode='auto')
OcrCore.recognize_image(image, language='en', mode=None) -> dict
place_image_result(result, x, y) -> dict
PortableOcr.recognize(image, language='jpn+eng', mode='standard') -> dict
```

The wrapper validates bytes, true integer dimensions, exact capacity and language tags. Invalid input raises ValueError; native errors become RuntimeError, with `_operation` lifetime protection. `recognize_image` reads the same caller-supplied PIL frame and returns relative coordinates; override mode is auto/native/pixel, with None selecting the instance mode and invalid values raising ValueError. `place_image_result` copies and offsets coordinates without rewriting text. `capture_ocr` captures BGRA once, recognizes that same image and adds the screen origin, avoiding mismatched second captures.

- auto: English low-palette, high black/white-contrast frames can use local pixel recognition; otherwise Windows OCR is preferred, with available portable fallback for missing Japanese/English system recognition. This is an image heuristic, not guaranteed font classification.
- native: only installed Windows OCR languages; no hidden component install or online switch.
- pixel: local English pixel recognition; Japanese retains standard jpn+eng processing. Missing required portable dependencies produce a clear error instead of pretending that precision mode ran.

The helper request adds mode=standard/pixel, default standard, and accepts eng/jpn+eng language. Existing restricted BMP/raw-RGB paths, JSON-line protocol, capacity and response schema remain. Pixel rereading is bounded to 32 candidate rows, two million crop pixels and at most two local scale variants per row; configured confidence filtering still applies. Engine diagnostics are windows-ocr, portable-tesseract or portable-tesseract-pixel. Portable results include min_confidence/rejected_lines in image-relative coordinates. These local interfaces never upload images.

## Optional AI image-reading API

`vision_ocr` is a strict boolean, default false. `vision_interval_ms` is an integer 1000–60000, default 3000. App creates VisionCore only when enabled with online mode and a usable key. `ocr_mode` is auto/native/pixel, default auto. Stop work and drain pending tasks before changing OCR/Vision settings and recreating recognition resources. Recognition and translation use the same active API slot/model, connection bound and request budget; saving settings sends no verification request.

```python
VisionRecognizer(engine)
VisionRecognizer.recognize(image, anchors, language='en',
                           *, cancelled=lambda: False) -> list[dict]
parse_transcription(content, anchors) -> list[dict]
VisionCore(core, engine, *, interval=3., settle=.45, recognizer=None)
VisionCore.capture_ocr(x, y, w, h, language='en') -> dict
VisionCore.pending -> bool
VisionCore.cancel_pending() -> None
VisionCore.reset() -> None
VisionCore.close() -> None
```

Input is a local PIL image plus existing anchors from that image: dimensions 1–4096, list/tuple with at most 512 anchors, string text up to 16000 characters, true-int x/y/w/h, positive boxes entirely inside the frame. Empty anchors cause no request. Convert to RGB, preserve aspect ratio with longest side at most 2048, then encode PNG up to 8 MiB. Each OCR hint is limited to 1000 characters and all description JSON to 131072. Request boxes are scaled for the uploaded image; displayed geometry remains in original local coordinates.

POST to the active `{base_url}/chat/completions` with its endpoint-bound authorization key, no redirects/environment proxies and identity encoding only. Recognition is nonstreaming: stream=false, max_tokens=4096, temperature=0, disabled thinking and JSON-object response format. A fixed system instruction asks for transcription only and treats image/OCR text as untrusted. user.content is an array containing a JSON text description and PNG base64 `image_url` data URL, detail=high. No external image URL or File API upload/remote file is used. Subsequent text translation retains the separate SSE protocol.

`deepseek-flash` is an example supported model. The official guide documents text-plus-inline-image content arrays for Chat Completions; another compatible provider may differ. [DeepSeek Vision documentation](https://api-docs.deepseek.com/guides/vision/)

Response bodies are at most 2 MiB of strict UTF-8 JSON with duplicate fields rejected, a nonempty choices array, message.content string and stop finish reason. Transcription content is at most 131072 characters and has form `{"lines":[{"id":0,"text":"source text"}]}`. Each nonblank line is at most 1000 characters without Cc/Cf/Cs/Zl/Zp, including line breaks, bidi controls and surrogates. IDs must be distinct existing-anchor integers, and result count cannot exceed anchor count. Model geometry cannot replace local bounds. Missing IDs retain OCR text; only text changes, preserving position, size, colors and confidence. No guessed new text boxes or executable actions are accepted.

The recognizer shares TranslationEngine's bounded slots and request reservation/usage accounting. Each actual request spends the same allowance. Controlled HTTP/JSON/cancellation/timeout failures raise TranslationError/VisionError; unknown failures become fixed wrapper messages without provider bodies. One failed recognition falls back locally without an internal retry loop; subsequent translation and its retries follow engine policy.

After local recognize_image returns, VisionCore copies the line dictionaries, sorts them by (y,x), and applies the existing strict layout._join_horizontal_fragments rules to long same-baseline narrative fragments. This precedes both anchor_signature and VisionRecognizer. Every anchor remains one physical row: there is no vertical paragraph merge or inserted newline at this stage, reducing repeated continuations when a model reads adjacent fragments of one line. Failure falls back to these locally joined rows with their union geometry, source text and colors; the original OCR input is not mutated. Plain OcrCore is unaffected by this wrapper change, and downstream Pipeline still performs the existing vertical paragraph grouping. The observed geometry changes from sixteen native fragments to fifteen physical rows, yielding the same ten-row and five-row paragraphs.

VisionCore has only one background recognition future while capture polling checks target/region/language and text stability. `anchor_signature(image, anchors, language)` hashes RGB image dimensions, all sorted local (x,y,w,h) boxes and the RGB union inside those boxes, returning (language,width,height,32-byte SHA256 digest). Limits are 512 boxes and 4096×4096; overlapping areas are merged into vertical bands and visited once, never exceeding one frame's pixels. OCR-guessed strings, pixels outside text boxes and DIB alpha are excluded. Invalid dimensions/bounds raise ValueError; the caller supplies the same RGB frame.

When full-image pixels change but the text signature stays equal, local anchors are revalidated without resetting the stability timer, canceling the request or clearing displayed output. That poll can still consume completed work. Eligible in-box pixel changes, added/missing/relocated eligible boxes or language changes advance generation; previously published rows survive only with exact current per-row evidence. Focus loss/stop explicitly cancel. Screen-region origin/dimension/language changes reset raw capture for revalidation; matching text can reuse a cached result relocated to current x/y without modifying cached coordinates.

Two LRU maps each hold 16 entries: full-frame RGB digest to text signature plus associated preserved rows, and text signature to recognition result. A valid shortcut/result skips local OCR and API work. Success has no TTL; failed local fallback lasts 30 seconds, checked on re-entry/reappearance rather than a periodic retry timer. Target/text-generation checks still apply. Recognizers receive deep-copied anchors so failure preserves original geometry/colors. Pending means unfinished work; cancellation prevents application but cannot refund sent requests. Close cancels this wrapper's pool with wait=False and closes its core, never the game. Missing local anchors cause no speculative model recovery. Engine diagnostics are vision-waiting, vision+local and local-fallback with controlled vision_error.

Two long same-baseline English fragments can first rejoin with one space before vertical grouping. Height difference must stay within 15%, baseline within 12% of row height and horizontal gap within twice row height; each fragment spans at least six row heights and the union at least sixteen. Colors/language must match, both parts need at least two words, the right part starts with a lowercase continuation, and an adjacent aligned narrative row must span at least 75% of the union. Without that evidence, fragments remain separate. No game vocabulary is hardcoded; title-style buttons, unsupported fragments and columns do not join. The real sixteen-anchor geometry fixture yields the same ten-row left paragraph and five-physical-row lower dialogue.

Pipeline keeps at most 512 raw OCR rows, applies language routing and paragraph grouping, then enforces max_objects (1–32). Reducing the object limit no longer truncates a paragraph to its first few raw lines before grouping.


## Request-count policy (retained from 0.01.14)

`TranslationEngine(config, db_path, *, client=None)` reads `unlimited_requests`, defaulting to `False`. Only a real `bool` is accepted; strings, numbers and `None` raise a controlled `TranslationError`. The switch never overrides offline/missing-key network prohibition, changes the network semaphore, response bounds, retry count or timeouts.

- Finite: before each send or retry, the locked reservation checks `session_requests < max_requests`, otherwise raising `BudgetExceeded`. A limit of zero sends no new request.
- Unlimited: `_reserve_request()` skips only count rejection, while incrementing session/cumulative accounting under the same lock. Image recognition and translation share this entry point. There is no hidden 10000-request cap; 10000 bounds only the finite setting.
- `get_stats()` adds `unlimited_requests: bool`. `requests_remaining` is `max(0,max_requests-session_requests)` as an integer in finite mode and `None` (JSON `null`) in unlimited mode. Consumers must branch on `None`, rather than treating it as zero or subtracting it. Request/failure/token/cumulative counters remain active.
- This is a computational/network setting, not an `APPEARANCE_FIELDS` entry. Busy UI saves are refused; an idle save rebuilds the engine and restarts its session counter without clearing the dictionary or persistent collection progress.

## OCR quality gate and source pixels (0.01.15)

```python
from nkc_galgame_translator.ocr_quality import rejection_reason
rejection_reason(text: str, source_lang: str) -> str | None
```

This pure local function does not rewrite input, return corrected text, access the network or read/write dictionaries. Multiple confusable-error signals in a short English UI phrase return the fixed code `suspect_ocr_menu`; otherwise it returns `None`. It applies only to `en` and `en-*`; other language selections pass. Unknown proper names, game terms or unlisted words are not a rejection reason on their own. Matching bounds are specified below.

Pipeline calls it after per-row language routing and before paragraph grouping. Rejected rows retain `text` and gain internal fields. These fields are not writable model-response fields and do not enter translation-memory keys.

| Field | Type/value | Contract |
|---|---|---|
| `line._preserve_source` | bool; `True` when preserved | Keep the game's pixels. Do not draw the OCR string or enter `TranslationEngine.translate`. |
| `line._ocr_rejection_reason` | Fixed string | `suspect_ocr_menu` for rule evidence; `overlapping_rejected_region` when preserving an entire intersecting box. |
| `Pipeline.get_stats().preserved_source` | Non-negative int | Current visible preserved-box count, not a cumulative request count. |

Layout treats rejected rows as horizontal and vertical merge barriers. Accepted original/grouped rectangles that intersect rejected geometry are also preserved, preventing a final background rectangle from covering source text that should remain visible. ObjectTracker immediately increments `revision` on quality transitions; the minor-OCR-edit delay does not apply when either side is rejected. Pipeline scheduling and current-state lookup skip preserved boxes. `OverlayState.apply_objects` removes old overlays immediately; `apply_translation` rejects their late chunks and final output. A later acceptable recognition can produce a new translatable revision.

No new event kind is introduced: existing `objects` snapshots carry the preservation state. No fake translation or faulty OCR string is painted as source. Unlimited mode cannot bypass this screen gate. Historical records do not override a rejected box; the feature does not bulk-delete the dictionary. Other previously started valid work may still complete and write its own result; this does not promise to retract every dispatched request. Manual text translation remains available. Optional upstream Vision image reading may still issue recognition requests.

### Matching bounds

- Language tags are case-insensitive and limited to `en` / `en-*`. Input is at most 4096 characters and 32 `splitlines()` physical lines. This rule does not reject larger inputs; existing input-size bounds remain independent.
- Each original row and its NFKC/trimmed form must be at most 160 characters, with 2–8 words of at most 32 characters each. A match on any row preserves the entire input object.
- A fixed set of common menu/action phrase anchors requires at least 2 damaged content words. Bounded confusable edits cost at most 2 steps per word and 4 per phrase. Supported evidence includes selected visually confusable characters, adjacent transposition and dropped menu-hotkey initials; arbitrary spelling correction is not performed.
- Legal hotkey forms such as `(N)ew`, `[N]ew` and `S(a)ve` are understood as their original word without returning replacement text. Correct text, unknown words/names, a single typo and non-English text are not rejected by this rule alone.
- Word-pair distance results use a process-local LRU of at most 1024 entries. It is not a translation dictionary and never writes to SQLite.

These are conservative heuristics, not complete spelling or semantic validation. Passing the gate does not prove that OCR is correct.

Preservation metadata is recomputed locally; same-named fields from OCR responses are not trusted. If previously smoothed geometry would intrude into rejected source geometry, OverlayState falls back to the current raw box before drawing accepted content.

## Legacy diagnostic reflow and mixed wrapping

This section describes the compatible non-fixed path. Production Pipeline sets `_fixed_layout=True` and uses the source-row contract at the end of this chapter instead.

```python
from nkc_galgame_translator.layout import reflow_translation
reflow_translation(text: str, final: bool = True) -> str
```

| Layer / field | Contract |
|---|---|
| `merge_dialogue_lines()` / `line._flow_layout` | `True` only on locally grouped continuous-prose paragraphs; source `text` retains the newline between physical rows. Existing multiline objects, compact button runs and list/field/speaker rows do not gain reflow from this rule. |
| Raw Pipeline observation | Discards an incoming `_flow_layout` and derives it again from local grouping evidence. Model output cannot choose layout policy or expand geometry. Disabling paragraph grouping does not generate the flag. |
| `reflow_translation()` | Applies only to compatible non-fixed output with that flag. CRLF/CR normalize to LF; soft single newlines disappear. Adjacent Han/Kana or their punctuation need no inserted space; other text boundaries use one space. Existing within-line spaces remain. |
| Paragraphs / lists | Two or more newlines become one blank line. Bullet/numbered list starts keep a preceding newline. Source list, field/speaker-label and tab-structured rows block prose grouping. Existing multiline source objects retain their previous newline policy. |
| Cumulative streams | Holds undecided trailing whitespace and potentially incomplete list markers until later characters establish their role; a final result completes normally. A standalone newline chunk need not move existing text repeatedly. |
| Pipeline presentation | Legacy diagnostics may reflow before labeling. Production fixed-row output bypasses this reflow and uses native source slots. A layout-flag change reformats existing output without translating again. |
| Storage / scheduling | Does not rewrite translation input, dictionary source/target text, cache keys, IDs or revisions. Makes no new API request. Quality gating, stale-result rejection and geometry stabilization remain applicable. |

C++ retreats to a Latin word's beginning only when the measured break falls inside that word; it no longer retreats to any earlier space ahead of CJK continuation. Common CJK closing punctuation stays with the preceding glyph and opening brackets with the following glyph when space allows. Very narrow rectangles still make progress and retain the 8px floor/`fits=false` behavior. UTF-16 surrogate pairs are not split. Explicit LF breaks, overlay rectangles, the same-object/revision no-enlargement rule and GLRegion ABI 2/56 bytes remain unchanged.

`gl_overlay_snapshot().regions[].lines[]` adds integer `start` and `length`: UTF-16 offset and visible row length in the rendering input after CR removal, excluding trimmed trailing spaces. Existing `y/width/height` fields remain. No source/translation copy or screenshot is returned. These offsets support controlled break-point regressions; they are not Unicode code-point indices.

## Content value and stable coverage (retained from 0.01.17)

```python
from nkc_galgame_translator.translatability import preservation_reason, unchanged_translation
preservation_reason(text: str, source_lang: str = 'en') -> str | None
unchanged_translation(source: str, translated: str) -> bool
```

| Interface / field | Contract |
|---|---|
| `preservation_reason` | At most 4096 input/NFKC characters and 32 physical lines. Returns a reason only when every nonempty row qualifies; any ordinary row keeps a multiline object eligible. Invalid/oversized inputs remain the caller's validation responsibility. |
| `nonlinguistic` | Empty, numeric or symbol-only rows, independently of language. Original pixels are retained, not redrawn from OCR. |
| `isolated_key` | In explicit English scopes: isolated Latin letters, F1–F24 and known key abbreviations. Ordinary Enter/Space/Shift words require matched keycap wrappers. |
| `hud_code` | Bounded 80-character known abbreviations, measurement values, explicit HUD-prefix/value codes and clock formats. Uppercase alone is never evidence. |
| `glyph_noise` | Isolated 3–24-character Latin strings with identical repeated thin glyphs such as iii/lll/111. Mixed i/l runs alone do not reject normal words such as million or illusion. |
| `nontranslatable_rows` | Every row qualifies but individual rows have different reasons. |
| `unchanged_translation` | Raw source/output and normalized results each ≤64000 characters. Nonempty equality after NFKC/casefold/whitespace normalization; does not strip punctuation, labels, brackets or diacritics or rewrite dictionary data. |
| `_translation_unchanged` | Pipeline adds true only for a complete unchanged raw result. Ordinary events omit this field. Comparison precedes reflow, source labels and outer brackets. |
| `OverlayState._unchanged` | Current object ID→revision completed-display sentinel. Final identity clears coverage and rejects late same-revision partials; missing/new/preserved objects or clear remove it. Not persisted. |

Content preservation uses the existing `_preserve_source` barriers, overlap protection and revision rules. It applies to screen OCR, not the manual text-translation interface. A cumulative partial equal to the raw source emits empty display text; only the final identity event establishes completion. A later genuinely different complete result can still display. The post-translation identity decision does not undo requests, success counters or database commits.

### Atomic rectangle confirmation

`OverlayState._stable_geometry` accepts x/y/w/h as one rectangle. A dimension change over 2px waits with its position for three similar candidate boxes (2px tolerance). A move over 6px with stable dimensions follows immediately. Persistent 1–2px changes require three identical candidates instead of being ignored forever. Candidates use capture-relative positions; moving the game window shifts accepted geometry first. Colors follow observations and font-size filtering remains separate. If a previously smoothed box overlaps a neighboring object/preserved region that raw current geometry avoids, use the raw box. Missing objects still hide immediately.

### Reusable native paint buffer

Each OverlayWindow owns a compatible DC/bitmap, reused for same-size streaming updates and reallocated when dimensions change. Background and text are rendered there before a single BitBlt commit. Failure may use direct drawing; destruction restores selected objects and releases GDI resources. Font metrics, masks, target restrictions and click-through behavior are unchanged; C ABI remains 2.

`gl_overlay_snapshot().regions[].paint` is read-only diagnostics: `buffered:bool` reports the last paint's buffered commit; `buffer_allocations:int` counts successful allocations in that window; `size:[width,height]` is the buffer's pixel size; `commits:int` counts successful buffered commits. These support owned-window reuse/resize checks, not measured live DWM flicker or promised frame rates.

### VisionCore per-row preservation and early gates (retained from 0.01.17)

Local OCR rows undergo source-language routing and quality/content-value checks before permitted horizontal joining. Preserved rows are barriers; eligible boxes overlapping them are also preserved. These rows are excluded from AI anchor lists and the text signature, so meaningless HUD counter changes do not reset useful text's settle timer or cancel its first recognition request. With no eligible anchors, no AI request is made. If eligible anchors remain, the selected game-region image is still uploaded: **ignored pixels are not redacted or cropped away**.

Current preserved rows accompany useful recognized rows when publishing, preventing downstream paragraph joins across their rectangles. The raw-frame cache still has 16 entries, each associating the text signature with its preserved rows. `_published` keeps eligible physical rows only. Per-row evidence contains language, frame size, exact x/y/w/h, bg/fg and a SHA256 of current RGB pixels. At most 512 rows and one frame's total unique crop pixels are hashed per pass; over-budget rows cannot carry over. This retains digests, not another persistent image copy.

While a changed whole-text signature waits, only old physical rows with this exact current evidence plus current preserved barriers are published. New/changed/missing rows are not retained; focus cancellation/reset clears published state. Existing Pipeline tracking/cache then renders those observations; this is not a stale-overlay timeout. VisionCore honors configured auto/native/pixel recognition instead of forcing system OCR. Auto adds a low-palette, dark-majority, strongly concentrated colored-HUD branch; explicit mode choices still win.

## 0.01.20 — Cell and source-row layout interfaces

### Local OCR geometry

Windows OCR uses actual `OcrLine.Words`; the independent Tesseract helper uses `WORD` boxes. A same-row gap of at least `max(24px, 3 × physical-row ink height)` may separate distant cells. Splitting precedes pixel-text refinement so a later OCR pass cannot glue a name and its price back together. Coordinates come from local pixel/word evidence, not translation length or estimated character widths.

| Field | Coordinates and contract |
|---|---|
| OCR `separated_cell` | Optional strict bool for a locally split distant cell; not model-supplied metadata. |
| Native OCR `ink_bounds` | Optional `[x,y,w,h]` unpadded word-union bounds relative to the input image; legacy `x/y/w/h` retain padded coverage bounds. |
| OcrCore `_layout_cell` | Locally derived `True`; blocks both same-baseline narrative rejoining and vertical paragraph grouping. |
| OcrCore `_source_ink` | Real ink bounds, image-relative from `recognize_image`; `place_image_result` adds the capture origin exactly once to produce screen coordinates. |
| `_source_rows` | Physical source rows created by local paragraph grouping, described below; not remotely selectable geometry. |

Background sampling uses the cell's own row margins so a selected inverse-color row does not borrow its neighbor's background. Undetected entries are not invented from artwork.

### Table and list protection

```python
from nkc_galgame_translator.layout import mark_table_values, has_numeric_table_evidence, merge_dialogue_lines
mark_table_values(lines: list[dict]) -> list[dict]
has_numeric_table_evidence(line: dict) -> bool
merge_dialogue_lines(lines: list[dict]) -> list[dict]
```

`mark_table_values()` copies rows without changing source text or geometry. It considers at most 512 rows and requires at least three aligned label/value pairs, including two digit-bearing values. A value has at most six restricted numeric/confusable glyphs; a letters-only value has at most two characters. Values span at most four row heights and sit at least three row heights after their label. Label-left/value-right alignment tolerance is `min(12px,.35h)`, height ratio at most 1.25, and adjacent vertical distance at most `3.2h`. Newly protected cells receive `_preserve_source=True` and `_ocr_rejection_reason='numeric_table_cell'`; existing rejection reasons remain. A normal header such as `Cost` is not treated as a value just for standing above the column.

Confirmed local values also carry `_numeric_column=_TableEvidence.NUMERIC`, a string enum with value `numeric_table_cell`. `has_numeric_table_evidence()` checks enum-member identity, preserving known prices while Vision initially publishes barriers without their left labels. Internal deepcopy retains identity. Diagnostic JSON may serialize the value as a string, but a subsequently supplied ordinary string is not trusted evidence; a provider/JSON field cannot forge this marker.

A separate list-evidence path requires at least three aligned compact Latin labels, each at most three words/40 characters and without narrative continuation words/punctuation. At least two one-word entries or an aligned numeric partner are needed. Left alignment tolerance is `min(12px,.35h)`, height ratio at most 1.25, and row gap at most `1.6h`; inverse selection colors do not invalidate this list evidence. It prevents entry gluing without rewriting text or coordinates. Numeric/symbol rows remain layout barriers and do not reach the translation engine. Accepted narrative paragraphs may still share translation context.

### Python source-row contract

```python
from nkc_galgame_translator.native import fixed_source_rows
fixed_source_rows(region: dict) -> list[_SourceRow]
```

Production Pipeline sets `_fixed_layout=True` and derives `_source_line_count` (1–32) from local source text. It discards incoming `_source_rows`; local grouping reconstructs physical rows. `_flow_layout` remains narrative provenance, not an instruction to freely reflow production display. Manual translation and dictionary source/output/cache keys are unaffected by the display policy.

Each `_source_rows` item is `{x,y,w,h,font_size, ink_bounds?}`. All coordinates are relative to the parent overlay. Row bounds are nonempty integer rectangles contained by that parent. Optional `ink_bounds=[x,y,w,h]` is also parent-relative and contained by the corresponding row. `font_size` is 0–512; zero asks native code to calibrate from source ink height. A grouped paragraph records each actual physical OCR row; total paragraph height is not font size. A single separated cell can supply an implicit row, with screen-relative `_source_ink` rebased by the parent origin.

A legacy multiline object without physical bounds receives `_source_line_count` equal-height slots inside the parent, with count no greater than pixel height. This is a compatibility fallback, not precise OCR evidence. Without `_fixed_layout`, the helper returns no rows. Invalid geometry/size raises `ValueError` before the DLL call; native code separately validates totals, offsets and intersecting ink bounds.

### Additive C ABI: `gl_overlay_fixed`

```cpp
struct GLSourceRow { // Windows x64: 36 bytes, 9 int32_t fields
    int32_t x, y, width, height;
    int32_t ink_x, ink_y, ink_width, ink_height;
    int32_t font_size;
};
int gl_overlay_fixed(void* context, const GLRegion* regions, int count,
    const GLSourceRow* rows, int row_count, const int32_t* offsets);
```

`GLRegion` remains ABI 2 / 56 bytes. This additive entry leaves legacy `gl_overlay` available. `offsets` has `count+1` entries, begins with zero, ends with `row_count` and never decreases. Each region has 0–32 rows: zero selects legacy layout; otherwise source rows constrain layout. Limits are 512 regions and 16384 total rows. Parent/row/ink rectangles are nonempty and contained by their parent; ink rectangles within a region cannot overlap. Font size is 0–512. Existing text/batch limits remain, and the fixed entry also rejects malformed UTF-16 surrogate sequences.

The caller keeps arrays, strings and pointers readable through the synchronous call. Return 1 accepts a snapshot for asynchronous drawing; return 0 leaves the batch unsubmitted and exposes a fixed diagnostic through `gl_error()`. Fixed-layout calls require this version's export; the wrapper does not silently fall back to the old layout. A fixed region partially clipped by the target client area or virtual desktop hides instead of shifting its source-row origin.

Final text with exactly the source row count of explicit lines uses those lines. Otherwise native code allocates text from measured glyph advances and source ink widths, preserving supported Unicode clusters and preferring word boundaries. Each allocated row is bounded to 8192 UTF-16 units; a larger row also counts as not fitting. One object shares the largest fitting font under the ceiling derived from stable median source ink height, explicit sizes and reusable same-revision history; a substantial geometry correction permits recalibration. Final spare width is distributed between clusters; partial streams retain natural advances. One cluster cannot be justified and stays at the original ink start. Final masks cover the union of source row rectangles, not inter-row gaps or unrelated parent blank space. If no fit exists at 8px, `fits=false` and an empty mask preserves game pixels.

Snapshot additions are `regions[].fixed_layout:bool`, `source_rows:int`, and per-line `x`, `ink_y`, `ink_height`, `clip:[x,y,w,h]` relative to the overlay. Fixed-layout `start/length` are accumulated UTF-16 spans of the allocated, trimmed rows; they are not slice offsets into the original newline-containing provider string. Legacy offsets retain their CR-removed meaning. Existing `paint` diagnostics remain. Snapshots contain no source/output copy or screen capture.


## 0.01.20 whole-frame geometry and Aero diagnostics

`OcrCore(refine_workers=2)` refines measured regions only after complete-image discovery; workers 1–8. Observations add `ocr_stages=['whole_frame','measured_cells','parallel_ink_refine']`, `refine_workers:int`, `region_refine_ms:float`. All refinement uses the same image, at most 512 regions and min(image pixels ×2,4000000) pixels of work.

`refine_ink` updates only `_source_ink` with reliable flat-edge evidence and preserves a 1px antialias fringe. Complex uncertain texture retains measured geometry. `separator_above` tests nearly flat horizontal rules between overlapping rows, requiring at least 85% span and contrast 48 against bg. `_row_boundary` is an internal enum; a JSON string with that name is not trusted evidence.

Layout identifies non-overlapping prose-column chains of at least three rows with prose evidence. Visual rules, short endings/new wide rows, menus and prices prevent unwanted joins. Groups retain `_source_rows`, so semantic grouping does not add or relocate display rows. Arbitrary layouts are not guaranteed perfectly recognized.

The `gl_overlay_fixed` ABI is unchanged. Capture retains an immutable BGRA frame of the selected region. A foreground/antialias glyph mask selects local repair pixels. Background RGB outside that mask is byte-identical; there is no whole-row interpolation, blur or added highlight. Repair proceeds inward from edges, preferring opposing sample directions with smaller color discontinuities to preserve structures crossing text. The opaque patch is cached by frame, row geometry and colors, within a 64MiB total texture budget. Each patch is at most 1048576 pixels and source ink totals at most 524288 pixels; larger regions hide their overlay.

Dense/missing foreground, a foreground-colored shape extending outside the ink region, or incomplete repair retains original pixels and suppresses translation. It does not forcibly erase ambiguous rings or borders. Production fixed-row rendering hides the region when source coverage or repair budget is unavailable; legacy non-fixed diagnostics retain solid-color drawing. The model cannot supply erase masks or out-of-bounds samples. Occluded detail remains an approximation, not a guarantee for arbitrary artwork/fonts.

Region diagnostics add `aero:bool`, `background_opaque:true`, `background_frame:uint64` and `background_builds:uint64`. Additional fields are `background_suppressed:bool`, `background_mask_pixels:uint`, `background_repaired_pixels:uint`, `background_reason:str` (success: glyph_mask_repaired; otherwise controlled fallback reasons). `aero=true` indicates a usable repaired background that is not suppressed. Suppressed regions do not draw translation glyphs. Existing fixed_layout/source_rows/font_px/fits/paint/lines/clip remain compatible. No source/result text or raw pixels are exposed in the snapshot.


### 0.01.20 foreground colors and repair limits

On flat backgrounds, `ocr_regions.py` considers at most 4096 candidate colors. A high-contrast dominant color and nearby colors must cover at least 25% of ink before measured `fg` is supplied to the native glyph mask. This supports colored glyphs as well as white/black text. Complex texture, similarly colored artwork or an unreliable dominant color may still suppress translation and retain the original image; arbitrary colored fonts are not guaranteed.

Background caching includes `fg`, so a changed foreground does not reuse a stale mask. Controlled reasons are `glyph_mask_repaired`, `foreground_missing`, `dense_foreground`, `foreground_leaks_boundary`, `repair_incomplete`, `source_unavailable`, `repair_budget`, `allocation`, `budget`, `no_frame`. Byte-identical RGB outside the glyph mask refers to the background layer; normal translated glyph drawing still covers its own text positions.

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

## Window movement contract

`gl_overlay_anchored(context, regions, count, rows, row_count, offsets, origins)` is an additive ABI 2 export. The first six arguments follow `gl_overlay_fixed`; `origins` contains `2*count` int32 capture-origin coordinates. NativeCore validates each region's `_capture_origin` and uses this entry when all regions supply it. Coordinates never come from model output.

Submission converts absolute OCR coordinates into game-client-relative positions. A native 16 ms timer moves overlay HWNDs without OCR, translation, refitting or activation. Late tokens with old capture origins remain at the current window position. The timer interval is not a scheduling-latency guarantee. Background sampling rebases into its source frame's client origin. Resize hides old geometry until fresh layout; focus loss, minimization and out-of-bounds placements hide overlays.

Transient capture movement, resizing or an unavailable first frame returns `changed:false,pending:true,lines:[]`. OcrCore/VisionCore forward this status; Pipeline retries without confirming stale rows or submitting translation. Nonrecoverable errors still stop capture and report failure.

### Response-speed interfaces (0.01.21)

`ParallelDiscovery.submit(working: PIL.Image, language: str) -> Future[list[dict]]` submits one supplemental SPARSE_TEXT whole-frame scan to a private single-worker executor. The caller must await it before releasing the image, including primary-failure paths. `close()` waits before releasing the engine. The caller runs the primary scan.

`RegionalRefiner.refine(working, lines, language) -> list[dict]` preserves order; at most the first 64 eligible low-confidence rows and 2,000,000 crop pixels are refined. The 256-entry LRU key contains language, raw text/confidence, crop size and SHA-256. Values contain only text/confidence. Current geometry, backgrounds and cell flags are retained. The helper loop owns cache mutation; workers do not access it. Close clears the cache.

`PERFORMANCE_PRESETS: dict[str,dict[str,int]]` has responsive/balanced scheduling fields. `SettingsPanel.apply_performance_preset(name)` fills idle controls; it does not save, start tasks, issue requests or alter credentials. The existing validated save workflow persists settings.

`TranslationEngine.get_stats()` adds `first_token_samples: int`, `first_token_total_ms: float`, `last_first_token_ms: float | None`, and `mean_first_token_ms: float | None`. They measure each HTTP attempt to its first nonempty content delta, excluding queue/OCR/UI time and previous retry waits. Attempts failing after a first token still count; attempts without a token do not. A lock protects aggregates; no keys or raw responses are persisted.

### 0.01.22 cache and stream contracts

`FrameCache(max_bytes=134217728,max_entries=16)` is an in-process LRU owned under OcrCore's RLock. `key(bytes,scope)` combines SHA256 with dimensions/language/mode/confidence; `get(key,bytes)` still checks exact bytes and returns a deep copy or None. `put` charges RGB length plus 1 MiB per result, evicts oldest entries, and skips oversized items. `clear` releases entries and accounted bytes on close. This is OCR evidence, not persisted translation substitution.

`recognize_image` adds `frame_cache_hit: bool`. On hits `ocr_ms` measures retrieval and `region_refine_ms=0`; `ocr_stages` describes original provenance, not work repeated now. Private pipeline observations carry monotonic `captured_at` and `confirmation`. Only a subsequent unchanged capture allows OCR time to count toward settling. New revisions reset confirmation and stale generations remain rejected.

TranslationEngine stores only the latest cumulative partial in `_flight_chunks`, under its lock. Followers poll at about 8 ms, may coalesce intermediate chunks, and receive the final Future result. Finally clears success and error state. Existing public and native ABI contracts remain unchanged; polling intervals are not OS/network timing guarantees.

## 0.01.23 local RGB contrast interfaces

The independent MIT OCR helper adds `color_contrast(image,background)`, `flat_color_frame(image)`, `find_contrast_rows(image)`, `read_contrast_rows(engine,tesserocr,image,language,regions,cache=None)` and `ContrastCache`. GUI JSON and native ABI are unchanged.

RGB channel-distance normalization uses an 8-level noise margin and a 4x mapping, preserving chromatic differences even at similar luminance. Whole-frame color normalization requires a measured background share of at least 80%; local rows require measured flat edges and contrasting surroundings. Detection accepts RGB images of 1–4096 pixels per dimension, examines at most 256 candidate rectangles and returns at most 8. Rows are 10–128 pixels high, at least 48 pixels wide and at least twice as wide as high. Ink occupies 2.5%–50%. Per-crop area is at most min(1 million, frame/3), aggregate at most min(2 million, frame/2).

Local SINGLE_LINE recognition tries native scale and, when needed, half scale. It accepts confidence >=70, maps actual word bounds back using measured resize ratios and clamps to the detected rectangle. Only uncovered cells are appended. The output remains bounded to 512 boxes / 16000 characters each / 64000 total. Original RGB, foreground/background sampling and source-ink geometry are unchanged.

ContrastCache uses language, dimensions, SHA256 plus exact RGB byte equality; 64 entries / 16 MiB including a conservative 1 MiB result allowance per entry. LRU eviction applies. Results are crop-relative and rebase on the current detected row; successful empty results may be reused, exceptions are not cached. Text/color/size/language changes invalidate reuse.

Pixel mode enables this path; auto also routes flat chromatic text to it. Forced Windows OCR retains its native engine. No new network calls, threads, dependencies or settings. Ambiguous textured/gradient backgrounds and unbounded selections may still be missed; no game-specific word substitutions are used.
