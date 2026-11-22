# SPDX-License-Identifier: MIT
"""Bounded display-value checks for OCR objects, without guessing translations.

The caller retains original game pixels for a returned reason. Unknown words,
names and capital letters alone are never evidence that translation is useless.
This module neither corrects OCR nor accesses a dictionary, network or process.
"""
from __future__ import annotations

import re
import unicodedata
from .literal_rules import only_literals

MAX_TEXT_CHARS = 4096
MAX_LINES = 32
MAX_CODE_LINE_CHARS = 80
MAX_COMPARISON_CHARS = 64000

# Do not include ordinary English menu/action words (EXIT, HELP, SCAN, etc.).
# ARM is a real English word, so it is handled only with a numeric HUD value.
_HUD_ABBREVIATIONS = frozenset({
    'HP', 'MP', 'SP', 'AP', 'XP', 'EXP', 'LV', 'LVL', 'ATK', 'DEF', 'SPD',
    'STR', 'DEX', 'INT', 'VIT', 'STA', 'CRT', 'EVA', 'ACC', 'RES',
    'FPS', 'CPU', 'GPU', 'RAM', 'VRAM', 'HUD', 'DPS', 'RPM', 'N/A',
})
_KEY = re.compile(r'(?:[A-Za-z]|F(?:[1-9]|1[0-9]|2[0-4])|Ctrl|Alt|Esc|Tab|'
                  r'Del|Ins|PgUp|PgDn)', re.I)
_BOXED_KEY = re.compile(r'(?:Shift|Space|Enter|Backspace)', re.I)
_MEASUREMENT = re.compile(
    r'[+-]?\d+(?:[.,]\d+)?(?:[/:-]\d+(?:[.,]\d+)?)?\s*'
    r'(?:%|HP|MP|XP|FPS|Hz|kHz|MHz|GHz|ms|s|m|km|cm|mm|m/s|km/h|KB|MB|GB|TB)', re.I)
_CLOCK = re.compile(
    r'[0-9OoØøAa]{1,2}:[0-9OoØøAa]{2}(?::[0-9OoØøAa]{2})?\s*HRS'
    r'(?:\s*\d{1,2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{1,4})?', re.I)
_HUD_NUMERIC = re.compile(
    r'(?:' + '|'.join(re.escape(token) for token in sorted(
        _HUD_ABBREVIATIONS | {'ARM', 'ARH', 'SYS', 'SHD', 'SHLD', 'CF', 'LF'},
        key=lambda token: (-len(token), token))) + r')\s*[:=]?\s*'
    r'[+-]?\d+(?:[.,/:]\d+)*[A-Z]{0,3}%?'
    r'(?:\s+[+-]?\d+(?:[.,/:]\d+)*[A-Z]{0,3}%?){0,2}', re.I)
_HUD_SYS_CODE = re.compile(r'SYS\s+[A-Z]\s+[A-Z]{2,3}', re.I)
_HUD_FLAG = re.compile(r'(?:CF|LF)\s+(?:HS|LS|ON|OFF)')
_GLYPH_WORD = re.compile(r'[A-Za-z1]{3,24}')
_GLYPH_REPEAT = re.compile(r'i{3,}|l{3,}|1{3,}', re.I)
_BALANCED = {'[': ']', '(': ')', '<': '>', '{': '}'}


def _unbox(text):
    """Analysis only: remove at most two matched decorative wrappers."""
    for _ in range(2):
        if len(text) > 2 and _BALANCED.get(text[0]) == text[-1]:
            text = text[1:-1].strip()
        else:
            break
    return text


def _row_reason(text, english):
    if not any(char.isalpha() and char!='\u30fc' for char in text):
        return 'nonlinguistic'
    if not english or len(text) > MAX_CODE_LINE_CHARS:
        return None
    value = _unbox(text)
    # "Enter" or "Space" alone can be real menu text; require visible keycap
    # wrappers for those ordinary words rather than guessing from capitalization.
    if _KEY.fullmatch(value) or (value != text and _BOXED_KEY.fullmatch(value)):
        return 'isolated_key'
    if _CLOCK.fullmatch(value) or _MEASUREMENT.fullmatch(value):
        return 'hud_code'
    if value in _HUD_ABBREVIATIONS:
        return 'hud_code'
    tokens = value.split()
    if 1 < len(tokens) <= 6 and all(token in _HUD_ABBREVIATIONS for token in tokens):
        return 'hud_code'
    # A known gauge prefix plus a numeric/code value is stronger evidence than
    # arbitrary uppercase words. Never reject a name simply for being uppercase.
    if _HUD_NUMERIC.fullmatch(value) or _HUD_SYS_CODE.fullmatch(value) or _HUD_FLAG.fullmatch(value):
        return 'hud_code'
    # Repeated *identical* thin glyphs are evidence for an isolated OCR fragment
    # like "Siiius". Mixed i/l runs occur in real words such as "million".
    if _GLYPH_WORD.fullmatch(value) and _GLYPH_REPEAT.search(value):
        return 'glyph_noise'
    return None


def preservation_reason(text: str, source_lang: str = 'en') -> str | None:
    """Return a fixed reason only when every physical row lacks display value.

    Numeric/symbol-only rows are language independent. Key names, known HUD
    grammars and repeated-glyph fragments are checked only in explicit English
    scopes. At most 4096 input/normalized characters and 32 rows are inspected.
    Any ordinary row keeps a multiline object eligible, including mixed dialogue
    and counters. Missing/oversized/unsupported input is left to caller validation.
    """
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
        return None
    if only_literals(text):
        return 'protected_literal'
    normalized = unicodedata.normalize('NFKC', text)
    if len(normalized) > MAX_TEXT_CHARS or '\x00' in normalized:
        return None
    lines = normalized.splitlines()
    if len(lines) > MAX_LINES:
        return None
    english = (isinstance(source_lang, str)
               and source_lang.strip().replace('_', '-').lower().split('-')[0] == 'en')
    reasons = []
    for line in lines:
        if line.strip():
            reason = _row_reason(line.strip(), english)
            if reason is None:
                return None
            reasons.append(reason)
    if not reasons:
        return 'nonlinguistic'
    return reasons[0] if len(set(reasons)) == 1 else 'nontranslatable_rows'


def unchanged_translation(source: str, translated: str) -> bool:
    """Compare raw, unlabeled text without erasing punctuation or real wording.

    NFKC, case folding and collapsed whitespace make formatting-only differences
    equivalent. Nonempty results only; no removal of labels, bracket pairs,
    punctuation or diacritics. Call on raw output before display decoration.
    Both inputs are bounded to 64000 characters, including normalized results.
    """
    if not all(isinstance(value, str) and len(value) <= MAX_COMPARISON_CHARS
               for value in (source, translated)):
        return False
    values = []
    for value in (source, translated):
        value = unicodedata.normalize('NFKC', value).casefold()
        if len(value) > MAX_COMPARISON_CHARS:
            return False
        if '\x00' in value:
            return False
        values.append(' '.join(value.split()))
    return bool(values[0]) and values[0] == values[1]
