# SPDX-License-Identifier: MIT
"""Table/menu geometry regressions; no game artwork or API calls."""
from copy import deepcopy

import pytest

from nkc_galgame_translator.layout import merge_dialogue_lines, _join_horizontal_fragments, mark_table_values


def row(text, x=48, y=102, w=280, h=32, **extra):
    return dict(text=text, x=x, y=y, w=w, h=h, bg=[0, 0, 0],
                fg=[245, 245, 245], source_lang='en', **extra)


def source_geometry(lines):
    return [(line['text'], line['x'], line['y'], line['w'], line['h']) for line in lines]


@pytest.mark.parametrize('selected', [None, 3])
def test_inventory_without_price_anchors_keeps_long_single_word_rows_separate(selected):
    # The Windows OCR sample missed some prices and one inventory row. Long
    # words such as antibiotics must not turn the remaining list into prose.
    lines = [row(text, y=y, w=width) for text, y, width in [
        ('forged ERs', 102, 251), ('dilithiun', 171, 229),
        ('h brid rain', 205, 306), ('souvenirs', 240, 229),
        ('antibiotics', 274, 280), ('DONE', 309, 101)]]
    if selected is not None:
        lines[selected].update(bg=[245, 245, 245], fg=[0, 0, 0])
    before = deepcopy(lines)
    result = merge_dialogue_lines(lines)
    assert result == before
    assert lines == before


@pytest.mark.parametrize('offset', [(0, 0), (140, 70), (-1600, 30)])
def test_locally_split_cargo_cells_never_recombine_or_cover_price_column(offset):
    dx, dy = offset
    texts = [('forged CRs', '488'), ('1GB RAMs', '66'), ('dilithium', '85'),
             ('hybrid grain', '25'), ('souvenirs', '18'), ('antibiotics', '81')]
    lines = []
    for index, (label, cost) in enumerate(texts):
        top = 102 + index*35
        lines += [row(label, x=48+dx, y=top+dy, w=306, _layout_cell=True),
                  row(cost, x=485+dx, y=top+dy, w=73, _layout_cell=True,
                      _preserve_source=True)]
    original = deepcopy(lines)
    result = merge_dialogue_lines(list(reversed(lines)))
    assert source_geometry(result) == source_geometry(original)
    assert all('_flow_layout' not in line and '_source_rows' not in line for line in result)
    assert lines == original


def test_one_numeric_partner_protects_compact_multiword_label_column():
    labels = [row(text, y=100+i*35, w=330) for i, text in enumerate([
        'Heavy armor', 'Light armor', 'Crystal shield', 'Plasma shield'])]
    # One successfully recognized price is sufficient when the remaining
    # aligned column already consists of at least three compact lexical rows.
    cost = row('85', x=500, y=170, w=49)
    result = merge_dialogue_lines([*labels, cost])
    assert len(result) == 5
    assert all('\n' not in line['text'] for line in result)


def test_unknown_single_word_item_names_do_not_require_a_game_dictionary():
    lines = [row(text, y=100+i*35, w=340) for i, text in enumerate([
        'Xenothorium', 'Velorian crystals', 'Kryostone', 'Helion alloy'])]
    assert merge_dialogue_lines(lines) == lines


def test_narrow_prose_with_grammatical_continuations_still_groups():
    lines = [row(text, y=100+i*35, w=350) for i, text in enumerate([
        'The silence', 'fell', 'over us', 'again'])]
    result = merge_dialogue_lines(lines)
    assert len(result) == 1
    assert result[0]['text'] == '\n'.join(line['text'] for line in lines)
    assert len(result[0]['_source_rows']) == len(lines)


def test_sentence_punctuation_prevents_short_dialogue_being_labeled_as_a_list():
    lines = [row(text, y=100+i*35, w=350) for i, text in enumerate([
        'Silence.', 'Later.', 'Someone arrived.'])]
    assert len(merge_dialogue_lines(lines)) == 1


def test_small_ambiguous_pair_does_not_claim_whole_list_evidence():
    assert len(merge_dialogue_lines([row('Strange object'), row('Gone', y=137)])) == 1


def test_paragraph_preserves_each_source_row_and_contained_ink_coordinates():
    lines = [row('This is the beginning of a long narrative.', x=-500, y=80,
                 w=450, h=32, _source_ink=[-498, 82, 445, 27]),
             row('It continues over a second physical row.', x=-498, y=116,
                 w=430, h=31, font_size=24, _source_ink=[-496, 118, 425, 26])]
    original = deepcopy(lines)
    result = merge_dialogue_lines(lines)
    assert len(result) == 1
    assert result[0]['_source_rows'] == [
        dict(x=0, y=0, w=450, h=32, font_size=0, ink_bounds=[2, 2, 445, 27]),
        dict(x=2, y=36, w=430, h=31, font_size=24, ink_bounds=[4, 38, 425, 26]),
    ]
    assert lines == original


@pytest.mark.parametrize('ink', [[0, 0, 100, 30], [49, 103, 400, 31],
    [49, 103, -2, 20], [float('nan'), 103, 20, 20], [49, 103, 20], 'bad'])
def test_invalid_source_ink_never_enlarges_or_invents_a_source_row(ink):
    result = merge_dialogue_lines([
        row('This is a prose row.', _source_ink=ink),
        row('This is another prose row.', y=137)])
    assert len(result) == 1
    assert 'ink_bounds' not in result[0]['_source_rows'][0]
    assert result[0]['_source_rows'][0] == dict(x=0, y=0, w=280, h=32, font_size=0)


