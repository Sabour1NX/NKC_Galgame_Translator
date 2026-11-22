# SPDX-License-Identifier: MIT
"""Bounded, read-only import of user-selected bilingual dictionary files.

Parsing never writes the database or evaluates imported text. The caller can
preview the returned records and commit them in one separate transaction.
"""
from __future__ import annotations

from .i18n import ui_source

import csv
import io
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
from .input_paths import local_file_path


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_FIELD_CHARS = 4096
_XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'
_SOURCE_HEADERS = {'source', 'src', 'original', 'source_text', 'word', 'term',
                   ui_source('Original text'), '\u6e90\u6587', '\u6e90\u6587\u672c', '\u8bcd\u6761', '\u5355\u8bcd'}
_TARGET_HEADERS = {'target', 'dst', 'translation', 'translated', 'target_text',
                   'meaning', '\u8bd1\u6587', '\u76ee\u6807\u6587\u672c', '\u7ffb\u8bd1', '\u91ca\u4e49'}


class DictionaryImportError(ValueError):
    """A fixed diagnostic that never echoes file contents or system paths."""


def _language(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{2,8})*', value.strip()):
        raise DictionaryImportError(ui_source('Select valid source and target languages.'))
    code = value.strip().lower().replace('_', '-')
    pieces = code.split('-')
    if pieces[0] == 'zh':
        # A script marker is authoritative; bare "zh" is intentionally not
        # assumed to mean either simplified or traditional Chinese.
        if 'hans' in pieces or (not any(p in pieces for p in ('hans', 'hant')) and any(p in pieces for p in ('cn', 'sg'))):
            return 'zh-hans'
        if 'hant' in pieces or any(p in pieces for p in ('tw', 'hk', 'mo')):
            return 'zh-hant'
    return code


def _language_score(candidate: str, selected: str) -> int | None:
    candidate = _language(candidate)
    if candidate == selected:
        return 0
    # Generic English/Japanese etc. can select a regional variant. An explicit
    # region never silently selects a different region. Ambiguity is rejected.
    if (candidate.split('-')[0] == selected.split('-')[0] != 'zh'
            and ('-' not in candidate or '-' not in selected)):
        return 1
    return None


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise DictionaryImportError(ui_source('The dictionary exceeds the 20 MiB limit. Split it before importing.'))
        with path.open('rb') as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise DictionaryImportError(ui_source('Unable to read the dictionary. Check that the file exists and is readable.')) from None
    if len(raw) > MAX_FILE_BYTES:
        raise DictionaryImportError(ui_source('The dictionary exceeds the 20 MiB limit. Split it before importing.'))
    if not raw:
        raise DictionaryImportError(ui_source('The dictionary file is empty.'))
    if raw.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
        raise DictionaryImportError(ui_source('UTF-32 is not supported. Save as UTF-8 or UTF-16 with a BOM.'))
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'gb18030')
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if '\x00' in text:
                raise DictionaryImportError(ui_source('The file contains invalid null characters. UTF-16 files must have a BOM.'))
            return text
        except UnicodeError:
            pass
    raise DictionaryImportError(ui_source('Unable to decode the dictionary. Use UTF-8, UTF-16 with a BOM, or GB18030.'))


def _field(value, row: int) -> str:
    if not isinstance(value, str):
        raise DictionaryImportError(f'\u7b2c {row} \u6761\u8bb0\u5f55\u7684\u539f\u6587\u548c\u8bd1\u6587\u5fc5\u987b\u662f\u6587\u672c\u3002')
    if len(value) > MAX_FIELD_CHARS:
        raise DictionaryImportError(f'\u7b2c {row} \u6761\u8bb0\u5f55\u7684\u5b57\u6bb5\u8d85\u8fc7 4096 \u5b57\u7b26\u3002')
    value = unicodedata.normalize('NFC', value.replace('\r\n', '\n').replace('\r', '\n')).strip()
    if len(value) > MAX_FIELD_CHARS:
        raise DictionaryImportError(f'\u7b2c {row} \u6761\u8bb0\u5f55\u7684\u5b57\u6bb5\u8d85\u8fc7 4096 \u5b57\u7b26\u3002')
    if not value:
        raise DictionaryImportError(f'\u7b2c {row} \u6761\u8bb0\u5f55\u7684\u539f\u6587\u548c\u8bd1\u6587\u4e0d\u80fd\u4e3a\u7a7a\u3002')
    if any(unicodedata.category(char) in {'Cc', 'Cs'} and char not in '\n\t' for char in value):
        raise DictionaryImportError(f'\u7b2c {row} \u6761\u8bb0\u5f55\u5305\u542b\u65e0\u6548 Unicode \u6216\u4e0d\u652f\u6301\u7684\u63a7\u5236\u5b57\u7b26\u3002')
    return value


