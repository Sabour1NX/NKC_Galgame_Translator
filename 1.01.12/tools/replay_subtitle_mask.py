# SPDX-License-Identifier: MIT
"""Measure residual mint source ink inside one OCR line on a Windows desktop."""
import argparse
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from nkc_galgame_translator.aoi_dialogue import repair_ocr_rows
from nkc_galgame_translator.native import NativeCore
from test_native_aero import print_window, region, render, source_window


def is_mint(pixel):
    red, green, blue = pixel
    return green >= 150 and green - red >= 52 and green - blue >= 12 and blue - red >= 18


def replay(image, box, source_text):
    left, top, width, height = box
    if not (0 <= left < left + width <= image.width and 0 <= top < top + height <= image.height):
        raise ValueError("The text box must be inside the screenshot.")
    row = dict(x=left, y=top, w=width, h=height, text=source_text, fg=[255]*3, bg=[80, 118, 150])
    row, = repair_ocr_rows(image, [row])
    rx, ry = region()["x"] + 20, region()["y"] + 20
    x, y = row["x"], row["y"]
    ix, iy, iw, ih = row["_source_ink"]
    item = region() | row | dict(x=rx+x, y=ry+y, text=" ", final=True, _fixed_layout=True,
                                _source_ink=[rx+ix, ry+iy, iw, ih])
    with NativeCore() as core, source_window(image, rx, ry):
        core.capture_bgra(rx, ry, *image.size)
        overlay = render(core, [item])[0]
        if overlay["background_suppressed"]:
            raise ValueError(overlay["background_reason"])
        output = print_window(overlay["hwnd"], diagnostic_overlay=True).convert("RGB")
        points = [(u, v) for v in range(row["h"]) for u in range(row["w"])
                  if is_mint(image.getpixel((u+x, v+y)))]
        if not points:
            raise ValueError("No mint source ink found in the text box.")
        return {"source_pixels": len(points), "remaining_pixels": sum(is_mint(output.getpixel(p)) for p in points)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--box", nargs=4, type=int, required=True, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--text", required=True, help="OCR text from the selected line")
    args = parser.parse_args()
    with Image.open(args.image) as source:
        result = replay(source.convert("RGB"), args.box, args.text)
    print(json.dumps(result))
    raise SystemExit(1 if result["remaining_pixels"] else 0)
