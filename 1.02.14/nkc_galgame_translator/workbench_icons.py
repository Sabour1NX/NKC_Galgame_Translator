# SPDX-License-Identifier: MIT
"""Tint the shared 24-unit navigation and scope glyphs for the current palette."""
from pathlib import Path

from PIL import Image, ImageOps, ImageTk


def load_icons(root, ink, primary, secondary, disabled):
    with Image.open(Path(__file__).with_name('resources') / 'workbench.png') as source:
        atlas = source.convert('RGBA')
    size = max(18, round(root.winfo_fpixels('16p')))
    icons = {}
    for index in range(8):
        tile = atlas.crop((96 * index, 0, 96 * (index + 1), 96))
        for state, colors in [('idle', (ink, ink)), ('active', (primary, secondary)),
                              ('disabled', (disabled, disabled))]:
            colored = ImageOps.colorize(tile.getchannel('R'), *colors)
            colored.putalpha(tile.getchannel('A'))
            icons[index, state] = ImageTk.PhotoImage(
                colored.resize((size, size), Image.Resampling.LANCZOS), master=root)
    return icons
