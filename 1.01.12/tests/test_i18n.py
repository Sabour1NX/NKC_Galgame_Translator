# SPDX-License-Identifier: MIT
import pytest
from nkc_galgame_translator.i18n import detect_system_language, initial_language, LanguageLabels


@pytest.mark.parametrize('langid,expected',[(0x0804,'zh-CN'),(0x0404,'zh-CN'),(0x0409,'en'),(0x0809,'en'),(0x0411,'ja'),(0x040c,'en'),(None,None)])
def test_os_ui_language_mapping(langid,expected):
    if expected is None:assert detect_system_language() in {'zh-CN','en','ja'}
    else:assert detect_system_language(langid)==expected


def test_manual_language_overrides_os(monkeypatch):
    monkeypatch.setattr('nkc_galgame_translator.i18n.detect_system_language',lambda:'ja')
    assert initial_language({})=='ja'
    assert initial_language({'app_language':'en','app_language_selected':False})=='ja'
    assert initial_language({'app_language':'en','app_language_selected':True})=='en'
    assert initial_language({'app_language':'zh-CN'},interactive=False)=='zh-CN'
    assert initial_language({'app_language':'bogus','app_language_selected':True})=='ja'


def test_localized_language_choices_preserve_codes():
    mapping=LanguageLabels({'\u82f1\u8bed':'en','\u65e5\u8bed':'ja','\u7b80\u4f53\u4e2d\u6587':'zh-Hans'})
    assert mapping['English']==mapping['\u82f1\u8a9e']==mapping['\u82f1\u8bed']=='en'
    assert mapping['Japanese']==mapping['\u65e5\u672c\u8a9e']=='ja'
    assert mapping.get('Simplified Chinese')=='zh-Hans'
    assert list(mapping)==['\u82f1\u8bed','\u65e5\u8bed','\u7b80\u4f53\u4e2d\u6587']


def test_translated_agreements_retain_exact_mit():
    from pathlib import Path
    from nkc_galgame_translator.agreement import AGREEMENT_TEXT, MIT_LICENSE
    from nkc_galgame_translator.agreement_en import AGREEMENT_TEXT_EN
    from nkc_galgame_translator.agreement_ja import AGREEMENT_TEXT_JA
    root = Path(__file__).resolve().parents[1]
    assert MIT_LICENSE == (root / 'LICENSE').read_text(encoding='utf-8')
    for terms in (AGREEMENT_TEXT, AGREEMENT_TEXT_EN, AGREEMENT_TEXT_JA):
        assert terms.endswith(MIT_LICENSE)
        assert all(name in terms for name in ('Tesseract', 'SQLite', 'PyInstaller', 'DPAPI'))

def test_japanese_interface_beta_label_is_separate_from_game_language():
    from nkc_galgame_translator.i18n import NATIVE_NAMES, LANGUAGE_NAMES, translate, ui_source
    from nkc_galgame_translator.settings_ui import INTERFACE_LANGUAGE_LABELS
    assert NATIVE_NAMES['ja'] == '\u65e5\u672c\u8a9e (beta)'
    assert INTERFACE_LANGUAGE_LABELS[NATIVE_NAMES['ja']] == 'ja'
    assert LANGUAGE_NAMES[ui_source('Japanese')][1] == '\u65e5\u672c\u8a9e'
    assert translate(ui_source('App memory'), 'ja') == 'RAM \u4f7f\u7528\u91cf'
    assert translate(ui_source('Memory line color'), 'ja') == 'RAM / VRAM \u306e\u7dda\u8272'