def test_split_cell_marker_blocks_horizontal_narrative_repair():
    left = row('A substantial narrative fragment', x=20, y=20, w=250, h=24, _layout_cell=True)
    right = row('continues with enough words', x=300, y=20, w=250, h=24, _layout_cell=True)
    support = row('This full width support is still one physical row.', x=20, y=50, w=530, h=24)
    assert _join_horizontal_fragments([left, right, support]) == [left, right, support]


def test_horizontal_repair_unions_both_actual_ink_rectangles():
    left = row('A substantial narrative fragment', x=20, y=20, w=250, h=24,
               _source_ink=[22, 22, 245, 19])
    right = row('continues with enough words', x=300, y=20, w=250, h=24,
                _source_ink=[302, 22, 245, 19])
    support = row('This full width support is still one physical row.', x=20, y=50, w=530, h=24)
    result = _join_horizontal_fragments([left, right, support])
    assert len(result) == 2
    assert result[0]['_source_ink'] == [22, 22, 525, 19]


def price_table(values=('188', 'BE', 'o5', 'Hi')):
    result = [row('Cargo', y=33, w=127), row('Cost', x=458, y=33, w=97)]
    for index, (text, label) in enumerate(zip(values, (
            'forged CRs', '1GB RAMs', 'hybrid grain', 'antibiotics'))):
        width = 24*len(text)
        result += [row(label, y=102+index*35, w=280),
                   row(text, x=558-width, y=102+index*35, w=width)]
    return result


def test_numeric_column_protects_ocr_garbled_values_without_altering_cells():
    lines = price_table()
    before = deepcopy(lines)
    result = mark_table_values(lines)
    assert [line['text'] for line in result if line.get('_preserve_source')] == ['188', 'BE', 'o5', 'Hi']
    assert all(line['_ocr_rejection_reason'] == 'numeric_table_cell'
               for line in result if line.get('_preserve_source'))
    assert source_geometry(result) == source_geometry(lines)
    assert lines == before
    assert all(new is not old for new, old in zip(result, lines))
    assert not result[1].get('_preserve_source')  # Cost remains translatable.


@pytest.mark.parametrize('header', ['Cost', 'Sell', 'Age', 'Gold'])
def test_confusable_word_headers_do_not_become_numeric_values(header):
    lines = price_table()
    lines[1].update(text=header, y=68, x=558-24*len(header), w=24*len(header))
    lines[0]['y'] = 68
    assert not mark_table_values(lines)[1].get('_preserve_source')


@pytest.mark.parametrize('values', [('BE', 'Hi', 'as', 'Go'), ('188', 'BE', 'Hi', 'Go')])
def test_short_word_column_requires_two_digit_bearing_values(values):
    lines = price_table(values)
    assert mark_table_values(lines) == lines


def test_two_numeric_pairs_do_not_establish_a_whole_table_column():
    lines = price_table(('188', '85'))
    assert mark_table_values(lines) == lines


@pytest.mark.parametrize('change', ['left_alignment', 'right_alignment', 'baseline', 'distant', 'gap', 'wide'])
def test_numeric_evidence_requires_matching_row_and_column_geometry(change):
    lines = price_table(('188', 'BE', 'o5'))
    target = lines[-1]
    if change == 'left_alignment':
        lines[-2]['x'] += 24
    elif change == 'right_alignment':
        target['x'] += 24
    elif change == 'baseline':
        target['y'] += 24
    elif change == 'distant':
        target['y'] += 500
        lines[-2]['y'] += 500
    elif change == 'gap':
        target['x'] = lines[-2]['x']+lines[-2]['w']+20
    else:
        target['w'] = 200
    assert not any(line.get('_preserve_source') for line in mark_table_values(lines))


def test_existing_preservation_reason_and_input_order_remain_intact():
    lines = price_table()
    lines[3].update(_preserve_source=True, _ocr_rejection_reason='nonlinguistic')
    lines.reverse()
    result = mark_table_values(lines)
    assert source_geometry(result) == source_geometry(lines)
    original_price = next(line for line in result if line['text'] == '188')
    assert original_price['_ocr_rejection_reason'] == 'nonlinguistic'
    assert sum(bool(line.get('_preserve_source')) for line in result) == 4


def test_provider_table_flags_cannot_substitute_for_numeric_evidence():
    lines = price_table(('BE', 'Hi', 'as', 'Go'))
    for line in lines:
        line['_layout_cell'] = True
        line['_numeric_column'] = True
    assert mark_table_values(lines) == lines


def test_numeric_evidence_survives_vision_wait_without_publishing_new_label_text():
    from nkc_galgame_translator.vision_core import _local_anchors
    from nkc_galgame_translator.pipeline import _quality_lines
    local, barriers = _local_anchors({'lines': price_table()}, 'en')
    assert local['lines']
    assert {'BE', 'Hi'} <= {line['text'] for line in barriers}
    # An initial Vision wait publishes barriers while eligible text is still
    # pending. The missing label pairs must not make bad prices translatable.
    ready = _quality_lines(deepcopy(barriers), 'en', (0, 0), True)
    assert all(line['_preserve_source'] for line in ready)
    assert {line['text'] for line in ready} == {'188', 'BE', 'o5', 'Hi'}


def test_json_provider_cannot_forge_local_numeric_evidence():
    import json
    from nkc_galgame_translator.pipeline import _quality_lines
    evidence = next(line for line in mark_table_values(price_table()) if line['text'] == 'BE')
    # Serialization is allowed for diagnostics, but provenance cannot be
    # asserted by an external JSON/provider string on the return path.
    untrusted = json.loads(json.dumps(evidence))
    ready = _quality_lines([untrusted], 'en', (0, 0), True)
    assert not ready[0].get('_preserve_source')
