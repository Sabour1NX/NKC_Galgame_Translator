# SPDX-License-Identifier: MIT
import pytest

from nkc_galgame_translator.tuning import BOOLEAN_FIELDS, NUMERIC_FIELDS, TUNING_DEFAULTS, validate_tuning


def test_defaults_and_concurrency_share_one_limit():
    assert validate_tuning({}) == TUNING_DEFAULTS
    for limit in (1, 4, 16):
        result = validate_tuning({'translation_workers': str(limit), 'max_concurrency': 99})
        assert result['translation_workers'] == result['max_concurrency'] == limit
    assert 'api_key' not in validate_tuning({'api_key': 'synthetic-only'})


def test_unlimited_switch_keeps_the_finite_quota_for_later_restore():
    assert validate_tuning({})['unlimited_requests'] is False
    for quota in (0,20,10000):
        for enabled in (True,False):
            saved=validate_tuning({'max_requests':quota,'unlimited_requests':enabled})
            assert saved['max_requests']==quota and saved['unlimited_requests'] is enabled


@pytest.mark.parametrize('name', NUMERIC_FIELDS)
def test_each_integer_limit_is_enforced(name):
    _, minimum, maximum, _ = NUMERIC_FIELDS[name]
    assert validate_tuning({name: minimum})[name] == minimum
    settings={name:maximum}
    if name=='overlay_font_min':settings['overlay_font_max']=maximum
    assert validate_tuning(settings)[name] == maximum
    for value in (minimum - 1, maximum + 1, 1.0, float('nan'), True, '1.5', '1e2', ''):
        with pytest.raises(ValueError):
            validate_tuning({name: value})


@pytest.mark.parametrize('name', BOOLEAN_FIELDS)
def test_boolean_inputs_are_not_coerced(name):
    for value in (False, True):
        assert validate_tuning({name: value})[name] is value
    for value in ('true', 'false', 0, 1, None):
        with pytest.raises(ValueError):
            validate_tuning({name: value})


@pytest.mark.parametrize('value', [None, [], 1, 'settings'])
def test_non_mapping_rejected(value):
    with pytest.raises(ValueError):
        validate_tuning(value)


@pytest.mark.parametrize('value', ['', ' '*8, 'x'*32, '😀'*16, '\ud800', 'Arial\x00Hidden',
                                  'Arial\n', '\tArial', '\u202eArial', 1, None])
def test_font_names_reject_invalid_gdi_names(value):
    with pytest.raises(ValueError):
        validate_tuning({'overlay_font_family': value})


def test_font_name_unicode_unit_limit_and_normalization():
    assert validate_tuning({'overlay_font_family':'  \u5b8b\u4f53  '})['overlay_font_family'] == '\u5b8b\u4f53'
    assert validate_tuning({'overlay_font_family':'\u5b57'*31})['overlay_font_family'] == '\u5b57'*31
    assert validate_tuning({'overlay_font_family':'😀'*15+'x'})['overlay_font_family'] == '😀'*15+'x'
    for value in ('zh-CN','en','ja'):
        assert validate_tuning({'app_language':value})['app_language'] == value
    for value in ('English','fr',True,[],None):
        with pytest.raises(ValueError):validate_tuning({'app_language':value})
