# File, OCR IPC and native-input contracts

## 0.01.27 CUDA modules and IPC

| Module / class | Language | Responsibility |
|---|---|---|
| `cuda_ocr.py` / `CudaOcr` | Python / MIT | Local bounded JSON IPC client, hidden helper, image paths and lifecycle; no deep-learning imports in the GUI |
| `tools/cuda_ocr_helper.py` / `Engine` | Separate Python helper | RapidOCR / ONNX Runtime CUDA, PP-OCRv6-small detection/recognition, verification of executed CUDA kernels |
| `cuda_settings_ui.py` / `CudaControls` | Python / Tk | Shared first-run/settings switch, linear quality slider and memory budget; no probing/downloads |
| `OcrCore` | Python | Attempt GPU in Auto for en/ja/zh; same-frame CPU fallback on failure, actual `cuda_status` |

`CudaOcr(root, memory_mb=1024, quality=75)` exposes `available()` (files only), serialized `recognize(image, language='en')` and `close()` (helper/temp-image cleanup). Recognition requests contain only `image_path/language`; `warmup()` sends `{"warmup":true}` using synthetic tensors without capture/network; `cancel()` interrupts the helper and the cancelled instance cannot restart. Images are restricted to the allowed temporary root; stdin is data, never code. Responses contain `lines/ocr_ms/cuda`, at most 512 rows, 64000 total text characters and 1 MiB response size; rectangles must fit the image and confidence must be finite in 0–100. Acceptance requires `CUDAExecutionProvider` and `kernels_verified=true`, rather than provider availability alone.

States: `disabled/ready/active/not_installed/failed/cpu_mode/pixel_priority/unsupported_language`; ready is not proof of completed inference. Versions and hashes are locked in `requirements-cuda.lock`, `CUDA_DEPENDENCY_MANIFEST.json` and `models/cuda/manifest.json`. Distribution manifests carry component/model licensing. Installation/verification failure must preserve CPU fallback rather than claiming GPU acceleration.

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

## 0.01.27 perception candidates and image reading

`OcrCore.recognize_image` / `capture_ocr` may additionally return up to 128 `vision_anchors`: `text,x,y,w,h,bg,fg,confidence,_source_ink,_vision_only=True`. Low-confidence candidates provide geometry only to explicitly enabled AI image reading. They never enter ordinary rendered translations or success history. Normal local lines retain the configured confidence threshold (default 55). Selection filtering and coordinate conversion apply to candidates too.

The independent helper's `find_text_surfaces`, `surface_rows`, `read_text_surfaces` and `merge_surface_detections` follow whole-frame discovery with measured flat-panel RGB normalization and physical-row rereading. There are no game-specific coordinates. Oversized filled button blocks are excluded as text rows. Limits remain 512 ordinary lines, 128 candidates, 64000 combined characters and a 1 MiB JSON response; text, finite confidence and geometric bounds are validated.

Optional Vision includes the complete selected game-region image and up to 32 enlarged small-text crops from that same region. Additional crops have an aggregate 2-million-pixel and 4 MiB raw PNG budget; the original image retains existing image/HTTP limits. The model rereads locally anchored source text and cannot invent coordinates. Missing reliable local geometry leaves the source intact. A similar model name does not prove image-input support. Background search and image reading are independent settings; search does not replace OCR.

## 0.01.27 context boundary

The optional background context layer uses the single DeepSeek server-side search tool; display translation requests have no tools and do not wait for new search. Both layers share request/concurrency/token accounting. Source text, excerpts, pages and notes remain untrusted. Returned links are never fetched by the client and cannot change source geometry. See [CONTEXT_AGENT.md](CONTEXT_AGENT.md) for exact payload, metadata, timeout and cache contracts.

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

These are implemented boundaries, not an OS sandbox or protection from a malicious same-account process. Dictionary, OCR and model content remains string data: no eval, script rules, shell generation, automatic link opening or output execution.

## Ordinary local files