class _Records:
    def __init__(self):
        self.rows = 0
        self.values: dict[str, str] = {}

    def add(self, source, target):
        self.rows += 1
        if self.rows > MAX_ENTRIES:
            raise DictionaryImportError(ui_source('The dictionary exceeds the 100,000-record limit. Split it before importing.'))
        source, target = _field(source, self.rows), _field(target, self.rows)
        if source in self.values and self.values[source] != target:
            raise DictionaryImportError(f'\u7b2c {self.rows} \u6761\u8bb0\u5f55\u4e0e\u524d\u9762\u7684\u540c\u4e00\u539f\u6587\u5b58\u5728\u4e0d\u540c\u8bd1\u6587\uff0c\u8bf7\u5148\u6d88\u9664\u51b2\u7a81\u3002')
        self.values[source] = target

    def finish(self):
        if not self.values:
            raise DictionaryImportError(ui_source('No valid entries were found for the selected language pair.'))
        return [{'source': source, 'target': target} for source, target in self.values.items()]


def _header(value: str) -> str:
    return unicodedata.normalize('NFKC', value).strip().casefold().replace(' ', '_')


def _delimited(text: str, delimiter: str, source_lang: str, target_lang: str):
    result = _Records()
    columns = None
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    for row in reader:
        if not row or all(not value.strip() for value in row):
            continue
        if columns is None:
            sources, targets = [], []
            for index, value in enumerate(row):
                header = _header(value)
                if header in _SOURCE_HEADERS:
                    sources.append(index)
                elif header in _TARGET_HEADERS:
                    targets.append(index)
                else:
                    try:
                        language = _language(header)
                    except DictionaryImportError:
                        continue
                    if language == source_lang:
                        sources.append(index)
                    elif language == target_lang:
                        targets.append(index)
            if sources or targets:
                if len(sources) != 1 or len(targets) != 1:
                    raise DictionaryImportError(ui_source('Headers must identify one source column and one translation column, such as source,target or word,translation.'))
                columns = sources[0], targets[0], len(row)
                continue
            if len(row) != 2:
                raise DictionaryImportError(ui_source('A dictionary without a header must have exactly two columns. More columns require source and translation headers.'))
            columns = 0, 1, 2
        source_column, target_column, width = columns
        if len(row) != width:
            raise DictionaryImportError(f'\u7b2c {reader.line_num} \u884c\u7684\u5217\u6570\u4e0e\u8868\u5934\u6216\u9996\u884c\u4e0d\u4e00\u81f4\u3002')
        result.add(row[source_column], row[target_column])
    return result.finish()


def _json_object(pairs):
    if len(pairs) > MAX_ENTRIES:
        raise DictionaryImportError(ui_source('The JSON object exceeds the 100,000-item limit. Split it before importing.'))
    obj = {}
    for key, value in pairs:
        if key in obj and obj[key] != value:
            raise DictionaryImportError(ui_source('The JSON object has duplicate field names with different values. Resolve the conflicts first.'))
        obj[key] = value
    return obj


def _json(text):
    # Bound structure before json.loads allocates a deeply nested object tree.
    depth=nodes=0; quoted=escaped=False
    for char in text:
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '[{':
            depth+=1;nodes+=1
            if depth>16 or nodes>MAX_ENTRIES+1:
                raise DictionaryImportError(ui_source('The JSON structure is too deeply nested or contains too many objects. Split the file.'))
        elif char in ']}':depth-=1
    def invalid_constant(_):
        raise DictionaryImportError(ui_source('JSON must not contain NaN or infinity.'))
    value = json.loads(text, object_pairs_hook=_json_object, parse_constant=invalid_constant)
    records = _Records()
    if isinstance(value, dict):
        for source, target in value.items():
            records.add(source, target)
    elif isinstance(value, list):
        for row, item in enumerate(value, 1):
            if not isinstance(item, dict) or 'source' not in item or 'target' not in item:
                raise DictionaryImportError(f'\u7b2c {row} \u6761 JSON \u8bb0\u5f55\u9700\u8981 source \u548c target \u5b57\u6bb5\u3002')
            records.add(item['source'], item['target'])
    else:
        raise DictionaryImportError(ui_source('A JSON dictionary must map source text to translations, or be an array with source/target fields.'))
    return records.finish()


