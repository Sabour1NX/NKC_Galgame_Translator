# Dependencies, builds and provenance · 0.01.27

## 0.01.27 CUDA runtime and prewarm contracts

Optional components lock ONNX Runtime GPU 1.32.0, RapidOCR 3.10.0, CUDA 13.x runtime / cuDNN 9.x. RTX 3070 / driver 617.42 was verified locally; this does not certify other combinations. Wheel/model hashes are fixed. Detection and recognition provider arenas share the configured budget, totaling 1 GiB by default, with additional driver/runtime memory.

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` retains disabled-by-default low-level call compatibility; App passes the enabled user-setting default and may transfer a prewarmed `CudaOcr` instance. `App._prepare_cuda()` runs local `warmup()` in a background thread without screen capture or API requests, reusing the helper for later OCR. Prewarming does not eliminate first-inference cost for every new image shape.

## 0.01.27 Optional CUDA component installation

CUDA components are separate from the base program: approximately 2.1 GiB plus about 31 MB of models, with actual distribution size in the manifest. Explicitly run `vendor/python/python.exe tools/setup_cuda_ocr.py` to download/install into project-local `vendor/cuda` / `models/cuda`. `--verify` checks installed versions/model hashes, not real GPU inference. It does not modify global PATH/CUDA or install automatically when a settings switch changes. CPU remains available without these components.

Versions, hashes and licenses are in `requirements-cuda.lock`, `CUDA_DEPENDENCY_MANIFEST.json`, `third_party/cuda/` and `models/cuda/LICENSE`. The main process only uses bounded image/JSON IPC and does not import deep-learning packages. Arena budgets exclude driver and some temporary overhead; desktop-wide nvidia-smi usage is not this process's memory consumption.

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

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## Dependency review

No new third-party package or font bundle. Style analysis reuses Pillow13.0.0; installed-face and glyph checks use Windows GDI. Rebuild the native DLL for the additive exports. Dependency locks and third-party licenses remain applicable.

The platform is Windows x86-64. Version 0.01.20 retains the dependency baseline introduced by 0.01.11, and rebuilds the native DLL for mixed Latin/CJK wrapping while retaining fixed-image OCR and the font setter. The OCR quality gate uses Python standard-library rules; it and the retained unlimited-request option add no dependency or ABI change. The application chooses installed Windows font families and redistributes no Microsoft font files. The [dependency manifest](../DEPENDENCY_MANIFEST.json) is the detailed source of package versions, wheel URLs, SHA256 hashes, groups and upstream licensing metadata.

| Component | Baseline | Purpose |
|---|---|---|
| CPython | 3.14.10 x64 | Application runtime and Tk UI; official PSF/historical license notices retained. |
| OpenSSL / SQLite / Expat | 3.5.9 / 3.50.4 / 2.9.0 | TLS, local database and XML parsing in the runtime. |
| Tcl/Tk | 9.0.4 | Desktop widgets; separate upstream licenses. |
| HTTPX / httpcore / h11 | 0.28.1 / 1.0.9 / 0.16.0 | HTTP and streaming transport. |
| anyio / typing_extensions | 4.16.0 / 4.16.0 | Transport dependencies. |
| certifi / idna | 2026.10.23 / 3.20 | Certificate bundle and domain handling. |
| Pillow | 13.0.0 | Restricted image transfer and development capture. |
| tesserocr / Tesseract / Leptonica | 2.13.0 cp314 / 5.5.4 / 1.87.0 | Isolated OCR helper and native dependencies. |
| MSVC / Windows SDK | 19.43.34809 / 10.0.26100.0 | C++ x64 DLL build; SDK/WinRT/GDI. |
| PyInstaller / hooks | 6.22.3 / 2026.10 | Standalone application packaging. |
| pytest / pywin32 | 9.2.0 / 312 | Regression and Windows UI validation. |
| pip-audit | 2.10.1 | Development-time public Python advisory queries. |
| markdown-it-py | Locked in requirements-docs.lock | Development-only offline HTML generation. |

The inventory is not a statement that every component uses MIT. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the original files in `licenses/`. The build creates `SBOM.cdx.json` and `licenses/components.json` in the release directory.

## Exact lock files

`requirements-runtime.lock` contains the eight main Python packages; `requirements-ocr.lock` contains the separate OCR wheel. Build, test, advisory and documentation tools have their own `requirements-build.lock`, `requirements-test.lock`, `requirements-audit.lock` and `requirements-docs.lock`. `requirements.txt` references the runtime lock.

Locks require exact CPython 3.14/Windows x64 wheels, both pinned version and SHA256. Use `--require-hashes --only-binary=:all:`. Do not remove hashes to work around an incompatible Python version, architecture or missing wheel. A dependency update must update locks, notices, inventory and tests together. The main process does not import tesserocr.

## Build from source

Install the official [Python 3.14.10 x64 release](https://www.python.org/downloads/release/python-31410/) including Tcl/Tk and pip. The recorded installer SHA256 is `92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965`. An isolated developer runtime may be used without changing an existing Conda installation or global PATH. The example assumes that runtime was placed at `vendor/python`; otherwise set `$pythonExe` to its actual full path.

Install Visual Studio 2022 Build Tools with x64 C++ and Windows SDK. `native/build.ps1` locates the tools. Optional `tools/setup_compiler.ps1` modifies the current user's PATH/INCLUDE/LIB only when a developer explicitly runs it; public application startup does not alter compiler settings.

```powershell
$pythonExe = (Resolve-Path '.\vendor\python\python.exe').Path
& $pythonExe -m pip install --require-hashes --only-binary=:all: -r requirements-runtime.lock -r requirements-build.lock -r requirements-test.lock
& $pythonExe -m pip install --require-hashes --only-binary=:all: --no-deps --target vendor/ocr -r requirements-ocr.lock
& .\native\build.ps1
& $pythonExe -m pytest -q
& $pythonExe main.py --self-test
& .\tools\package.ps1 -Python $pythonExe
```

The native flags include `/O2 /MT /GS /sdl /guard:cf` and linker `/DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /GUARD:CF`. This version keeps GLRegion ABI 2/56 bytes but requires the newly exported font setter.

The source ZIP does not duplicate third-party wheels or OCR models. Obtain Japanese/English models from the [official tessdata_fast repository](https://github.com/tesseract-ocr/tessdata_fast), place them in `models/tessdata` and verify the exact manifest hashes. The matching verified program ZIP also contains those models and licenses. A matching filename is insufficient.

Packaging does not install from the network or read private configuration into the package. It rejects build versions that differ from its manifest. A full build embeds current Python source into the EXE. `-SkipBuild` is only for refreshing public documents/inventory after a complete build, not for shipping modified source with an old EXE.

## Audit scope and remaining checks

The baseline update from Python 3.13.5/Pillow 11.1.0 occurred in 0.01.11. The [Python release notes](https://www.python.org/downloads/release/python-31410/), [Pillow JPEG2000 advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8) and [Pillow TIFF/EXIF advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-wqgw-9xfh-qf2g) describe the relevant upstream fixes. Input format restrictions remain necessary after updating dependencies.

The recorded 14 November 2026 pip-audit query found no known advisory for its covered runtime/OCR/build Python package versions. See `DEPENDENCY_AUDIT.json` for raw scope/date. This is historical dependency evidence, not a new claim that all 0.01.20 code or every C/C++ dependency is vulnerability free.

The OCR wheel still reports OpenJPEG 2.5.4; that text does not prove which upstream patches are present. This application explicitly decodes bounded BMP and calls `SetImageBytes` with raw RGB, avoiding Leptonica's general file decoder. Regression checks reject `SetImage`/`SetImageFile` routes and misleading image suffixes. This narrows reachable input, not the library's overall vulnerability status. Reassess before enabling additional formats.

## Reproduction and documentation

`tools/dependency_manifest.py` builds version/hash metadata from pip `--report` records. Normal users use the already supplied locks. `tools/package.ps1` creates separate program/source ZIPs, file hashes and the inventory. `tools/verify_release.py` checks contents, privacy exclusions, hash correspondence and matching source. Final results belong to this version's [TEST_REPORT.json](../TEST_REPORT.json).

Install `requirements-docs.lock`, then run `& .\vendor\python\python.exe tools/build_html_docs.py` and `& .\vendor\python\python.exe tools/build_english_docs.py`. Both manuals have eighteen chapters, inline SVG diagrams and no JavaScript or remote resource loading. Browser networking is unnecessary to read them; external primary-source links are optional navigation only.

From the version directory in PowerShell, run source with `& .\vendor\python\python.exe main.py`, self-test with `& .\vendor\python\python.exe main.py --self-test`, and tests with `& .\vendor\python\python.exe -m pytest`. Avoid a bare `python` command: it may select an existing Anaconda installation or a different Python minor version, while this portable OCR wheel targets CPython 3.14 x64. For a source-only `Portable OCR helper failed` error, first check the interpreter version and full path, then investigate models and other diagnostics. The packaged EXE contains its runtime and does not depend on the Python selected by system PATH.

Optional `vendor/python/python.exe tools/record_demo.py --frames-only` validates the actual Tk UI and saves PNG frames; `--ffmpeg <local-encoder-path>` can additionally create an MP4 using an external FFmpeg/Windows Media Foundation H.264 encoder. The recording explicitly labels its simulated AI SSE responses, returned through httpx MockTransport with zero network requests. Scripted timing does not measure real translation speed or quality. Temporary fake credentials and fixture consent do not alter real configuration. FFmpeg is neither a translation runtime requirement nor included in the public ZIPs; real-game/API evidence is reported separately.

There is no automatic updater, telemetry or model download during application startup. Development advisory queries send package names/versions, not user text, images or credentials.

Version 0.01.20 uses existing Pillow/HTTPX dependencies for optional PNG image recognition; no new local neural model or extra cloud SDK is bundled. Native loading additionally requires gl_ocr_bgra.


## 0.01.20 dependency scope

Background repair, OCR refinement and compressed context reuse existing C++, Pillow, SQLite and zlib. No dependency or lockfile was added/changed. Advisory evidence is retained from the existing report; this is not a fresh online vulnerability query. Release verification and TEST_REPORT.json state the current checks.

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