`nkc_galgame_translator.input_paths.local_file_path(value: str | os.PathLike) -> pathlib.Path` returns an absolute path without environment expansion, downloads or shell execution. Length is 1–32,700 characters, with no ASCII controls. UNC/device namespaces, alternate data streams, reserved device names and trailing dot/space components are rejected. Ordinary relative dot/dot-dot resolution is supported. Drives must be local fixed/removable/CD/RAM drives; network-mapped and unavailable drives are rejected. Every component must avoid symlinks/reparse points, and the final object must be a regular file.

Move cloud placeholders, linked directories or shared-network dictionaries into a normal local directory before use. Invalid paths raise ValueError; missing/permission-denied files can raise OSError. Import converts these to a controlled DictionaryImportError without paths/body; native loading uses a fixed RuntimeError. A same-account attacker can still race validation and opening; the installation directory is not a security boundary against that account.

## Dictionary parser

```python
parse_dictionary(path, source_lang: str, target_lang: str) -> list[dict[str,str]]
class DictionaryImportError(ValueError): ...
```

Only `.csv/.tsv/.json/.tmx` are accepted. Maximum file size is 20 MiB, input records 100,000 and each normalized source/target field 4,096 characters. Duplicate/unmatched input records still count. JSON nesting is bounded to 64, rejects nonfinite numbers and conflicting duplicate fields. TMX XML depth is at most 64 and element count at most one million; DOCTYPE/DTD/entity declarations are forbidden. UTF-8/BOM, BOM-marked UTF-16 and GB18030 are supported; UTF-32 and unmarked UTF-16 are not.

Fields are strings, nonempty after normalization, NFC-normalized with CR/CRLF→LF and surrounding whitespace trimmed. Non-CR/LF/TAB controls and invalid surrogates are rejected. Exact duplicates coalesce; one source with conflicting targets rejects the complete file. Parsing does not write SQL or call a model. Preview and commit are separate; database capacity differs between game and shared scopes. See the dictionary chapter for headers, TMX language matching and examples.

## Independent helper startup

For source development, use the pinned `vendor/python/python.exe` interpreter (CPython 3.14 x64), not an unspecified `python` from PATH. The matching tesserocr wheel cannot be loaded by a different Python minor version. Packaged launches use the independent helper EXE and its bundled runtime.

The main program never imports tesserocr. `PortableOcr` starts a separate hidden executable when present, otherwise an isolated Python helper (`-I`, unbuffered output). It removes PYTHONPATH/PYTHONHOME/PYTHONSTARTUP environment influence, uses UTF-8 streams and limits OCR threading. A unique temporary directory holds only its current frame.bmp; helper CLI receives `--packages`, required `--tessdata`, and required `--input-root`.

The helper resolves all CLI paths against its launch directory before changing cwd. Tesseract's narrow Windows model path cannot reliably consume Unicode absolute paths, so the helper switches its own cwd with Python's Unicode-capable API to the resolved model directory, then initializes Tesseract with `path='.'`. No model copying or short-name dependence is used at runtime. Relative image paths from independent callers remain relative to the original launch directory. Missing working directories return a fixed error. The GUI's current directory is unaffected.

## Requests

Each request is one UTF-8 JSON line, including a newline, at most 16,384 characters. Allowed keys are `image_path`, `language`, `quit` only.

```json
{"image_path":"E:\\example\\data\\ocr-session\\frame.bmp","language":"jpn+eng"}
```

The path must name `frame.bmp` directly under this session's input root. No network path, reparse point, device/ADS/control path or directory is accepted. Main-process requests use absolute paths. Language defaults to `jpn+eng`; allowed values are `jpn`, `eng`, `jpn+eng`, `chi_sim`, `chi_sim+eng`. Missing models cause a controlled error, not a download. `{"quit":true}` exits only when used alone. An oversized/non-newline-terminated request produces a fixed error and ends the helper, avoiding interpretation of a trailing fragment as a new request.

## BMP and raw RGB

