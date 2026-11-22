# Third-party notices · 0.01.27

Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.


The project's main application, native core, project scripts and original icon assets use **MIT**. The independent OCR helper in `tools/ocr_helper.py` has its own MIT license. The main process does not import tesserocr. Components distributed alongside the project keep their original licenses; this document does not relicense them or establish compatibility merely because they communicate through separate processes.

The complete MIT is in the [user agreement](USER_AGREEMENT.md). Original upstream notices accompany the binary distribution in `licenses/`, with inventory entries in `licenses/components.json`. Keep these files when redistributing. The summaries below aid navigation and do not replace original license conditions.

## Runtime and Python packages

| Component | License material and considerations |
|---|---|
| CPython 3.14.10 | PSF and historical licenses in its complete LICENSE; original bundled-runtime notices retained. Microsoft's redistributable runtime has its own terms. |
| Tcl/Tk 9.0.4 | Original `license.terms`; the upstream terms apply. |
| OpenSSL 3.5.9 | Apache-2.0 original license and notices. |
| Expat 2.9.0 / libffi 3.4.4 | MIT-style upstream licenses. |
| zlib-ng 2.2.4, runtime string 1.3.1.zlib-ng; zlib 1.3.2 in Tk | Preserve the respective upstream zlib license material; version strings and owning DLLs are recorded separately. |
| bzip2 1.0.8 | Original bzip2 license. |
| XZ/liblzma 5.2.5 | Original COPYING distinguishes public-domain library code from GPL-covered tools; do not label every XZ component identically. |
| mpdecimal 4.x / Zstandard 1.5.7 | BSD-style originals. |
| LibTomMath bundled with Tcl 9.0.4 | Upstream public-domain notice. |
| httpx / httpcore | BSD-3-Clause. |
| anyio / h11 | MIT. |
| idna | BSD-3-Clause. |
| Pillow | MIT-CMU plus licenses of native libraries included by its wheel. |
| certifi 2026.10.23 | MPL-2.0; complete matching source archive and original license are included in source-acquisition material. |
| PyInstaller | GPLv2 with its bootloader distribution exception; preserve the exact upstream exception. |

Runtime originals and provenance are recorded under `licenses/runtime-upstream/`; copied license text, source URL/version and owning component should remain linked. This release does not redistribute Microsoft font files: font selection refers to the user's installed Windows fonts.

## OCR distribution

Tesserocr is MIT, Tesseract is Apache-2.0, Leptonica uses a BSD-style license, and the included tessdata_fast language models have their own Apache-2.0 license. The original wheel's notices also cover libarchive, bzip2, giflib, ICU, Lerc, curl, deflate, iconv, jpeg-turbo, lzma, png, psl, ssh2, tiff, webp, xml2, zlib, OpenJPEG, OpenSSL, zstd, lz4 and runtime components. Preserve every supplied original, including `getopt_LICENSE.txt` and `leptonica-license.txt`; do not infer required notice coverage only from one top-level package name.

The release inventory maps the actual OCR DLLs to original wheel notice files. The recorded baseline contains 28 such DLL mappings and 37 original notices. These numbers describe that baseline's provenance inventory, not a guarantee about a future updated wheel. Verify hashes and mapping whenever the wheel changes.

## LGPL components and replacement material

The OCR wheel's `iconv` and `charset` DLLs come from libiconv 1.18, the identified conda-forge `hc1393d2_3` build, under LGPL-2.1-only. Matching source, recipe/patch material, acquisition URLs and hashes are supplied; the provenance work compares the identified binary code/source relationship. The separate GPL `iconv.exe` command-line tool is not distributed.

Users retain the modification, replacement and debugging/reverse-engineering rights required by the applicable LGPL. Do not impose a disclaimer or application agreement that removes those rights. A redistributor must retain the actual required source/relinking or replacement material for its chosen form of distribution; process boundaries alone do not waive license obligations.

## Development tools and optional engines

Tests, packaging, auditing and documentation tools retain the licenses recorded by their exact locked distributions. They are not all runtime requirements. FFmpeg is an externally supplied optional recording tool, not part of either public ZIP or required for translation; a redistributor adding it must review that exact build's licensing separately.

The offline neural engines in [OFFLINE_ENGINES.md](OFFLINE_ENGINES.md) are researched possibilities, not integrated dependencies. Their code, models, tokenizers and dictionary data must be reviewed separately before distribution. In particular, an Apache-2.0 model does not become MIT by being used with the application.

When publishing modifications, include corresponding project source and the complete notices required by each included component. Do not replace upstream licenses with this summary or claim that the whole package has one uniform license. See the recorded version/hash manifest and full original texts for the actual release contents.
