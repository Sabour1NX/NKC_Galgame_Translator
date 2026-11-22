# SPDX-License-Identifier: MIT
"""Pure UI-translation regressions; no Tcl interpreter, GUI, API, or disk writes."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nkc_galgame_translator import i18n
from nkc_galgame_translator.language_setup import InitializationDialog
from nkc_galgame_translator.settings_ui import DictionaryImportDialog


@pytest.mark.parametrize('original,english,japanese', [
    ('\u5f53\u524d\u69fd\u4f4d 1 · \u5df2\u914d\u7f6e', 'Current slot 1 · Configured', '\u4f7f\u7528\u4e2d\u306e Slot 1\u30fb\u8a2d\u5b9a\u6e08\u307f'),
    ('\u69fd\u4f4d 2\n\u5f53\u524d\u4f7f\u7528 · \u5df2\u914d\u7f6e', 'Slot 2\nActive · Configured', 'Slot 2\n\u4f7f\u7528\u4e2d\u30fb\u8a2d\u5b9a\u6e08\u307f'),
    ('\u6b63\u5728\u7f16\u8f91\uff1a\u69fd\u4f4d 1\uff08\u5f53\u524d\u4f7f\u7528\uff09', 'Editing slot 1 (active)', '\u7de8\u96c6\u4e2d\uff1aSlot 1\uff08\u4f7f\u7528\u4e2d\uff09'),
    ('\u69fd\u4f4d 3 \u5df2\u542f\u7528 · \u4ec5\u672c\u5730\u7ffb\u8bd1\u8bcd\u5178', 'Slot 3 active · Local dictionary only', 'Slot 3 \u3092\u4f7f\u7528\u4e2d\u30fb\u30ed\u30fc\u30ab\u30eb\u8f9e\u66f8\u306e\u307f'),
    ('\u7ffb\u8bd1\u5e76\u53d1\u4e0a\u9650\u987b\u4e3a 1 \u81f3 16 \u7684\u6574\u6570\u3002', 'Concurrent translations must be an integer from 1 to 16.', '\u7ffb\u8a33\u306e\u6700\u5927\u540c\u6642\u51e6\u7406\u6570 \u306f 1\uff5e16 \u306e\u6574\u6570\u306b\u3057\u3066\u304f\u3060\u3055\u3044\u3002'),
    ('\u5df2\u8fbe\u5230\u672c\u6b21\u542f\u52a8\u7684 80 \u6b21 API \u8bf7\u6c42\u9650\u989d\uff1b\u672c\u5730\u7f13\u5b58\u4ecd\u7136\u53ef\u7528\u3002',
     'This session’s limit of 80 API requests has been reached; Local cached translations remain available.',
     '\u4eca\u56de\u306e Session \u306e API \u4e0a\u9650 80 \u56de\u306b\u9054\u3057\u307e\u3057\u305f\u3002\u30ed\u30fc\u30ab\u30eb\u306e\u7ffb\u8a33 Cache \u306f\u5f15\u304d\u7d9a\u304d\u4f7f\u7528\u3067\u304d\u307e\u3059\u3002'),
])
def test_controlled_template_fields_translate_and_round_trip(original, english, japanese):
    assert i18n.translate(original, 'en') == english
    assert i18n.translate(english, 'ja') == japanese
    assert i18n.translate(japanese, 'zh-CN') == original


def test_catalog_reverse_lookup_has_no_ambiguous_display_aliases():
    aliases = {}
    for original, targets in i18n.catalog().items():
        for source in (original, *targets):
            assert aliases.setdefault(source, original) == original, source


@pytest.mark.parametrize('original,english,japanese', [
    ('\u5f00\u59cb\u7ffb\u8bd1', 'Start translation', '\u7ffb\u8a33\u958b\u59cb'),
    ('\u5f00\u59cb', 'Start', '\u958b\u59cb'),
    ('\u4ec5\u4f7f\u7528\u672c\u5730\u8bcd\u5178', 'Use local dictionary only', '\u30ed\u30fc\u30ab\u30eb\u8f9e\u66f8\u3060\u3051\u3092\u4f7f\u7528'),
    ('\u4ec5\u672c\u5730\u7ffb\u8bd1\u8bcd\u5178', 'Local dictionary only', '\u30ed\u30fc\u30ab\u30eb\u8f9e\u66f8\u306e\u307f'),
])
def test_different_buttons_and_statuses_remain_distinct_on_language_switch(original, english, japanese):
    assert i18n.translate(original, 'en') == english
    assert i18n.translate(english, 'ja') == japanese
    assert i18n.translate(japanese, 'zh-CN') == original


@pytest.mark.parametrize('profile', ['\u5f00\u59cb Welcome / Settings / \u8a2d\u5b9a', '{mode} {profile} ${x}', '\u6e38\u620f\u6863\u6848\uff1aStart\n\u539f\u6587 → \u8bd1\u6587'])
def test_import_scope_preserves_opaque_game_name_across_languages(profile):
    original = f'\u5bfc\u5165\u76ee\u6807\uff1aen → zh-Hans · \u6e38\u620f\u6863\u6848\uff1a{profile}'
    english = f'Import destination: en → zh-Hans · Game profile: {profile}'
    japanese = f'\u30a4\u30f3\u30dd\u30fc\u30c8\u5148\uff1aen → zh-Hans\u30fb\u30b2\u30fc\u30e0\u5225\u8a2d\u5b9a\uff1a{profile}'
    assert i18n.translate(original, 'en') == english
    assert i18n.translate(english, 'ja') == japanese
    assert i18n.translate(japanese, 'zh-CN') == original


@pytest.mark.parametrize('language', ['zh-CN', 'en', 'ja'])
def test_import_dialog_formats_ui_before_inserting_game_data(language):
    profile = 'Settings / \u8bbe\u7f6e / \u8a2d\u5b9a / {source}'
    dialog = DictionaryImportDialog.__new__(DictionaryImportDialog)
    dialog.app = SimpleNamespace(term_scope=lambda: (profile, 'en', 'zh-Hans'),
                                 tr=lambda text: i18n.translate(text, language))
    dialog.shared = SimpleNamespace(get=lambda: False)
    dialog.scope_label = Mock()
    dialog.commit_button = Mock()
    dialog.entries = object()
    dialog.preview_scope = object()
    dialog.invalidate()
    text = dialog.scope_label.configure.call_args.kwargs['text']
    assert text.endswith(profile)
    assert 'en → zh-Hans' in text
    assert dialog.entries is None and dialog.preview_scope is None
    dialog.commit_button.configure.assert_called_once_with(state='disabled')


def test_catalog_and_compiled_tables_are_immutable_reused_and_do_not_cache_data():
    catalog = i18n.catalog()
    tables = i18n._translation_tables()
    assert i18n.catalog() is catalog
    assert i18n._translation_tables() is tables
    with pytest.raises(TypeError):
        catalog['new'] = ('new', 'new')
    with pytest.raises(TypeError):
        tables[0]['new'] = ('new', 'new', 'new')
    before = set(tables[0])
    i18n.translate('\u5bfc\u5165\u76ee\u6807\uff1aen → zh-Hans · \u6e38\u620f\u6863\u6848\uff1aunique private game text', 'en')
    assert set(tables[0]) == before


@pytest.mark.parametrize('fail_save', [False, True])
def test_first_language_confirmation_saves_choice_before_applying_without_consent(fail_save):
    dialog = InitializationDialog.__new__(InitializationDialog)
    dialog.language = SimpleNamespace(get=lambda: 'en')
    original = {'app_language': 'ja', 'app_language_selected': False, 'agreement_version': ''}
    saved = {**original, 'app_language': 'en', 'app_language_selected': True}
    save = Mock(side_effect=OSError('no access') if fail_save else None, return_value=saved)
    app = SimpleNamespace(config=dict(original), config_store=SimpleNamespace(save=save),
                          apply_ui_language=Mock())
    dialog.app = app
    if fail_save:
        with pytest.raises(OSError):
            dialog.save_language()
        assert app.config == original
        app.apply_ui_language.assert_not_called()
    else:
        assert dialog.save_language()
        assert app.config == saved and not app.config['agreement_version']
        app.apply_ui_language.assert_called_once_with('en')
    save.assert_called_once_with(saved)
