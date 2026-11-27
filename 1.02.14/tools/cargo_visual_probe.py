# SPDX-License-Identifier: MIT
"""Verify fixed cell placement on a provided game-only image, without API/input.

Translations are synthetic fixtures. The report and image stay outside public
packages; no claims about live game/API translation or complete OCR accuracy.
"""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.pipeline import _quality_lines
from overlay_smoke import print_window, window_mask

FIXED = {'Cargo': '\u8d27\u7269', 'Cost': '\u4ef7\u683c', 'forged CRs': '\u4f2a\u9020\u4fe1\u7528\u70b9',
         '1GB RRHS': '1GB \u5185\u5b58', 'dilithiun': '\u53cc\u9502\u6676\u4f53',
         'hubrid grain': '\u6742\u4ea4\u8c37\u7269', 'hybrid grain': '\u6742\u4ea4\u8c37\u7269',
         'antibiotics': '\u6297\u751f\u7d20', 'DONE': '\u5b8c\u6210'}


def render(core, regions):
    sequence = core.native.overlay_snapshot()['sequence']
    core.show_overlay(regions)
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        state = core.native.overlay_snapshot()
        if state['sequence'] > sequence and len(state['regions']) == len(regions):
            return state
        time.sleep(.005)
    raise RuntimeError('Fixed overlay render timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    source = Image.open(args.image).convert('RGB')
    output = source.copy()
    with OcrCore(mode='auto') as core:
        ocr = core.recognize_image(source, 'en')
        prepared = _quality_lines(ocr['lines'], 'en', (0, 0), True)
        ignored = [row for row in prepared if row.get('_preserve_source')]
        assert {'BE', 'Hi'} <= {row['text'] for row in ignored}
        regions = [{**row, 'text': FIXED[row['text']], 'final': True,
                    '_track_id': index+1, '_revision': 1}
                   for index, row in enumerate(prepared)
                   if not row.get('_preserve_source') and row['text'] in FIXED]
        assert len(regions) == 8
        state = render(core, regions)
        for region, actual in zip(regions, state['regions']):
            assert actual['fits'] and actual['fixed_layout'] and actual['source_rows'] == 1
            assert actual['bounds'] == [region[k] for k in ('x', 'y', 'w', 'h')]
            assert len(actual['lines']) == 1
            picture = print_window(actual['hwnd'], diagnostic_overlay=True)
            mask, _ = window_mask(actual['hwnd'])
            output.paste(picture, tuple(actual['bounds'][:2]), mask)
            actual.pop('hwnd', None)
        # Check every price/barrier pixel, including OCR-garbled values, remains
        # identical to the user's source image in the composite.
        for row in ignored:
            box = (row['x'], row['y'], row['x']+row['w'], row['y']+row['h'])
            assert output.crop(box).tobytes() == source.crop(box).tobytes()
        long_case = {**regions[2], '_revision': 2, 'text': '\u8fd9\u662f\u4e00\u6bb5\u6bd4\u539f\u540d\u79f0\u66f4\u957f\u7684\u8bd1\u6587\uff0c\u5fc5\u987b\u5728\u540c\u4e00\u884c\u7f29\u5c0f\u5b57\u53f7\u3002'}
        longer = render(core, [long_case])['regions'][0]
        assert longer['fits'] and len(longer['lines']) == 1
        assert longer['font_px'] < state['regions'][2]['font_px']
        longer.pop('hwnd', None)
    directory = ROOT/'reports'
    output.save(directory/'cargo-fixed-after.png')
    report = dict(kind='Fixed supplied game image + actual native overlay pixels',
        api_requests=0, live_game_capture=False, fixed_translations=True,
        prepared=prepared, render=state, price_pixels_identical=True,
        long_translation_shrinks_in_same_row=longer)
    (directory/'cargo-fixed-probe.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'cells': len(regions), 'api_requests': 0}))


if __name__ == '__main__':
    main()
