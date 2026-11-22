# Release and verification · 0.01.27

Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.

## 0.01.27 delivery layout

`delivery/customer/` contains customer material; `delivery/release/` contains program/source archives; `trial/nishokuchou-0.01.27-trial/` is the runnable clean trial. `demo/NeedyGirlOverdose/` and development `config/` are private. Open OPEN_FIRST.html. The latest measured report compares 0.01.15 with 0.01.25; 0.01.27 did not remeasure those historical samples; named historical reports retain their original versions. TEST_REPORT.json records actual validation.

Each release uses its own `0.xx.xx` directory. Version 0.01.23 does not overwrite earlier versions. The public product has no API key or private game data and does not require administrator access. The internal Python package remains `nkc_galgame_translator` and native library remains `nkc_galgame_translator_core.dll`; the user-facing executable is `NKC_Galgame_Translator.exe`.

| Artifact | Purpose |
|---|---|
| `NKC_Galgame_Translator-0.01.27-windows-x64.zip` | Standalone Windows x64 program, matching DLL/runtime/OCR resources, manuals and licenses. |
| `NKC_Galgame_Translator-0.01.27-source.zip` | Corresponding application/native/helper source, tests, hash locks, build and documentation tools. |
| `NKC_Galgame_Translator-0.01.27-SHA256SUMS.txt` | Checksums for release archives; compare against a trusted copy. |
| `docs/PROJECT_MANUAL.html` and `docs/PROJECT_MANUAL.en.html` | Complete offline Chinese and English manuals, including SVG structure/workflows and granular interfaces. |
| `SBOM.cdx.json`, dependency/license inventories | Component versions, origins, hashes and license material. |

Unzip into a writable local directory and keep the complete tree. Do not distribute only the EXE or mix DLLs from another release. ABI 2 remains unchanged but the wrapper requires `gl_set_font`. Fonts are system resources selected by name, not separately bundled assets.

## Verification procedure

Run the version's full regression suite, self-test, native PE-hardening validation and release verification. Check the first-launch language chooser, agreement order, absent-key guidance, all three UI languages, three API slots, target selection, multi-object tracking, AI-only translation, concurrent streaming, dictionary import and error recovery. Test font selection and all label/bracket policies without unnecessary network calls. A language-only save must refresh widgets while preserving user data; it does not record agreement acceptance.

Real-game testing should identify the game, actual target HWND/PID, translation direction, the API used for each new result, request count and relevant capture evidence. Confirm click-through behavior, target-only overlay, stable font size and positions, wrapping, focus/move handling and source recovery on failure. A controlled fixture or historical screenshot is not evidence of a new real-game run.

Only the current [TEST_REPORT.json](../TEST_REPORT.json) establishes this release's measured counts and status. Earlier releases' test counts do not establish this release's acceptance. Simulated HTTP tests do not spend a private API balance; a genuine API check is documented separately. Passing one game does not establish compatibility with all games, display modes or anti-cheat systems.

The build's package allowlist excludes credentials, config/key files, databases, logs, private demos and game programs; the requested customer report includes three benchmark screenshots. Verify both ZIPs with `tools/verify_release.py`. Review source correspondence, dependency locks, models and original notices; inspect SBOM and file hash coverage. A successful content check is not an independent security audit or a publisher signature.

## Upgrading and private demonstrations

Keep a backup of the older version before copying personal settings/dictionaries. DPAPI credentials belong to the Windows user/machine and their bound endpoint; copying them to another computer does not create usable credentials. Do not claim portability of the secret store. New appearance preferences do not rewrite dictionary text or change translation-cache scope.

A local demonstration may deliberately contain an encrypted credential previously authorized by its owner. Label that folder private, keep it outside public archives and show only safe configuration/status values in evidence. Never place a plaintext key into documentation, report bodies, screenshots or distributed scripts. The demo's local API quota is a request cap, not a guarantee against provider charges.

Emailing an authorized task report and scheduling a one-time idle shutdown are operator tasks, not general product behavior. Neither is automatically restored or scheduled by launching the public program. End users should not receive private test footage, personal addresses, game assets or shutdown scripts inside a release.

## Known practical limits

OCR quality varies with stylized fonts, small pixels, animation and scene contrast. Color patches approximate the background and may be visible on artwork. New translation tasks require a usable API; historical records are references rather than offline answers. Native font fallback may select a different actual face; the diagnostic snapshot reports it. Very long text may reach the 8-pixel floor and report `fits=false`. Online timing depends on capture, OCR, queueing, provider response and network conditions; no universal frame-rate or latency claim is made.

The MIT license and disclaimer govern the project's own code; third-party components retain their own licenses. Include corresponding source and required notices when redistributing covered binaries. See [USER_AGREEMENT.md](USER_AGREEMENT.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
