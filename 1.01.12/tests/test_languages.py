# SPDX-License-Identifier: MIT
import pytest

from nkc_galgame_translator.languages import detect_source_language, label_translation, source_label, foreign_language_groups


@pytest.mark.parametrize('text,selected,expected', [
    ('Welcome to the Scarlet Mansion.', 'ja', 'en'),
    ('\uff37\uff45\uff4c\uff43\uff4f\uff4d\uff45 \uff22\uff21\uff23\uff2b\uff01', 'ja', 'en'),
    ('\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002', 'en', 'ja'),
    ('ESC \u3067\u9589\u3058\u308b', 'ja', 'ja'),
    ('\uff79\uff9e\uff70\uff91\u3092\u958b\u59cb\u3059\u308b', 'en', 'ja'),
    ('\u7d05\u9b54\u9928', 'ja', 'ja'),
    ('\u7ea2\u9b54\u9986', 'zh-Hans', 'zh-Hans'),
    ('Welcome', 'zh-Hans', 'zh-Hans'),
    ('Bonjour', 'fr', 'fr'),
    ('Willkommen', 'de', 'de'),
    ('Bienvenido', 'es', 'es'),
    ('\u4e2d\u6587 English', 'ja', 'ja'),
    ('12345', 'ja', 'ja'),
    ('---', 'en', 'en'),
    ('Café', 'ja', 'ja'),
])
def test_conservative_source_language_routing(text, selected, expected):
    assert detect_source_language(text, selected) == expected


def test_label_stream_preserves_newlines_and_empty_coverage():
    assert label_translation('', 'ja', False) == ''
    assert label_translation('\u6b22\u8fce\n\u6765\u5230', 'en', False) == '[\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230'
    assert label_translation('\u6b22\u8fce\n\u6765\u5230\u7ea2\u9b54\u9986', 'en', True) == '[\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230\u7ea2\u9b54\u9986]'
    assert label_translation('\u6b22\u8fce', 'ja') == '[\u65e5\u8bed\uff1a\u6b22\u8fce]'


def test_selected_languages_have_display_names():
    assert source_label('zh-Hans') == '\u7b80\u4f53\u4e2d\u6587'
    assert source_label('zh-Hant') == '\u7e41\u4f53\u4e2d\u6587'
    assert source_label('en-US') == '\u82f1\u8bed'
    assert source_label('fr') == '\u6cd5\u8bed'
    assert source_label('ko') == '\u97e9\u8bed'
    assert source_label('xx') == 'xx'


@pytest.mark.parametrize('label,brackets,partial,complete', [
    (True,True,'[\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230','[\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230]'),
    (True,False,'\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230','\u82f1\u8bed\uff1a\u6b22\u8fce\n\u6765\u5230'),
    (False,True,'[\u6b22\u8fce\n\u6765\u5230','[\u6b22\u8fce\n\u6765\u5230]'),
    (False,False,'\u6b22\u8fce\n\u6765\u5230','\u6b22\u8fce\n\u6765\u5230'),
])
def test_independent_source_and_bracket_switches(label,brackets,partial,complete):
    options=dict(show_source_label=label,show_translation_brackets=brackets)
    assert label_translation('', 'en', False, **options) == ''
    assert label_translation('\u6b22\u8fce\n\u6765\u5230', 'en', False, **options) == partial
    assert label_translation('\u6b22\u8fce\n\u6765\u5230', 'en', True, **options) == complete
    # Literal game/model brackets are content; disabling decoration never edits them.
    assert '[\u83dc\u5355]' in label_translation('[\u83dc\u5355]', 'en', True, **options)


@pytest.mark.parametrize('field', ['show_source_label','show_translation_brackets'])
def test_display_switches_must_be_boolean(field):
    with pytest.raises(ValueError):label_translation('x','en',**{field:'false'})


@pytest.mark.parametrize('sources,target,expected', [
    (['en','en-US','en_GB'],'zh-Hans',{'en'}),
    (['zh-CN','zh-Hant','ZH_hans','en-US'],'zh-Hans',{'en'}),
    (['en-US','ja-JP','zh-CN'],'zh-Hant',{'en','ja'}),
    (['en','ja','ja-JP'],'en-US',{'ja'}),
    (['','  ','zh-Hans'],'zh-CN',set()),
])
def test_mixed_foreign_language_count_excludes_target_and_region_aliases(sources,target,expected):
    assert foreign_language_groups(sources,target)==expected


def test_localized_source_tag_keeps_game_text_intact():
    original = 'Welcome'
    assert label_translation(original, 'ja', label_language='en') == '[Japanese: Welcome]'
    assert label_translation(original, 'en', label_language='ja') == '[\u82f1\u8a9e\uff1aWelcome]'