Only uncompressed BI_RGB BMP is accepted: `BM` marker, 40-byte BITMAPINFOHEADER, one plane, 24/32 bits, width and absolute height 1–4,096. Pixel offset must be 54; exact file length must equal offset plus aligned scanline bytes. The upper file-size bound is `4096*4096*4+1024`. Compression, extended headers, spoofed suffixes, truncation and trailing bytes are rejected.

After header/size validation, Pillow explicitly opens only BMP, checks dimensions, loads and converts RGB. `set_rgb_image(engine,image)->bytes` validates raw buffer length and calls `SetImageBytes(pixels,width,height,3,width*3)`. The caller retains the returned buffer until AUTO and any SPARSE_TEXT recognition finish. It deliberately does not use SetImageFile or SetImage(PIL), whose implementation can invoke Leptonica format decoders. EPS/TIFF/JPEG2000 general file decoding is not exposed by this path. That reduces reachable inputs, not the license obligations or proof of all bundled libraries' security.

## Responses and lifetime

```json
{"lines":[{"text":"Start game","x":32,"y":30,"w":340,"h":40,"confidence":94.5}],"ocr_ms":20.1}
```

Producer JSON is at most 1,048,576 UTF-8 bytes. The consumer separately bounds a line to 1,048,576 characters plus a checking character and requires its newline. `lines` is a list of at most 512 entries; empty is a normal no-text result. Each text has at most 16,000 characters, total 64,000, without NUL/unpaired surrogates. Coordinates are true integers, not bool; every nonempty rectangle must fit wholly inside the input image. Confidence is finite 0–100 and OCR time finite 0–120,000 ms, neither bool/NaN/Infinity. Any error member causes a fixed parent exception rather than displaying its raw value.

`validate_response(response,width,height)->dict` returns a valid dictionary or raises RuntimeError. `PortableOcr.recognize(image)` serializes through an instance RLock and rejects invalid dimensions before process creation. Response queue capacity is two; wait timeout is 20 seconds. Timeout, malformed output or helper exit closes the process and temporary directory, allowing a fresh helper next call. Close asks for quit, waits one second, then kills if necessary and waits at most two more seconds. The reader thread never touches Tk.

## Python/native boundary

The absolute DLL path passes ordinary-file validation. `ctypes.CDLL(...,winmode=0x900)` searches its directory and System32, not cwd/PATH. ABI 2's structure remains 56 bytes; the 0.01.20 font export is additionally mandatory.

| Input | Python boundary |
|---|---|
| Capture x/y/w/h | int32 coordinates, dimensions 1–4,096, reject bool/fraction/addition overflow before buffers/DLL. |
| OCR language | ASCII language-tag syntax, at most 64 chars, no NUL. |
| Regions | list/tuple, at most 512 dictionaries. |
| Region coordinates | int32, dimensions 1–8,192 and checked addition. |
| IDs/revisions | true uint64 integers; default zero. |
| Font size | integer 0–512, zero auto-fit. |
| Text | string, no NUL/isolated surrogates, at most 64,000 UTF-16 units per box and 1,048,576 per batch. |
| RGB | three converted/clamped components, 0–255. |
| Final flag | converted to zero/one. |
| Target | uint64 HWND, uint32 PID; zero reserved for diagnostic/clear semantics. |
| Font family | string, 1–31 UTF-16 units; nonblank; reject Cc/Cf/Cs; no file loading. |

Validation raises ValueError before submitting a partial snapshot. C++ independently validates counts, sizes, text lengths and duplicate nonzero IDs. Invalid direct C rectangles can be skipped whereas Python rejects their batch. Raw callers remain responsible for valid context/pointers/readable NUL-terminated buffers; ctypes and length checks are not memory isolation.

Font setter details, asynchronous state and selected/actual-face diagnostics are in the API chapter. Regressions cover file/path attacks, malformed JSON/XML/BMP/IPC, native integer and UTF-16 boundaries, Unicode-model paths and normal Japanese OCR. Actual current-version results are in TEST_REPORT.json rather than inherited historical counts.


## Fixed-image OCR and local pixel mode in 0.01.20

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

