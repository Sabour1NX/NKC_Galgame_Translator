# Dictionary import and historical references · 0.01.27

Version 0.01.27 adds optional CUDA OCR, background context and group font fitting. Fresh same-image OCR evidence compares 0.01.15 with 0.01.27, separating cold startup, changed-background warm paths, cached revisits and character accuracy; real-API observations are separate. Historical evidence retains its original version labels. See the current performance and test reports for scope.

Compatibility review: 0.01.27 · 18 November2026. Historical sections retain their original version numbers.


Existing game/shared dictionaries and imports remain managed reference data. New translations are AI-generated; no local template/composition engine runs. Current prompt extraction uses matching named-game terms; shared entries remain manageable but are not automatically applied to output. Imports never execute as code.

## CSV and TSV

Suffix controls comma/tab delimiter; semicolons are not guessed. UTF-8, UTF-8 BOM, BOM-marked UTF-16 LE/BE and GB18030 are supported; UTF-32 and unmarked UTF-16 are rejected. Recommended headers are `source,target`; `word,translation` supports ECDICT-style data. Other recognized source names include `src/original/source_text/term` and their supplied Chinese aliases; target names include `dst/translated/target_text/meaning`. A unique pair of source/target columns is required, with header case/outer whitespace ignored. Language-code columns matching the selected direction also work. ECDICT `definition` does not replace its `translation` column; unrelated columns are ignored.

```csv
source,target
Start,Begin
"Open, now","Open immediately"
"Say ""Hello""","Greet the visitor"
"First line
Second line","Line one
Line two"
HP {n},Health {n}
```

Headerless files must have exactly two columns, source then target. A first row using reserved header names is interpreted as a header; add source/target explicitly when uncertain. Quoting/newlines follow CSV rules. Blank rows are skipped; nonblank records need both fields and consistent column counts. Internal LF/TAB and Unicode text are retained, line endings become LF, outer whitespace is stripped and NFC normalization is applied.

## JSON

An object mapping source strings to target strings or a list of `{source,target}` objects is accepted. Null/numbers/arrays are not text. NaN, Infinity, trailing commas and conflicting duplicate fields are rejected; nesting is bounded. JSON has no authoritative language metadata, so the selected pair applies to the whole file.

```json
[{"source":"Open the door","target":"Enter through the door"},
 {"source":"HP {n}","target":"Health {n}"}]
```

## TMX

The supported structure is `tmx/body/tu/tuv/seg`; `tuv xml:lang` determines matching. Every variant needs a unique seg. Inline element text is concatenated as text, never executed. Formatting-code text may remain; export plain TMX when that is wanted. Units without the selected pair are skipped, but an input with no usable entries fails.

| Selected code | Match preference | Not inferred |
|---|---|---|
| zh-Hans | zh-Hans, zh-CN, zh-SG | bare zh, zh-TW, zh-Hant |
| zh-Hant | zh-Hant, zh-TW, zh-HK, zh-MO | bare zh, zh-CN, zh-Hans |
| en | exact en, otherwise an unambiguous regional variant | conflicting regional translations |
| en-US | exact en-US, then generic en | en-GB as a substitute |
| ja | exact ja, then an unambiguous variant such as ja-JP | a different language |

All DTD/DOCTYPE/entity declarations are rejected; no external entity files or URLs are accessed. Built-in XML escapes such as ampersand escapes are permitted. Depth is at most 64 and elements at most one million.

## Limits, duplicates and commit

File maximum is 20 MiB and input-record maximum 100,000; duplicates and unmatched TMX units still count. Each field is at most 4,096 normalized characters, nonempty and free of unsupported controls. Exact source+target duplicates merge. Conflicting targets for one source reject the whole file, independently of the later keep/replace policy against existing database values.

A game/language dictionary allows 5,000 entries, a shared language pair 100,000. Manual editing remains limited to 256 characters per field. Numeric templates need exactly one `{n}` in each side; no arbitrary regex or macros execute. Preview shows only the first five entries. Existing values are kept by default; explicit replacement updates conflicts. Shared revision changes invalidate affected sentence-cache compatibility.

Use only data you may lawfully use and redistribute. A successful parse verifies structure, not translation accuracy or rights. Public releases include original small examples under docs/examples, not private game extractions or large third-party lexicons. Available examples include CSV/TSV/JSON/TMX; the file format and selected language pair must agree.