def _tag(element):
    return element.tag.rsplit('}', 1)[-1]


def _tmx(text, source_lang, target_lang):
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.IGNORECASE):
        raise DictionaryImportError(ui_source('TMX must not contain DTD or entity declarations. Export a dictionary without them.'))
    records = _Records()
    stack = []
    body = None
    units = nodes = 0
    for event, element in ET.iterparse(io.StringIO(text), events=('start', 'end')):
        tag = _tag(element)
        if event == 'start':
            stack.append(tag)
            nodes += 1
            if len(stack) > 64 or nodes > 1_000_000:
                raise DictionaryImportError(ui_source('The TMX structure is too deeply nested or contains too many elements. Split it into smaller files.'))
            if len(stack) == 1 and tag != 'tmx':
                raise DictionaryImportError(ui_source('The XML root element must be tmx.'))
            if stack == ['tmx', 'body']:
                if body is not None:
                    raise DictionaryImportError(ui_source('TMX must have only one body element.'))
                body = element
            continue
        if tag == 'tu':
            if stack != ['tmx', 'body', 'tu']:
                raise DictionaryImportError(ui_source('TMX tu records must be direct children of body.'))
            units += 1
            if units > MAX_ENTRIES:
                raise DictionaryImportError(ui_source('TMX exceeds the 100,000-record limit. Split it before importing.'))
            found = [[], []]
            for tuv in element:
                if _tag(tuv) != 'tuv':
                    continue
                language = tuv.attrib.get(_XML_LANG, tuv.attrib.get('lang', ''))
                selected = [_language_score(language, source_lang), _language_score(language, target_lang)]
                if all(score is None for score in selected):
                    continue
                segments = [seg for seg in tuv if _tag(seg) == 'seg']
                if len(segments) != 1:
                    raise DictionaryImportError(f'TMX \u7b2c {units} \u6761\u8bb0\u5f55\u7f3a\u5c11\u552f\u4e00 seg \u6587\u672c\u3002')
                content = ''.join(segments[0].itertext())
                for index, score in enumerate(selected):
                    if score is not None:
                        found[index].append((score, content))
            if all(found):
                pair = []
                for options in found:
                    priority = min(score for score, _ in options)
                    texts = {_field(value, units) for score, value in options if score == priority}
                    if len(texts) != 1:
                        raise DictionaryImportError(f'TMX \u7b2c {units} \u6761\u8bb0\u5f55\u542b\u591a\u4e2a\u51b2\u7a81\u8bed\u8a00\u7248\u672c\uff0c\u8bf7\u9009\u62e9\u66f4\u5177\u4f53\u7684\u8bed\u8a00\u3002')
                    pair.append(texts.pop())
                records.add(*pair)
            if body is not None:
                body.remove(element)
            element.clear()
        stack.pop()
    if body is None:
        raise DictionaryImportError(ui_source('The TMX file has no body element.'))
    return records.finish()


def parse_dictionary(path, source_lang: str, target_lang: str) -> list[dict[str, str]]:
    """Return deduplicated entries, or fail completely with a safe diagnostic.

    Exact duplicates collapse; a conflicting translation for the same source
    rejects the file. CSV/TSV/JSON have no language metadata: the selected pair
    applies to the entire file. TMX selects that pair from each translation unit.
    """
    source_lang, target_lang = _language(source_lang), _language(target_lang)
    if source_lang == target_lang:
        raise DictionaryImportError(ui_source('Choose different source and target languages.'))
    try:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix not in {'.csv', '.tsv', '.json', '.tmx'}:
            raise DictionaryImportError(ui_source('Supported dictionary formats: CSV, TSV, JSON, and TMX.'))
        path = local_file_path(path)
        text = _read_text(path)
        if suffix in {'.csv', '.tsv'}:
            return _delimited(text, ',' if suffix == '.csv' else '\t', source_lang, target_lang)
        if suffix == '.json':
            return _json(text)
        return _tmx(text, source_lang, target_lang)
    except DictionaryImportError:
        raise
    except (csv.Error, json.JSONDecodeError, ET.ParseError, RecursionError):
        raise DictionaryImportError(ui_source('Unable to parse the dictionary. Check delimiters, quotation marks, or the JSON/TMX structure.')) from None
    except (OSError, ValueError, TypeError, OverflowError):
        raise DictionaryImportError(ui_source('Unable to read or parse the dictionary. Check its format and encoding.')) from None
