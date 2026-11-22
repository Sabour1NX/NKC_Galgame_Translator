# SPDX-License-Identifier: MIT
"""High-precision menu OCR checks; names and normal dialogue stay eligible."""
import pytest

from nkc_galgame_translator.ocr_quality import rejection_reason


@pytest.mark.parametrize('text', [
    'Neu or Id gane?', 'NEU OR ID GANE?', '(N)eu or (I)d gane?',
    'L0ad garne', '5ave garne', 'Strat gane', 'Contlnue or exlt',
    'Maln rnenu', 'Pr3ss ent3r to continue', 'Pr3ss any k3y',
    'Nevv garne', 'Retum to rnain rnenu',
])
def test_multiple_corrupt_menu_words_preserve_source(text):
    assert rejection_reason(text, 'en') == 'suspect_ocr_menu'


@pytest.mark.parametrize('text', [
    'New or Old game?', '(N)ew or (O)ld game?', '[N]ew or [O]ld game?',
    'S(a)ve game', 'NEW GAME', 'Load game', 'Main menu',
    'Continue or Exit', 'Press [Enter] to continue', 'Press any key',
    'Game settings', 'Return to main menu', 'New Game Plus',
    'Neu or Old game?', 'New or Old gane?', 'Main rnenu', 'L0ad game',
    'Karonus system', 'PRINCESS BLUE', 'Id Software', 'Neu in Berlin',
    'New Dawn', 'Old Man', 'Dalfree', 'Manchi attack',
    'Your merchant ship picks up a distress beacon.', 'No life readings.',
    'New or old cane?', 'Save my game', 'A new name', 'Press F1 to continue',
    '\u30cb\u30e5\u30fc\u30b2\u30fc\u30e0', '\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d', 'Café menu', '\u6e38\u620f\u83dc\u5355',
    'Two new games', 'Saved game 3', 'Unknown words are not OCR evidence',
    'Neu or Id gane? This is a longer quotation about a typo.',
])
def test_valid_or_ambiguous_words_do_not_trigger_a_spellcheck(text):
    assert rejection_reason(text, 'en') is None


@pytest.mark.parametrize('language', ['en', 'en-US', 'en-GB', 'EN-us'])
def test_explicit_english_regional_scopes(language):
    assert rejection_reason('Neu or Id gane?', language) == 'suspect_ocr_menu'


@pytest.mark.parametrize('language', ['ja', 'de', 'fr', 'es', 'zh-Hans', 'auto', 'english', 'enoch', ''])
def test_other_languages_are_not_english_spellchecked(language):
    assert rejection_reason('Neu or Id gane?', language) is None


@pytest.mark.parametrize('separator', ['\n', '\r\n', '\r', '\u2028', '\u2029'])
def test_a_suspect_physical_line_rejects_whole_object_without_modification(separator):
    source = 'Welcome aboard.' + separator + 'Neu or Id gane?' + separator + 'Karonus system'
    unchanged = source[:]
    assert rejection_reason(source, 'en') == 'suspect_ocr_menu'
    assert source == unchanged


def test_no_correction_is_returned_or_invented_for_unknown_text():
    assert rejection_reason('Neu or Id gane?', 'en') == 'suspect_ocr_menu'
    assert rejection_reason('Completely unfamiliar invented names', 'en') is None
    assert rejection_reason('Welcome\nto the Karonus system.', 'en') is None


@pytest.mark.parametrize('text', ['', '123', 'x' * 100_000,
    ('Welcome\n' * 33) + 'Neu or Id gane?', 'Neu or Id gane?' + ' ' * 161,
    'Neu or Id gane?\x00', 'Neu or Id gane? 🔑', 'a' * 33 + ' garne'])
def test_bounded_and_unsupported_inputs_do_not_expand_matching(text):
    assert rejection_reason(text, 'en') is None


def test_non_strings_fail_open_to_caller_validation():
    assert rejection_reason(None, 'en') is None
    assert rejection_reason('Neu or Id gane?', None) is None


def test_nfkc_fullwidth_english_is_analysis_only():
    source = '\uff2e\uff45\uff55 \uff4f\uff52 \uff29\uff44 \uff47\uff41\uff4e\uff45\uff1f'
    assert rejection_reason(source, 'en-US') == 'suspect_ocr_menu'
    assert source == '\uff2e\uff45\uff55 \uff4f\uff52 \uff29\uff44 \uff47\uff41\uff4e\uff45\uff1f'
