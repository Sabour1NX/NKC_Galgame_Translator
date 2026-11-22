# SPDX-License-Identifier: MIT
"""Line geometry from the user-provided Space Rogue pixel-font screen.

This is a text/geometry fixture, not bundled game artwork or an OCR accuracy
claim. Bounds follow the observed English OCR rows; text is the visible source.
"""
from copy import deepcopy

import pytest

from nkc_galgame_translator.layout import merge_dialogue_lines


LEFT = [
    ("On a routine", 29, 92, 300, 27),
    ("trading mission", 32, 127, 374, 30),
    ("in the backwater", 32, 161, 400, 27),
    ("Karonus system", 29, 196, 351, 31),
    ("your merchant", 29, 230, 323, 31),
    ("ship, the", 29, 265, 224, 31),
    ("PRINCESS BLUE", 29, 300, 326, 26),
    ("picks up a", 29, 334, 249, 31),
    ("Small Craft", 29, 369, 272, 27),
    ("Distress Beacon.", 29, 403, 396, 27),
]
BOTTOM = [
    ('"No life readings," says Captain', 26, 572, 815, 31),
    ('Dolfree. "Looks like a derelict.', 29, 607, 805, 27),
    ("You're on EVA duty, Private, so scope", 29, 641, 940, 31),
    ("it out. Make it quick! We're behind", 32, 676, 886, 31),
    ('schedule."', 29, 710, 249, 27),
]


def scene(rows, offset=(0, 0)):
    return [{"text": text, "x": x+offset[0], "y": y+offset[1], "w": w, "h": h,
             "bg": [0, 0, 0], "fg": [255, 255, 255], "source_lang": "en",
             "_capture_origin": offset}
            for text, x, y, w, h in rows]


@pytest.mark.parametrize("offset", [(0, 0), (114, 42), (-1300, 28)])
def test_pixel_paragraphs_are_two_complete_objects_with_hard_breaks(offset):
    lines = scene(LEFT + BOTTOM, offset)
    original = deepcopy(lines)
    result = merge_dialogue_lines(list(reversed(lines)))
    assert len(result) == 2
    assert [r["text"] for r in result] == ["\n".join(v[0] for v in rows) for rows in (LEFT, BOTTOM)]
    assert [(r["x"]-offset[0], r["y"]-offset[1], r["w"], r["h"]) for r in result] == [
        (29, 92, 403, 338), (26, 572, 943, 165)]
    assert [r["font_size"] for r in result] == [24, 28]
    assert all(r["_capture_origin"] == offset for r in result)
    assert lines == original


def test_pixel_paragraph_keeps_unknown_ocr_spelling_as_data():
    lines = scene(LEFT)
    lines[1]["text"] = "trading w#ission"
    lines[4]["text"] = "your #erchant"
    result = merge_dialogue_lines(lines)
    assert len(result) == 1
    assert "trading w#ission\n" in result[0]["text"]
    assert "your #erchant\n" in result[0]["text"]


def test_right_picture_text_is_never_absorbed_or_covered_by_left_paragraph():
    # A same-style OCR false positive in the picture may interrupt reading
    # order, but must never be included in the paragraph union or context.
    lines = scene(LEFT + BOTTOM)
    lines.append(scene([("artwork noise", 600, 249, 180, 27)])[0])
    result = merge_dialogue_lines(lines)
    picture = next(r for r in result if r["text"] == "artwork noise")
    assert picture["x"] == 600 and picture["w"] == 180
    for region in result:
        if region is not picture and region["y"] < 500:
            assert region["x"]+region["w"] <= 432
            assert "artwork" not in region["text"]
    assert result[-1]["text"] == "\n".join(v[0] for v in BOTTOM)


def test_same_left_edge_does_not_bridge_large_paragraph_gap():
    result = merge_dialogue_lines(scene(LEFT + BOTTOM))
    assert result[0]["y"]+result[0]["h"] == 430
    assert result[1]["y"] == 572


def test_adjacent_pixel_font_different_language_is_a_separate_object():
    lines = scene(LEFT)
    lines[4]["source_lang"] = "ja"
    result = merge_dialogue_lines(lines)
    assert len(result) == 3
    assert result[1]["text"] == LEFT[4][0]
    assert result[1]["source_lang"] == "ja"


def test_horizontal_button_grid_does_not_become_paragraphs():
    buttons = [(text, x, y, width, 28) for text, x, y, width in [
        ("Load Game", 30, 100, 145), ("New Game", 340, 100, 130),
        ("Settings", 30, 137, 130), ("Exit", 340, 137, 64),
    ]]
    lines = scene(buttons)
    assert merge_dialogue_lines(lines) == lines


NATIVE_LEFT_BOUNDS = [
    (27, 90, 305, 32), (30, 125, 379, 35), (30, 159, 405, 32),
    (27, 194, 356, 36), (27, 228, 328, 36), (27, 263, 229, 36),
    (27, 298, 331, 31), (27, 332, 254, 36), (27, 367, 277, 32),
    (27, 401, 401, 32),
]
NATIVE_BOTTOM = [
    ('"No life readings,"', 24, 570, 455, 36),
    ('says Captain', 538, 570, 306, 36),
    ('Dalfree. "Looks like a derelict.', 27, 605, 810, 32),
    ("You're on EVA duty, Private, so scope", 27, 639, 945, 36),
    ("it out. Make it quick! We're behind", 30, 674, 891, 36),
    ('schedule."', 27, 708, 254, 32),
]


def test_actual_native_sixteen_anchors_become_two_complete_paragraphs():
    native_left = [(row[0], *bounds) for row, bounds in zip(LEFT, NATIVE_LEFT_BOUNDS)]
    lines = scene(native_left + NATIVE_BOTTOM)
    original = deepcopy(lines)
    result = merge_dialogue_lines(lines)
    assert len(result) == 2
    assert result[0]['text'] == '\n'.join(row[0] for row in LEFT)
    assert result[1]['text'].splitlines() == [
        '"No life readings," says Captain', *[row[0] for row in NATIVE_BOTTOM[2:]]]
    assert [(line['x'], line['y'], line['w'], line['h']) for line in result] == [
        (27, 90, 408, 343), (24, 570, 948, 170)]
    assert lines == original


def test_long_same_baseline_fragments_without_support_do_not_merge():
    lines = scene(NATIVE_BOTTOM[:2])
    assert merge_dialogue_lines(lines) == lines


@pytest.mark.parametrize('change', ['title', 'gap', 'baseline', 'color', 'language', 'short_support'])
def test_horizontal_join_rejects_button_like_or_separate_column_evidence(change):
    lines = scene(NATIVE_BOTTOM[:3])
    if change == 'title':
        lines[1]['text'] = 'Select Character'
    elif change == 'gap':
        lines[1]['x'] += 100
    elif change == 'baseline':
        lines[1]['y'] += 8
    elif change == 'color':
        lines[1]['fg'] = [100, 255, 255]
    elif change == 'language':
        lines[1]['source_lang'] = 'ja'
    elif change == 'short_support':
        lines[2]['w'] = 300
    result = merge_dialogue_lines(lines)
    assert any(line['text'] == lines[1]['text'] for line in result)
    assert not any('readings," says Captain' in line['text'] for line in result)


def test_long_title_case_button_grid_never_joins_even_with_full_width_help():
    lines = scene([
        ('Create New Campaign', 24, 570, 455, 36),
        ('Load Existing Campaign', 538, 570, 306, 36),
        ('Choose an option to continue playing.', 27, 605, 810, 32),
    ])
    assert merge_dialogue_lines(lines) == lines