When full-image pixels change but the text signature stays equal, local anchors are revalidated without resetting the stability timer, canceling the request or clearing displayed output. That poll can still consume completed work. In-box pixel changes, added/missing/relocated relative boxes or language changes advance generation and reject old results. Focus loss/stop explicitly cancel. Screen-region origin/dimension/language changes reset raw capture for revalidation; matching text can reuse a cached result relocated to current x/y without modifying cached coordinates.

Two digest-only LRU maps each hold 16 entries: full-frame RGB digest to text signature, and text signature to recognition result. A valid shortcut/result skips local OCR and API work. Success has no TTL; failed local fallback lasts 30 seconds, checked on re-entry/reappearance rather than a periodic retry timer. Target/text-generation checks still apply. Recognizers receive deep-copied anchors so failure preserves original geometry/colors. Pending means unfinished work; cancellation prevents application but cannot refund sent requests. Close cancels this wrapper's pool with wait=False and closes its core, never the game. Missing local anchors cause no speculative model recovery. Engine diagnostics are vision-waiting, vision+local and local-fallback with controlled vision_error.

## Screen OCR quality metadata

Version 0.01.15 Pipeline adds local `_preserve_source` and `_ocr_rejection_reason` metadata after language routing, without rewriting `text`. Model output cannot set these fields. Rejected and intersecting boxes do not enter translation or painting. See [API.md](API.md) for the gate and state lifetime.

## 0.01.20 — Word cells and source-row rendering boundaries

The independent helper adds optional strict-bool `separated_cell`, derived from distant actual WORD positions. Native OCR JSON also supplies image-relative unpadded `ink_bounds:[x,y,w,h]`. OcrCore converts these locally to `_layout_cell` and `_source_ink`, offsetting ink exactly once on placement. See [API.md](API.md) for containment checks, numeric-column evidence, `_source_rows`, the 36-byte `GLSourceRow`, `gl_overlay_fixed` offsets and failure semantics.

Legacy GLRegion ABI 2 / 56 bytes is unchanged. Production fixed layout requires a matching DLL exporting `gl_overlay_fixed`; absence raises an error instead of silently using free wrapping. Equal-height slots for an old multiline object are an explicit fallback, not character-count estimates of source coordinates.


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

## 0.01.23 local RGB contrast interfaces

The independent MIT OCR helper adds `color_contrast(image,background)`, `flat_color_frame(image)`, `find_contrast_rows(image)`, `read_contrast_rows(engine,tesserocr,image,language,regions,cache=None)` and `ContrastCache`. GUI JSON and native ABI are unchanged.

RGB channel-distance normalization uses an 8-level noise margin and a 4x mapping, preserving chromatic differences even at similar luminance. Whole-frame color normalization requires a measured background share of at least 80%; local rows require measured flat edges and contrasting surroundings. Detection accepts RGB images of 1–4096 pixels per dimension, examines at most 256 candidate rectangles and returns at most 8. Rows are 10–128 pixels high, at least 48 pixels wide and at least twice as wide as high. Ink occupies 2.5%–50%. Per-crop area is at most min(1 million, frame/3), aggregate at most min(2 million, frame/2).

Local SINGLE_LINE recognition tries native scale and, when needed, half scale. It accepts confidence >=70, maps actual word bounds back using measured resize ratios and clamps to the detected rectangle. Only uncovered cells are appended. The output remains bounded to 512 boxes / 16000 characters each / 64000 total. Original RGB, foreground/background sampling and source-ink geometry are unchanged.

ContrastCache uses language, dimensions, SHA256 plus exact RGB byte equality; 64 entries / 16 MiB including a conservative 1 MiB result allowance per entry. LRU eviction applies. Results are crop-relative and rebase on the current detected row; successful empty results may be reused, exceptions are not cached. Text/color/size/language changes invalidate reuse.

Pixel mode enables this path; auto also routes flat chromatic text to it. Forced Windows OCR retains its native engine. No new network calls, threads, dependencies or settings. Ambiguous textured/gradient backgrounds and unbounded selections may still be missed; no game-specific word substitutions are used.
