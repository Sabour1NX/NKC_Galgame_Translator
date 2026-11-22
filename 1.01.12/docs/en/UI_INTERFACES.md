# UI interfaces and asynchronous state

## 0.01.27 CUDA runtime and prewarm contracts

Optional components lock ONNX Runtime GPU 1.32.0, RapidOCR 3.10.0, CUDA 13.x runtime / cuDNN 9.x. RTX 3070 / driver 617.42 was verified locally; this does not certify other combinations. Wheel/model hashes are fixed. Detection and recognition provider arenas share the configured budget, totaling 1 GiB by default, with additional driver/runtime memory.

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` retains disabled-by-default low-level call compatibility; App passes the enabled user-setting default and may transfer a prewarmed `CudaOcr` instance. `App._prepare_cuda()` runs local `warmup()` in a background thread without screen capture or API requests, reusing the helper for later OCR. Prewarming does not eliminate first-inference cost for every new image shape.

## 0.01.27 CUDA recognition and actual fallback

The first-run language page and regular settings share CUDA controls. `cuda_enabled` defaults to true. CUDA is attempted only in **Auto OCR mode** for English, Japanese or Chinese. Explicit Windows / Pixel modes use CPU. Auto also prioritizes the CPU Pixel route for detected classic English pixel frames when the portable engine is available (`pixel_priority`); other languages use existing local OCR. Missing components, incompatible hardware, invalid models or failed inference fall back to Windows / Tesseract with actual status. Installed files do not prove GPU execution. A failed OCR instance does not repeatedly retry CUDA; stop and restart after changing settings.

| Setting | Default | Range and meaning |
|---|---|---|
| `cuda_enabled` | `true` | Enable/disable; no automatic component downloads |
| `cuda_quality` | `75` | 0–100, performance to accuracy; linearly adjusts detector input limit with 32-pixel quantization |
| `cuda_memory_mb` | `1024` | 256–16384 MiB inference arena budget; does not force allocation of 1 GiB; runtime/driver overhead is additional |

The detector long-side limit is approximately `768 + 11.52 × cuda_quality`, rounded to a multiple of 32; 75 selects 1632 pixels. Only larger images are downscaled, so settings can be equivalent for small images. The slider is not an accuracy percentage and does not guarantee monotonically better accuracy or speed. The model is PP-OCRv6-small. Consult this version's GPU/dependency results rather than assuming every NVIDIA GPU works.

With optional cloud image refinement enabled, CUDA rows with confidence at least 95 and no rejection marker can proceed directly to translation; other rows remain on the verification path. **95 is a model-score threshold, not a measured 95% accuracy promise.** Local CUDA OCR uploads no image; cloud refinement remains a separate opt-in image-transfer path.

## 0.01.27 window identity and runtime status

`window_metadata(hwnd, paths=None)` returns `hwnd,pid,title,process_path,exe_name,class_name`; list refresh shares process-path queries by PID. `translation_target(row)` filters metadata, without a game-title/engine allowlist. Explorer, desktop, taskbar, shell/helper windows and the application's overlay are excluded. Entries display “title · executable · PID”.

`App.chosen_window()` rereads metadata and validates HWND/PID, rejecting stale identities and shell/helper targets. `window_state(hwnd, expected_pid)` returns `closed / replaced / minimized / hidden / background / active`, without opening the process. `App._refresh_running_status()` runs at most once per second and combines target state with pipeline events to distinguish waiting, recognition, no text, AI requests and displayed translations. Actual errors stay latched until stopping/restarting. A status label is not evidence of completed translation: background/minimized targets and invisible selections are not captured for translation. Language settings, 1–8 selections, screenshot options, fonts and character spacing remain unchanged.


Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

## 0.01.27 context boundary

The optional background context layer uses the single DeepSeek server-side search tool; display translation requests have no tools and do not wait for new search. Both layers share request/concurrency/token accounting. Source text, excerpts, pages and notes remain untrusted. Returned links are never fetched by the client and cannot change source geometry. See [CONTEXT_AGENT.md](CONTEXT_AGENT.md) for exact payload, metadata, timeout and cache contracts.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## Multiple selections and automatic font styles

Choose a game window and click **Select region**. Drag repeatedly to add **1–8 non-overlapping rectangles**. Press **Enter to confirm**, Backspace or right-click to undo the last rectangle, or Esc to cancel without changing the previous selection. Minimum rectangle: 20 × 20 pixels. Combined bounds: at most 4096 pixels per axis. Keep each complete paragraph inside one rectangle with a small margin. Selections follow the game client, clip on resize and reset to the whole client when choosing a different game window. Selections last for the current UI session.

One captured frame serves all selections. Gaps between rectangles are blacked out before OCR or optional AI image reading. Grouping and tracking do not cross selection boundaries. Adding regions does not start independent OCR processes or change translation concurrency. Use windowed mode when needed.

In **Settings → Translation appearance**, enable **Match the source font style automatically (target-language support)**, save and restart translation. Local screenshot evidence approximates pixel, serif, sans-serif or monospaced style. Each box checks the installed font against the target script and actual translated characters. No font downloads are needed. This option defaults to off; disabling it restores the manual font. Size fitting and minimum/maximum sizes remain independent settings.

This matches broad style, not the original font file. Decorative text, complex backgrounds, short words and OCR mistakes can affect classification. Missing glyphs trigger an installed compatible fallback; if none exists, the original remains visible. Automatic coverage checking conservatively supports BMP characters. A box containing supplementary-plane characters or emoji retains the source; manual font mode remains available with Windows fallback.

State: `capture_region` stores rectangle tuples; `capture_region_target` stores HWND/PID. Esc leaves state unchanged; Enter commits together. A changed target clears the old selection.

All Tk widget operations run on the main thread. Internal package names remain `nkc_galgame_translator`; no cross-version interface guarantee is made. This chapter contains no personal keys or private paths.

## App and lifecycle

`App(*, show_setup=True)` constructs five pages, ConfigStore, an event queue and presentation state. `show_setup=False` suppresses automatic guidance only; it does not waive agreement checks or enable a missing key. The first-language chooser precedes agreement/API guidance, stores only language preference/selection, and sends no request. Saved interface language wins over supported OS detection. Interface-language saves apply to widgets immediately without restarting the program; active work must first be stopped.

| Method | Contract |
|---|---|
| `show_api_settings()` | Return dialog or None; unaccepted agreement selects its page, busy state refuses, existing dialog is reused. |
| `save_api_settings(base_url,model,*,api_key=None,offline_only=False,slot=None)` | Main thread, agreement accepted and idle. Validate and persist before replacing the engine/config. Slot None is active; 0–2 explicit. Return runtime config containing only the active plaintext key; never log the whole result. Failure preserves current state. |
| `save_settings(values=None)` | Return bool. None reads controls; a dict is a partial update merged with current config. Validate first, persist, then apply idle changes. Appearance-only updates retain the engine and its request allowance; computational/network changes can rebuild resources. OCR-threshold changes recreate OCR on next use. Controlled failures remain on the page. |
| `refresh_windows()` | Snapshot windows; preserve only the same previously selected HWND+PID, never guess initial selection. |
| `chosen_window()` | Selected metadata dict; no selection raises UIValidationError. |
| `term_scope()` | Trimmed profile and mapped source/target codes; blank profile differs from shared scope. |
| `open_dictionary_import()` | Reuse/create dialog only while idle; construction does not open a file picker. |
| `manual_translate()` | Validate agreement, busy state, input, same-language and context limits before obtaining engine; worker posts events without touching Tk. |
| `stop()` | Stop screen pipeline and clear/hide presentation; sent requests may still complete. |
| `close()` | Wait at 100-ms intervals for an active import, then close engine/core/UI; never kills the game. |
| `drain()` | Default every 40 ms, at most 256 events, then foreground-checked drawing and metrics. |
| `settings_error_message(error)` | At most 500 chars; controlled configuration/UI/tuning/security/translation errors only. Unknown exceptions become a fixed message. |

Source/target selections are restored from supported persisted `source_lang/target_lang`; Chinese legacy aliases are recognized for UI selection. Changes and translation/settings actions persist them. This is separate from `app_language`. Saving a font/label does not clear translations or trigger a model call. App.start applies the chosen native font and passes display switches into a new Pipeline before capturing.

## Manual streaming

`manual_input` is a Tk Text and `manual_count` a StringVar. Input maximum is 64–16,000, default 4,000, with Ctrl+Enter and a visible counter. Busy input is disabled. Empty/over-limit/equal-language input or context above 2,000 is rejected before network work.

`_post_manual(text)` stores at most 64,000 cumulative characters in one lock-protected slot and enqueues `('manual',0,None)` only if no marker is pending. New fragments replace the slot; a slow UI does not accumulate every prefix. `_take_manual()` removes the latest value and resets that marker flag. `_set_manual_output(text)` temporarily enables the output widget, replaces the text and disables editing again. HTML, scripts and links are literal text with no execution/navigation.

Manual events use `(kind,generation,payload)` with generation zero: manual updates output, manual_status gives a controlled result description and manual_done unlocks controls. One manual task is active at a time. Screen events carry independent session generations and object revisions.

## ApiSettingsDialog

`ApiSettingsDialog(app)` creates three-slot editing without a request. `select_slot(index)->bool` accepts real ints 0–2, refuses while busy and saves the current address/model/typed-key/clear draft before loading another draft. Saved keys do not enter an edit field or draft.

`save_online()->bool` calls App's persistence boundary. After a successful save it clears only that draft; other unsaved slot drafts keep the dialog open with a message. `use_offline()->bool` retains its historical name; the button defers setup for record browsing only, without translating or submitting unsaved online drafts. Failure is inline, not a permission prompt. `close()` clears typed keys/drafts, releases its grab and destroys the window.

`_refresh_endpoint_hint()` compares canonical addresses. A changed endpoint requires key re-entry; invalid binding/decryption gives ConfigStore's fixed message and the main slot state shows reconfiguration needed. UI does not expose the backend allow_key_reuse bypass. Busy translation/import disables slot edits and save.

## SettingsPanel

`SettingsPanel(app,parent)` owns variables by config key. `values()->dict` yields numeric strings and actual booleans, plus font/interface-language selection. `refresh(busy)` controls every editor and save button. `font_box` supports typed names and installed-system-family choices. `update_preview()` updates `preview_text`, `preview_hint` and `preview_label` locally; no preview requests occur. Source label and bracket switches are independent, with mixed-language-only as a conditional source-label policy. Font size still fits automatically, with Windows fallback for missing glyphs.

`validate_tuning(values)->dict` is pure. It requires a dictionary and supplies managed defaults. Integers must be true ints or at most six decimal digits, not bool/float/NaN/Infinity. Booleans must actually be bool. Family text is trimmed, nonempty, at most 31 UTF-16 units, without Cc/Cf/Cs; interface language is one of the supported codes. Failure raises a controlled TuningValidationError without rejected raw values. max_concurrency is synchronized to translation_workers. See the settings chapter for all ranges.

Appearance-only saves retain TranslationEngine and its count. Numeric/network/other engine policy updates can recreate it after idle validation. Interface-language updates refresh the existing interface immediately, retaining inputs and data. No language confirmation implicitly accepts the agreement.

## DictionaryImportDialog

| Method | Result and restrictions |
|---|---|
| `browse()` | Explicit user action opens a picker on the main thread; no automatic parse and disabled while busy. |
| `invalidate()` | Clears parsed entries/scope and disables commit, preventing stale-preview import. |
| `preview()->bool` | Fixes profile/language/shared scope; starts worker parsing and receives results through the event queue. |
| `commit()->bool` | Requires preview; captures its scope and replacement option; gets engine before worker transaction. |
| `receive(payload)` | Main-thread preview/import/error handling. Preview shows five entries, at most 200 chars per field, read-only; import refreshes inserted/updated/skipped and lists. |
| `close()->bool` | False while importing; otherwise destroys idempotently. Never interrupts a write transaction. |

Results use `('dictionary_result',0,(dialog,(kind,result,scope)))`. Import errors and controlled TranslationError use their bounded messages; unknown exceptions are replaced. Import holds `App.import_busy`, disabling API/mode/parameter mutation. Neither file contents nor arbitrary exception details become diagnostics.

## Agreement localization

The agreement version and explicit acceptance time remain the same local contract across languages. `agreement_en.py` supplies AGREEMENT_TITLE_EN, DISCLAIMER_EN, AGREEMENT_TEXT_EN and `get_agreement_text_en()`. English text appends the exact unchanged original MIT suffix, not a new license. Japanese UI has its translated disclaimer plus original English MIT; the complete manual is available in Chinese and English. Changing UI language alone never invents consent.


### Show source labels only for mixed foreign languages

`show_source_label` is the master switch. The strict boolean `source_label_mixed_only` defaults to false; its checkbox is disabled when the master switch is off. The effective policies are: master off → no labels; master on/mixed-only off → always label; both on → label only when the current visible OCR objects contain at least two distinct foreign source-language bases after excluding the target-language base. `en-US` and `en` count together, as do `zh-Hans` and `zh-CN`. For a Chinese target, English alone hides source labels; English plus Japanese enables them. Counting follows recognized object languages, independently of the application interface language.

Object appearance/disappearance and scene changes reformat accumulated translations without another LLM call or changes to object IDs, revisions, dictionaries or cache keys. Brackets stay independent, so `[translation]` remains possible without a source label. Preview shows single-language and mixed-language samples locally without network access. The four basic formatting combinations apply when source labeling is effective; this additional policy decides when it is effective.


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


## Choosing OCR and optional AI image reading

OCR choices are Auto (default), Windows and Pixel text. Auto selects local pixel recognition for English low-palette/high-contrast frames and otherwise prefers Windows OCR. Pixel mode suits older fonts but may still misspell words. These three OCR choices themselves use no network. Recognition operates on one captured frame and paragraph grouping preserves source row breaks and physical geometry for source-row-constrained display; image reading is not a higher capture frame rate.

AI image reading is a separate switch, off by default. It requires online mode and a current-slot model that supports images. It sends the selected game PNG plus local anchor boxes/OCR hints to correct source text only at those boxes, never inventing model coordinates. It may improve glyph reading but adds latency and charges. The minimum request interval defaults to three seconds and is adjustable from one to sixty seconds; submit only stable text, then display subsequent translation with the usual SSE streaming. Failure falls back to local recognition; text with no local anchor cannot be recovered by this feature alone.

Before AI submission, strict local rules rejoin supported same-baseline narrative fragments into physical rows while retaining each row position. Vertical paragraph grouping still occurs after recognition. Recognition failure retains those local rows; the model never supplies new coordinates.

Default local OCR sends no images. AI reading sends neither the whole desktop nor game files and creates no remote File API file. It shares translation's request allowance and is disabled without a key. Stop translation and wait for pending work before saving recognition modes/interval. The r4 agreement describes this changed data flow.


## Game identity, recognition controls and UI state

`warmup_identity` and `App.current_warmup_scope` retain old names for named-profile/executable identity only; they no longer activate a learning strategy. Expert/local/aggressive/warmup/hybrid switches are removed. Missing API permits record browsing only. Selected source language and per-object detection remain distinct.

`SettingsPanel` persists `ocr_mode=auto/native/pixel`, `ocr_refine_workers=1..8`, `context_max_chars=512..16000` and `context_history_records=1..64`, default 4/6000/24. Optional `vision_ocr` explicitly uploads the selected crop and defaults off. Timing errors are status text, never rendered as translation.

`App.open_translation_history()->Toplevel|None` reads up to 24 recent records plus current-scope status while idle without API calls. Busy/errors return None. The read-only window shows update time, local directory, source/result/context; empty history points back to historical terms. It does not load the entire SQLite database or expose keys.

## Unlimited API request control (0.01.14)

`unlimited_requests` is an independent checkbox, false by default, whose Boolean value survives Chinese/English/Japanese interface switching. While enabled, the numeric allowance entry is disabled but its value is preserved. Disabling the switch re-enables that field subject to normal busy state. All localized save paths use strict Boolean validation. Screen/manual/import/in-flight activity still prevents strategy saves; successful idle saves configure the next engine.

`requests_remaining=None` denotes unlimited allowance and must not be displayed as zero requests remaining. A numeric `max_requests=0` is distinct from this checkbox. Setup does not automatically enable unlimited mode; public defaults remain finite.

## Preserved source pixels (0.01.15)

Existing objects snapshots carry preservation flags. OverlayState removes the corresponding old overlay immediately and rejects late translated output. `Pipeline.get_stats().preserved_source` supplies the current preserved-box metric. No extra window or faulty OCR string is painted as source. Stop/focus loss still uses the existing session cleanup.

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
