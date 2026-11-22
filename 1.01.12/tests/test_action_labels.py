# SPDX-License-Identifier: MIT
from PIL import Image, ImageDraw

from nkc_galgame_translator.ocr import changed_source_indices
from nkc_galgame_translator.ocr_regions import action_label_layout, retain_action_labels
from test_pipeline import make_pipeline, start, wait_until, finals
from test_native_overlay import core, render


def original():
    image = Image.new('RGB', (220, 90), (244, 224, 246))
    ink = (100, 36, 15, 14)
    line = dict(text='OK', x=98, y=34, w=19, h=18, fg=[80, 24, 206],
                bg=[244, 224, 246], _source_ink=ink, confidence=98)
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 36, 106, 49), outline=tuple(line['fg']), width=2)
    draw.line([(109, 37), (109, 48)], fill=tuple(line['fg']), width=2)
    draw.line([(109, 43), (113, 37)], fill=tuple(line['fg']), width=2)
    draw.line([(109, 43), (113, 48)], fill=tuple(line['fg']), width=2)
    return image, line


def test_focus_outline_keeps_translation_and_glyph_change_revises(make_pipeline):
    before, original_label = original()
    label, = action_label_layout(before, [original_label])
    assert label['_center_label']
    with before.copy() as focused:
        draw = ImageDraw.Draw(focused)
        for x in range(20, 201, 4):
            draw.point((x, 24), fill='#8277ff')
            draw.point((x, 62), fill='#8277ff')
        assert not changed_source_indices(before, focused, [label])
        ocr_glitch = {**original_label, 'text': '0K'}
        stable = retain_action_labels(before, focused, [label], [ocr_glitch])
        assert stable == [label]
        assert retain_action_labels(before, focused, [label], []) == [label]
        pipeline, fake, engine, events, region = make_pipeline([label])
        start(pipeline, region)
        wait_until(lambda: len(finals(events)) == 1)
        fake.set_scene(stable)
        wait_until(lambda: sum(event[0] == 'objects' for event in events.snapshot()) >= 2)
        assert len(engine.scopes) == 1
        draw.rectangle((100, 36, 114, 49), fill='black')
        assert changed_source_indices(before, focused, [label]) == {0}
        replacement = {**original_label, 'text': 'NO'}
        assert retain_action_labels(before, focused, [label], [replacement]) == [replacement]
        fake.set_scene([replacement])
        wait_until(lambda: len(finals(events)) == 2)
    before.close()


def test_centered_button_fits_without_stretching_or_covering_focus_ring(core):
    before, original_label = original()
    item, = action_label_layout(before, [original_label])
    before.close()
    item.update(_fixed_layout=True, text='\u786e\u5b9a', final=True, _track_id=1, _revision=1)
    old = {**original_label, **{k:item[k] for k in ('_fixed_layout', 'text')},
           '_track_id':2, '_revision':1}
    previous = render(core, [old])[0]
    first = render(core, [item])[0]
    other = {**item, 'x': item['x']+120, 'text':'\u53d6\u6d88',
             '_source_ink': [original_label['_source_ink'][0]+120,36,15,14], '_track_id':3}
    pair = render(core, [item, other])
    assert first['fits'] and first['font_px'] > previous['font_px']
    assert pair[0]['font_px'] == pair[1]['font_px']
    for result in pair:
        line, = result['lines']
        assert abs(2*line['x'] + line['width'] - item['w']) <= 1
        assert line['width'] < item['w']-4
    assert item['y'] > 24 and item['y']+item['h'] < 62


def test_label_padding_stops_at_other_ink_and_selection_edge():
    before, label = original()
    try:
        assert action_label_layout(before, [{**label, '_selection_id':0}], [(95,30,25,30)])[0]['w'] == 19
        before.putpixel((90, 40), (90, 20, 220))
        assert action_label_layout(before, [label])[0]['w'] == 19
    finally:
        before.close()
