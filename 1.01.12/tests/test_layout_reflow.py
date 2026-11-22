# SPDX-License-Identifier: MIT
"""Display reflow regressions; no API, game assets or credentials required."""
import pytest

from nkc_galgame_translator.layout import merge_dialogue_lines, reflow_translation
from nkc_galgame_translator.pipeline import _quality_lines


def row(text, y=20, w=500, **extra):
    return dict(text=text, x=28, y=y, w=w, h=30, bg=[0, 0, 0],
                fg=[255, 255, 255], source_lang='en', **extra)


@pytest.mark.parametrize(('text', 'expected'), [
    ('\u6c14\u95f8\u8f7b\u89e6\u5373\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002\n\u770b\u6765\u8fd8\u6ca1\u70b8\u6bc1\uff01', '\u6c14\u95f8\u8f7b\u89e6\u5373\u5f00\uff0c\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002\u770b\u6765\u8fd8\u6ca1\u70b8\u6bc1\uff01'),
    ('The airlock opens\nat a touch.', 'The airlock opens at a touch.'),
    ('\u7b2c\u4e00\u6bb5\u3002\n\n\u7b2c\u4e8c\u6bb5\u3002', '\u7b2c\u4e00\u6bb5\u3002\n\n\u7b2c\u4e8c\u6bb5\u3002'),
    ('Narrative.\n- First item\n- Second item', 'Narrative.\n- First item\n- Second item'),
    ('Narrative.\n1. First item\n2. Second item', 'Narrative.\n1. First item\n2. Second item'),
    ('\u9879\u76ee\uff1a\n• \u6c14\u95f8\n• \u98de\u8239', '\u9879\u76ee\uff1a\n• \u6c14\u95f8\n• \u98de\u8239'),
    ('hello\r\nworld', 'hello world'),
    ('\u4f60\u597d \r\n \u4e16\u754c', '\u4f60\u597d\u4e16\u754c'),
    ('\u98de\u8239 PRINCESS BLUE\n\u6b63\u5728\u63a5\u8fd1\u3002', '\u98de\u8239 PRINCESS BLUE\u6b63\u5728\u63a5\u8fd1\u3002'),
    ('alpha  beta\ngamma', 'alpha  beta gamma'),
    ('alpha\n1234 engine', 'alpha 1234 engine'),
    ('alpha\n1.5 engine', 'alpha 1.5 engine'),
    ('한국어\n문장', '한국어 문장'),
    ('\n\n\u4e2d\u6587\n\n\n\u7b2c\u4e8c\u6bb5\n', '\u4e2d\u6587\n\n\u7b2c\u4e8c\u6bb5'),
])
def test_reflow_keeps_semantic_content_paragraphs_and_lists(text, expected):
    assert reflow_translation(text) == expected


@pytest.mark.parametrize('text', [
    '\u6c14\u95f8\u8f7b\u89e6\u5373\u5f00\uff0c\n\u5e73\u7a33\u5730\u5c06\u4f60\u9001\u5165\u3002\n\u770b\u6765\u8fd8\u6ca1\u70b8\u6bc1\uff01',
    'The airlock opens\nat a touch.  Nothing else.',
    'First.\n\nSecond.\n- Item\n+ Another\n* Third',
    'First.\n1. Item\n2) Item\n(3) Item\n[4] Item\n5\u3001 Item',
    'Start\n1234 engine\n1.5 engine\n-end\n*end\n-end.',
    '\u4e2d\u6587\r\nPRINCESS BLUE\r\n\u7ee7\u7eed\u524d\u8fdb\u3002 \n',
    '\u4e2d\u6587\n1', '\u4e2d\u6587\n-', 'alpha ', 'alpha\n\n\n', '',
])
def test_every_stream_chunk_prefix_remains_a_rendered_prefix(text):
    previous = ''
    for length in range(len(text) + 1):
        current = reflow_translation(text[:length], final=False)
        assert current.startswith(previous), (text, length, previous, current)
        previous = current
    assert reflow_translation(text, final=True).startswith(previous)


def test_many_short_rows_reflow_at_maximum_output_size():
    text = 'a\n' * 32767 + 'a'
    assert len(text) == 65535
    expected = 'a ' * 32767 + 'a'
    assert reflow_translation(text) == expected
    assert reflow_translation(text, final=False) == expected


@pytest.mark.parametrize('texts', [
    ('- Find the missing station', '- Return to the captain'),
    ('1. Find the missing station', '2. Return to the captain'),
    ('Captain: Get to the airlock.', 'Pilot: I will be there.'),
    ('Health: 100', 'Attack: 35'),
    ('Item\tQuantity', 'Fuel\t100'),
    ('\u968a\u9577\uff1a\u30a8\u30a2\u30ed\u30c3\u30af\u3078\u5411\u304b\u3048\u3002', '\u5175\u58eb\uff1a\u4e86\u89e3\u3057\u307e\u3057\u305f\u3002'),
])
def test_structured_source_rows_keep_independent_boxes(texts):
    lines = [row(text, y=20 + index * 35) for index, text in enumerate(texts)]
    assert merge_dialogue_lines(lines) == lines


def test_only_newly_joined_narrative_is_marked_for_reflow():
    lines = [row('The airlock opens at a touch...and'), row('cycles you smoothly in.', y=55)]
    merged = merge_dialogue_lines(lines)
    assert merged[0]['_flow_layout'] is True
    assert merged[0]['text'] == 'The airlock opens at a touch...and\ncycles you smoothly in.'
    source = {**row('Hard\nbreak'), 'h': 65}
    assert merge_dialogue_lines([source]) == [source]
    assert merge_dialogue_lines([row('Menu')]) == [row('Menu')]


@pytest.mark.parametrize('merge', [True, False])
def test_provider_cannot_mark_explicit_hard_breaks_as_flow(merge):
    source = row('First\nSecond', _flow_layout=True)
    prepared = _quality_lines([source], 'en', (0, 0), merge)
    assert '_flow_layout' not in prepared[0]
    assert prepared[0]['text'] == 'First\nSecond'


def test_latest_airlock_scene_keeps_three_boxes_and_two_narrative_paragraphs():
    # Text and bounds only, transcribed from the user's screenshot. No artwork.
    values = [
        ('The airlock opens at a touch...and', 15, 863, 31),
        ('cycles you smoothly in. Not blown', 50, 837, 31),
        ('after all!', 84, 243, 27),
        ('Garnet laser, memory banks intact --', 154, 911, 30),
        ('she seems A-OK, if a bit spartan.', 188, 831, 31),
        ('What went wrong?', 476, 403, 31),
    ]
    source = [{**row(text, y, width), 'h': height} for text, y, width, height in values]
    boxes = merge_dialogue_lines(source)
    assert [(item['x'], item['y'], item['w'], item['h']) for item in boxes] == [
        (28, 15, 863, 96), (28, 154, 911, 65), (28, 476, 403, 31)]
    assert [bool(item.get('_flow_layout')) for item in boxes] == [True, True, False]
    assert '\n'.join(item['text'] for item in boxes) == '\n'.join(item['text'] for item in source)
