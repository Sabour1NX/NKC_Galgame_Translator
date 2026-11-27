# SPDX-License-Identifier: MIT
"""Capture owned native overlay windows with fixed, synthetic translations.

No API, game input or desktop screenshot. Paragraph dimensions mirror the
reported layout; the output contains only synthetic text on a blank canvas.
An optional older DLL provides a reproducible before/after comparison.
"""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFont
from nkc_galgame_translator.native import NativeCore
from nkc_galgame_translator.languages import label_translation
from nkc_galgame_translator.layout import merge_dialogue_lines
from overlay_smoke import print_window

ROWS = [
    ('The airlock opens at a touch...and', 28, 15, 863, 31),
    ('cycles you smoothly in. Not blown', 28, 50, 838, 27),
    ('after all!', 28, 84, 245, 27),
    ('Garnet laser, memory banks intact --', 28, 154, 911, 30),
    ('she seems A-OK, if a bit spartan.', 28, 189, 843, 30),
    ('What went wrong?', 28, 476, 403, 31),
]
TRANSLATIONS = [
    '\u8f7b\u8f7b\u4e00\u78b0\uff0c\u6c14\u95f8\u5c31\u6253\u5f00\u4e86\uff0c\n\u987a\u7545\u5730\u5c06\u4f60\u9001\u5165\u8231\u5185\u3002\n\u539f\u6765\u5e76\u6ca1\u6709\u70b8\u6bc1\uff01',
    '\u77f3\u69b4\u77f3\u6fc0\u5149\u5668\u3001\u5b58\u50a8\u5e93\u90fd\u5b8c\u597d\u65e0\u635f——\n\u5b83\u770b\u8d77\u6765\u72b6\u6001\u826f\u597d\uff0c\u53ea\u662f\u6709\u4e9b\u7b80\u964b\u3002',
    '\u51fa\u4e86\u4ec0\u4e48\u95ee\u9898\uff1f',
]


def snapshot(core, regions):
    sequence = core.overlay_snapshot()['sequence']
    core.show_overlay(regions)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = core.overlay_snapshot()
        if state['sequence'] > sequence and len(state['regions']) == len(regions):
            return state
        time.sleep(.005)
    raise RuntimeError('Native layout snapshot timeout')


def capture(dll, reflow):
    # The production pipeline owns display normalization; exercise that exact
    # path with a tiny engine-free Pipeline object rather than an imitation.
    from nkc_galgame_translator.pipeline import Pipeline
    rows = [dict(text=t, x=x, y=y, w=w, h=h, source_lang='en',
                 bg=[0, 0, 0], fg=[255, 255, 255]) for t, x, y, w, h in ROWS]
    groups = merge_dialogue_lines(rows)
    assert len(groups) == 3, groups
    regions = []
    # The callback is invoked directly: no capture thread, engine or network.
    from types import SimpleNamespace
    session = object.__new__(Pipeline)
    session.show_source_label = True
    session.show_translation_brackets = True
    session.source_label_mixed_only = False
    session._visible_foreign_languages = {'en'}
    emitted = []
    session.emit = emitted.append
    for index, (group, translation) in enumerate(zip(groups, TRANSLATIONS), 1):
        if reflow:
            session._emit_translation_locked(1, index,
                SimpleNamespace(line=group, revision=1), translation, True)
            region = emitted[-1][2][1]
        else:
            region = {**group, 'text': label_translation(translation, 'en'), 'final': True}
        regions.append({**region, '_track_id': index, '_revision': 1})
    regions.append(dict(x=28, y=560, w=403, h=120, font_size=27,
        text='[\u82f1\u8bed\uff1aSpace Rogue \u661f\u8230\u7684\u8231\u95e8\u5df2\u7ecf\u6253\u5f00\uff0c\u8bf7\u68c0\u67e5\u8bbe\u5907\u5e76\u7ee7\u7eed\u524d\u5f80\u51fa\u53e3\u3002]',
        bg=[0, 0, 0], fg=[255, 255, 255], final=True, _track_id=4, _revision=1))
    picture = Image.new('RGB', (1021, 710), 'black')
    with NativeCore(dll) as core:
        result = snapshot(core, regions)
        for item in result['regions']:
            assert item['fits'], item
            shot = print_window(item['hwnd'], diagnostic_overlay=True)
            x, y, width, height = item['bounds']
            assert width == shot.width and height == shot.height
            picture.paste(shot, (x, y))
            # HWND is process-local and meaningless in a saved report.
            item.pop('hwnd', None)
    return picture, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    directory = ROOT / 'reports'
    directory.mkdir(exist_ok=True)
    report = {'kind': 'Owned native GDI windows; synthetic fixed translations and blank canvas',
              'api_requests': 0, 'real_game_capture': False, 'desktop_capture': False}
    panels = []
    if args.baseline:
        before, evidence = capture(args.baseline.resolve(), False)
        before.save(directory / 'layout-before.png')
        report['before'] = evidence
        panels.append(('0.01.15 / original wrapping', before))
    after, evidence = capture(ROOT / 'native/bin/nkc_galgame_translator_core.dll', True)
    after.save(directory / 'layout-after.png')
    report['after'] = evidence
    panels.append(('0.01.16 / paragraph reflow + mixed-script wrapping', after))
    canvas = Image.new('RGB', (1021 * len(panels), 760), '#f4f1ed')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 23)
    for index, (title, picture) in enumerate(panels):
        draw.text((index * 1021 + 20, 10), title, font=font, fill='#242424')
        canvas.paste(picture, (index * 1021, 50))
    canvas.save(directory / 'layout-comparison.png')
    (directory / 'layout-visual-probe.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'panels': len(panels), 'api_requests': 0}))


if __name__ == '__main__':
    main()
