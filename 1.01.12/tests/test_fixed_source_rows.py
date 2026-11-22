# SPDX-License-Identifier: MIT
"""Geometry boundary tests for the additive source-row native input."""
from types import MappingProxyType
import pytest
from nkc_galgame_translator.native import fixed_source_rows
from nkc_galgame_translator.presentation import OverlayState


def region(**extra):
    return dict(x=-100, y=50, w=200, h=60, _fixed_layout=True, **extra)


def values(row):
    return tuple(getattr(row, name) for name, _ in row._fields_)


def test_implicit_source_ink_is_relative_to_window_including_negative_monitors():
    rows = fixed_source_rows(region(_source_ink=[-98, 52, 195, 55]))
    assert values(rows[0]) == (0, 0, 200, 60, 2, 2, 195, 55, 0)


def test_frozen_physical_rows_keep_exact_geometry_and_font():
    data = (MappingProxyType(dict(x=2, y=1, w=180, h=24,
            ink_bounds=(4, 3, 175, 20), font_size=26)),
            MappingProxyType(dict(x=5, y=31, w=160, h=27, font_size=0)))
    rows = fixed_source_rows(region(_source_rows=data))
    assert values(rows[0]) == (2, 1, 180, 24, 4, 3, 175, 20, 26)
    assert values(rows[1]) == (5, 31, 160, 27, 5, 31, 160, 27, 0)


def test_unknown_multiline_geometry_stays_inside_original_equal_slots():
    assert [values(row)[:4] for row in fixed_source_rows(region(_source_line_count=3))] == [
        (0, 0, 200, 20), (0, 20, 200, 20), (0, 40, 200, 20)]
    assert fixed_source_rows(dict(x=0, y=0, w=100, h=30)) == []


@pytest.mark.parametrize('change', [
    {'x': -1}, {'y': -1}, {'w': 201}, {'h': 61}, {'x': True}, {'h': 0},
    {'font_size': 513}, {'ink_bounds': [0, 0, 201, 60]},
    {'ink_bounds': [True, 0, 10, 10]}, {'ink_bounds': [0, 0, 10]},
])
def test_invalid_source_row_cannot_extend_or_corrupt_overlay(change):
    row = dict(x=0, y=0, w=200, h=60, **{})
    row.update(change)
    with pytest.raises(ValueError):
        fixed_source_rows(region(_source_rows=[row]))


def test_geometry_debounce_holds_ink_and_row_evidence_as_one_rectangle():
    state = OverlayState()
    base = dict(text='Original source', x=20, y=20, w=200, h=60,
                _capture_origin=(0, 0), _fixed_layout=True,
                _source_ink=[22, 22, 196, 56],
                _source_rows=[dict(x=0, y=0, w=200, h=60, font_size=0)])
    def observation(line):
        return [dict(track_id=1, revision=1, line=line)]
    state.apply_objects(observation(base))
    noisy = {**base, 'w': 260, '_source_ink': [22, 22, 256, 56],
             '_source_rows': [dict(x=0, y=0, w=260, h=60, font_size=0)]}
    state.apply_objects(observation(noisy))
    held = state.objects[1]['line']
    assert held['w'] == 200 and held['_source_ink'] == base['_source_ink']
    assert values(fixed_source_rows(held)[0])[:4] == (0, 0, 200, 60)
    state.apply_objects(observation(noisy)); state.apply_objects(observation(noisy))
    assert state.objects[1]['line']['w'] == 260
    assert fixed_source_rows(state.objects[1]['line'])[0].width == 260
