# SPDX-License-Identifier: MIT
"""Conservative, bounded evidence of corrupt English menu OCR.

This is deliberately not a spellchecker: unknown names and vocabulary are not
evidence of bad OCR. Only a short, complete menu/action phrase with at least two
damaged content words and explainable glyph confusions is rejected. Callers keep
the original game pixels; this module never returns a guessed correction.
"""
from functools import lru_cache
import re
import unicodedata


SUSPECT_MENU_TEXT = 'suspect_ocr_menu'
MAX_TEXT_CHARS = 4096
MAX_LINES = 32
MAX_LINE_CHARS = 160
MAX_WORD_CHARS = 32

# Whole UI phrases, independent of any particular game or its translation.
_PHRASES = (
    'new game', 'old game', 'load game', 'save game', 'start game',
    'continue game', 'resume game', 'quit game', 'exit game', 'restart game',
    'new or old game', 'new or load game', 'new or saved game',
    'start new game', 'load saved game', 'save current game',
    'continue or exit', 'continue or quit', 'start or quit',
    'main menu', 'game menu', 'pause menu', 'game options', 'game settings',
    'sound settings', 'video settings', 'audio settings', 'display settings',
    'controller settings', 'keyboard settings',
    'return to title', 'return to main menu', 'back to main menu',
    'exit to desktop', 'press enter', 'press enter to continue',
    'press any key', 'press any key to continue', 'press escape to return',
)
_TEMPLATES = {}
for _phrase in _PHRASES:
    _words = tuple(_phrase.split())
    _TEMPLATES.setdefault(len(_words), []).append(_words)
_TEMPLATES = {count: tuple(phrases) for count, phrases in _TEMPLATES.items()}
_FUNCTION_WORDS = frozenset(('a', 'an', 'and', 'or', 'to', 'the', 'of', 'for', 'any'))
# Parenthesized hotkeys are sometimes omitted by OCR, e.g. (O)ld -> ld.
# Only the first glyph of an ordinary menu action can use this transition.
_HOTKEY_WORDS = frozenset(('new', 'old', 'load', 'save', 'start', 'continue',
                          'resume', 'quit', 'exit', 'restart'))
_GLYPH_GROUPS = ('1il', '0o', '5s', '8b', '2z', '3e', 'uwv', 'mn', 'ce')
_GLYPH_PAIRS = frozenset((left, right) for group in _GLYPH_GROUPS
                         for left in group for right in group if left != right)
_CLUSTERS = (('rn', 'm'), ('m', 'rn'), ('vv', 'w'), ('w', 'vv'),
             ('cl', 'd'), ('d', 'cl'))
_HOTKEY = re.compile(r'[\[(]([A-Za-z])[\])]')
_ALLOWED = re.compile(r"[A-Za-z0-9 \t.,!?;:/()\[\]<>_'’\"-]+\Z")
_WORDS = re.compile(r"[a-z0-9]+(?:['’][a-z0-9]+)*")


@lru_cache(maxsize=1024)
def _word_cost(observed, expected):
    """Return 0..2 for supported OCR changes, 3 for unrelated words.

    The cache is bounded and only holds short token pairs in process memory.
    Generic spelling substitutions/insertion/deletion are not allowed.
    """
    if observed == expected:
        return 0
    if not observed or len(observed) > MAX_WORD_CHARS or abs(len(observed) - len(expected)) > 2:
        return 3
    rows, columns = len(observed), len(expected)
    costs = [[3] * (columns + 1) for _ in range(rows + 1)]
    costs[0][0] = 0
    if expected in _HOTKEY_WORDS:
        costs[0][1] = 1
    for i in range(rows + 1):
        for j in range(columns + 1):
            cost = costs[i][j]
            if cost > 2 or i == rows or j == columns:
                continue
            if observed[i] == expected[j]:
                costs[i + 1][j + 1] = min(costs[i + 1][j + 1], cost)
            elif (observed[i], expected[j]) in _GLYPH_PAIRS:
                costs[i + 1][j + 1] = min(costs[i + 1][j + 1], cost + 1)
            for old, new in _CLUSTERS:
                if observed.startswith(old, i) and expected.startswith(new, j):
                    ni, nj = i + len(old), j + len(new)
                    costs[ni][nj] = min(costs[ni][nj], cost + 1)
            # Reading order can reverse neighboring glyphs. Short function
            # words cannot use this rule, which would create broad false hits.
            if rows >= 4 and columns >= 4 and i + 1 < rows and j + 1 < columns:
                if observed[i] == expected[j + 1] and observed[i + 1] == expected[j]:
                    costs[i + 2][j + 2] = min(costs[i + 2][j + 2], cost + 1)
    return min(3, costs[rows][columns])


def _suspect_line(line):
    if len(line) > MAX_LINE_CHARS:
        return False
    line = unicodedata.normalize('NFKC', line).strip()
    if not line or len(line) > MAX_LINE_CHARS or not _ALLOWED.fullmatch(line):
        return False
    # Removing hotkey delimiters is analysis-only. Nothing is rewritten in
    # the caller, sent to the network, or offered as replacement text.
    words = tuple(_WORDS.findall(_HOTKEY.sub(r'\1', line).lower()))
    if not 2 <= len(words) <= 8 or any(len(word) > MAX_WORD_CHARS for word in words):
        return False
    templates = _TEMPLATES.get(len(words), ())
    if words in templates:
        return False
    for template in templates:
        total = damaged = 0
        for observed, expected in zip(words, template):
            cost = _word_cost(observed, expected)
            if cost > 2:
                break
            total += cost
            if total > 4:
                break
            if cost and expected not in _FUNCTION_WORDS:
                damaged += 1
        else:
            if damaged >= 2:
                return True
    return False


def rejection_reason(text: str, source_lang: str) -> str | None:
    """Return a fixed rejection code or None, without correcting the input.

    Only explicit English scopes are inspected. At most 32 physical lines and
    4096 characters are accepted for analysis; excessive/unsupported input is
    left to the caller's normal validation. One suspect line rejects its whole
    object so a merged paragraph cannot hide an invalid fragment.
    """
    if not isinstance(text, str) or not isinstance(source_lang, str):
        return None
    if source_lang.strip().lower().split('-')[0] != 'en' or len(text) > MAX_TEXT_CHARS:
        return None
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        return None
    return SUSPECT_MENU_TEXT if any(_suspect_line(line) for line in lines) else None
