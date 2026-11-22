# NKC_Galgame_Translator · Real-time game translation

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

The app first reads the complete text region, reads available background references without waiting for web search, asks the model for the current translation, and then fits it into the original rows. These stages are kept separate: search notes help understanding but never replace the words displayed in your game.

Enable online background research in **Settings → Context and display layers**, save and restart translation. Public builds default to off. Only the supported official DeepSeek `deepseek-flash` server search extension is declared; other compatible providers retain ordinary translation. The model decides whether to search. A setting being enabled is not proof that search ran: status distinguishes received sources, no search and failures. Cached background references do not replace translation requests. See [context interfaces and limits](CONTEXT_AGENT.md).

One continuous body-text group shares a font size. At completion, character spacing can still expand to fill each original row. If a long row needs a smaller automatic font, the group shrinks together rather than enlarging another row. Headings, different source sizes, columns and font styles remain independent. Text that cannot fit at the minimum size retains the original. Font consistency cannot repair incorrectly measured OCR geometry.

The current live-game target is NEEDY GIRL OVERDOSE, focusing on small Japanese text, multicolor panels and paragraph sizing. Existing Space Rogue captures remain regression fixtures. Consult this release's test and performance reports for the actual coverage and limitations; a single scene is not an all-game claim.

**Read the game, right where it happens.**

Streamed translation follows the original text location so you can stay focused on the game. Version 0.01.27 · Windows 10/11 x64.

## Start in three steps

1. Extract the entire application folder to a writable location and run **NKC_Galgame_Translator.exe**. Keep all companion files; no separate Python installation is required.
2. Choose the interface language and review the user agreement. Open the prominent API configuration entry and save an HTTPS service URL, supported model and key in one of three slots. Stored keys display masked placeholders and are encrypted for the current Windows user.
3. Open a windowed game, select its window and source/target languages, choose the client area or text region and start translation. Return to the game to view the overlay.

## Multiple selections and automatic font styles

Choose a game window and click **Select region**. Drag repeatedly to add **1–8 non-overlapping rectangles**. Press **Enter to confirm**, Backspace or right-click to undo the last rectangle, or Esc to cancel without changing the previous selection. Minimum rectangle: 20 × 20 pixels. Combined bounds: at most 4096 pixels per axis. Keep each complete paragraph inside one rectangle with a small margin. Selections follow the game client, clip on resize and reset to the whole client when choosing a different game window. Selections last for the current UI session.

One captured frame serves all selections. Gaps between rectangles are blacked out before OCR or optional AI image reading. Grouping and tracking do not cross selection boundaries. Adding regions does not start independent OCR processes or change translation concurrency. Use windowed mode when needed.

In **Settings → Translation appearance**, enable **Match the source font style automatically (target-language support)**, save and restart translation. Local screenshot evidence approximates pixel, serif, sans-serif or monospaced style. Each box checks the installed font against the target script and actual translated characters. No font downloads are needed. This option defaults to off; disabling it restores the manual font. Size fitting and minimum/maximum sizes remain independent settings.

This matches broad style, not the original font file. Decorative text, complex backgrounds, short words and OCR mistakes can affect classification. Missing glyphs trigger an installed compatible fallback; if none exists, the original remains visible. Automatic coverage checking conservatively supports BMP characters. A box containing supplementary-plane characters or emoji retains the source; manual font mode remains available with Windows fallback.

## Make it yours

- Multiple text objects translate concurrently and stream into their original regions. Clicks pass through the overlay. Moving the game window moves the translated text with it.
- Select an installed font, fixed size or automatic sizing bounds (default 8–72 pixels). Long translations shrink within the configured range.
- Source-language labels, brackets and screenshot inclusion are optional. Interface languages are Chinese, English and Japanese; settings can be changed after first launch.
- Translation concurrency and request limits are configurable. Unlimited requests removes the application's count limit; provider balance and rate limits still apply.
- An optional game profile helps retain terminology and context references. Saved translation/context records inform future AI requests; they do not replace new AI translation.

## Response settings

The responsive preset uses a 50 ms capture interval and an 80 ms settling delay. For typewriter dialogue, a 150–300 ms settling delay can reduce intermediate requests. Choose the balanced preset for lower resource usage. Save, stop and restart translation to apply settings.

Classic pixel-font games can use Pixel mode. Auto mode recognizes typical pixel HUDs and flat colored text. Optional AI image reading requires a compatible model and adds an API request; it is off by default.

## Measured performance

See the [performance and recognition report](../PERFORMANCE_REPORT.en.html) for the fresh 0.01.15 versus 0.01.27 same-image comparison and separately scoped real-API observations. Local OCR, first translation callback and final translation callback are separate metrics. This fresh run does not measure native painting or monitor presentation; callback arrival is not screen visibility and 150ms is not an end-to-end ceiling. NEEDY GIRL OVERDOSE is the current live-game test target, emphasizing small Japanese text and multicolor panels. Image replays, synthetic layout cases and real API tests are labeled separately; they do not certify the entire game.

## Helpful checks

If translations are absent, check focus, the selected region, language and API balance. For repeated typewriter requests, increase settling time. For provider HTTP 429, reduce concurrency. Complex textures, low contrast and unusual fonts can affect recognition. When text cannot fit reliably, the original remains visible.

## API, records and license

Use your own OpenAI-compatible HTTPS service and supported model; provider charges apply. The public trial includes no private API key and adds no separate trial countdown. Without an API, saved records remain readable but new translations cannot be generated.

Keep config/ and data/ when migrating your personal folder. Encrypted keys normally require the same Windows account. See the [user agreement](../USER_AGREEMENT.en.md) for the disclaimer and MIT license, and the [complete manual](../PROJECT_MANUAL.en.html) for technical reference.
