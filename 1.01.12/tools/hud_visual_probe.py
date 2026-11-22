# SPDX-License-Identifier: MIT
"""Fixed-image OCR and owned-window rendering check; no API or live capture.

Run with a game-only image crop. Saved screenshots are private report artifacts,
never part of the public source/program package. Translations are fixed fixtures.
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
from overlay_smoke import print_window

FIXED = {'STATUS': '\u72b6\u6001', 'QUERY': '\u67e5\u8be2', 'SCAN': '\u626b\u63cf', 'COCKPIT': '\u9a7e\u9a76\u8231'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    source = Image.open(args.image).convert('RGB')
    output = source.copy()
    with OcrCore(mode='auto') as core:
        recognized = core.recognize_image(source, 'en')
        lines = _quality_lines(recognized['lines'], 'en', (0, 0), True)
        regions = []
        for index, line in enumerate(lines, 1):
            if not line.get('_preserve_source') and line['text'] in FIXED:
                regions.append({**line, 'text': FIXED[line['text']], 'final': True,
                                '_track_id': index, '_revision': 1})
        assert len(regions) == 4, 'Expected four readable menu fixtures'
        sequence = core.native.overlay_snapshot()['sequence']
        core.show_overlay(regions)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = core.native.overlay_snapshot()
            if snapshot['sequence'] > sequence and len(snapshot['regions']) == len(regions):
                break
            time.sleep(.005)
        else:
            raise RuntimeError('Native fixture render timeout')
        for region in snapshot['regions']:
            assert region['fits'] and region['paint']['buffered']
            picture = print_window(region['hwnd'], diagnostic_overlay=True)
            output.paste(picture, tuple(region['bounds'][:2]))
            region.pop('hwnd', None)
    folder = ROOT / 'reports'
    folder.mkdir(exist_ok=True)
    output.save(folder / 'hud-overlay-after.png')
    report = {'kind': 'Provided game-only fixed image + owned native window pixels',
              'live_game_capture': False, 'api_requests': 0, 'fixed_translations': True,
              'ocr': recognized, 'prepared_regions': lines, 'render': snapshot}
    (folder / 'hud-visual-probe.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'boxes': len(regions), 'api_requests': 0}))


if __name__ == '__main__':
    main()
