# SPDX-License-Identifier: MIT
"""Content-value filtering without API calls, corrections or game assets."""
import pytest

from nkc_galgame_translator.translatability import preservation_reason, unchanged_translation


@pytest.mark.parametrize('text', ['', '  ', '300', '\uff11\uff12\uff13', '05', '0/100',
    '99.5%', '+20', '00:30', '∞ → ★', '---', '...!?', '😀', '①②③'])
@pytest.mark.parametrize('language', ['en', 'ja', 'zh-Hans', 'fr', 'auto'])
def test_numeric_and_symbol_only_rows_keep_original_in_every_language(text, language):
    assert preservation_reason(text, language) == 'nonlinguistic'


@pytest.mark.parametrize('text', ['A', 'x', '[F1]', '(F12)', '<Esc>', 'Tab',
    '[Enter]', '[SPACE]', '{Shift}', '\uff26\uff12\uff14'])
def test_isolated_key_indicators_keep_original(text):
    assert preservation_reason(text, 'en-US') == 'isolated_key'


@pytest.mark.parametrize('text', ['ARM 300', 'ARH 4HH', 'CF 05', 'LF HS',
    'SYS f ebm', 'sys f ebn', 'SYS: 100/100', 'SHLD 50%',
    'HP', 'MP', 'XP', 'FPS', 'HP MP XP', 'N/A', '60fps', '12 km/h',
    '00:00HRS01MAR12', 'aø:øa HRS', '12:34:56 HRS', '[(HP)]'])
def test_known_hud_grammars_keep_original_without_generic_acronym_rule(text):
    assert preservation_reason(text, 'en') == 'hud_code'


@pytest.mark.parametrize('text', ['siiius', 'Siiius', '\uff33\uff49\uff49\uff49\uff55\uff53', 's111us', 'slllus'])
def test_isolated_repeated_thin_glyph_noise_keeps_original(text):
    assert preservation_reason(text, 'en') == 'glyph_noise'


@pytest.mark.parametrize('text', ['(Gun laser)', 'Gun laser', 'NEW GAME', 'EXIT',
    'PRINCESS BLUE', 'CHART', 'HELP', 'STATUS', 'QUERY', 'SCAN', 'COCKPIT',
    'ALERT', 'GO ON', 'NO GO', 'ARM', 'arm', 'Arm the laser', 'ARM THE GUN',
    'CF model', 'SYS error', 'SYS normal', 'SYS ready', 'ARM OFF', 'LF LOW',
    'ARM THE GUN 3', 'SYS HAS 2', 'ENTER', 'SPACE', 'Shift',
    'Health 100', 'LEVEL 5', '100 gold', 'Sirius', 'Karonus', 'WILL',
    'millimeter', 'million', 'illicit', 'illusion', 'Hawaii', 'Hawaiian',
    'Welcome to the PRINCESS BLUE.', 'press F1', 'New Game Plus',
    'Captain: wait!', '\u7d05\u9b54\u9928', '\u59cb\u3081\u308b', '\u5f00\u59cb', 'åäö', 'siIius people',
    'Unknown words', 'UNFAMILIAR NAME', 'ABCDEF', 'ARH CHART'])
def test_real_or_ambiguous_text_remains_eligible(text):
    assert preservation_reason(text, 'en') is None


@pytest.mark.parametrize('language', ['en', 'EN-us', 'en_GB'])
def test_english_aliases_are_supported(language):
    assert preservation_reason('Siiius', language) == 'glyph_noise'


@pytest.mark.parametrize('language', ['ja', 'de', 'fr', 'zh-Hans', 'auto', 'english', None])
def test_unsupported_scopes_do_not_guess_acronyms_or_english_ocr(language):
    assert preservation_reason('Siiius', language) is None
    assert preservation_reason('HP', language) is None


def test_one_real_row_keeps_whole_multiline_object_eligible():
    assert preservation_reason('HP\n300\nGun laser', 'en') is None
    assert preservation_reason('STATUS\n00:00HRS01MAR12', 'en') is None
    assert preservation_reason('Siiius\nWelcome aboard.', 'en') is None
    assert preservation_reason('HP\nMP\n300', 'en') == 'nontranslatable_rows'
    assert preservation_reason('300\n500', 'ja') == 'nonlinguistic'


@pytest.mark.parametrize('text', [None, 3, 'X' * 4097, 'A\n' * 33, 'HP\x00',
                                'Siiius' + ' ' * 4091])
def test_unsupported_input_is_left_to_caller_validation(text):
    assert preservation_reason(text, 'en') is None


@pytest.mark.parametrize(('source', 'translated'), [
    ('Sirius', 'Sirius'), ('SIRIUS', 'sirius'), ('Sirius  A', 'sirius\nA'),
    (' \uff33\uff49\uff52\uff49\uff55\uff53 ', 'sirius'), ('HP: 300', 'hp: 300'),
    ('Café', 'Cafe\u0301'), ('[Sirius]', '[SIRIUS]'), ('300', '\uff13\uff10\uff10'),
])
def test_unchanged_output_matches_only_normalized_raw_text(source, translated):
    assert unchanged_translation(source, translated)


@pytest.mark.parametrize(('source', 'translated'), [
    ('Sirius', '\u5929\u72fc\u661f'), ('Laser', '\u6fc0\u5149'), ('Sirius', '[\u82f1\u8bed\uff1aSirius]'),
    ('[Sirius]', 'Sirius'), ('Sirius?', 'Sirius!'), ('Café', 'Cafe'),
    ('New game', 'Newgame'), ('ARM 300', 'ARM 30'), ('one\ntwo', 'onetwo'),
    ('', ''), (' ', ' '), (None, 'None'), ('HP\x00', 'HP\x00'),
    ('a' * 64001, 'a' * 64001),
])
def test_real_changes_and_invalid_output_are_not_hidden(source, translated):
    assert not unchanged_translation(source, translated)


def test_analysis_does_not_mutate_or_return_corrected_text():
    source = '\uff33\uff49\uff49\uff49\uff55\uff53'
    assert preservation_reason(source, 'en') == 'glyph_noise'
    assert source == '\uff33\uff49\uff49\uff49\uff55\uff53'
# Numeric readouts use the same explicitly enumerated HUD prefixes as bare
# abbreviations. Meaningful labels such as "Health 300" remain translatable.
@pytest.mark.parametrize('text', ['HP 300', 'MP: 20/40', 'ATK 35', 'FPS60', 'LV 5'])
def test_known_hud_prefix_with_numeric_value(text):
    assert preservation_reason(text, 'en') == 'hud_code'

