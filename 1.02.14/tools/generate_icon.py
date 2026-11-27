# SPDX-License-Identifier: MIT
"""Generate the code-drawn red/white Taiji assets, without network or fonts."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RED = '#B6332D'
WHITE = '#FFFEFC'
SIZES = (16, 24, 32, 48, 64, 128, 256)

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100" role="img" aria-label="\u4e8c\u8272\u8776\u7ea2\u767d\u592a\u6781\u56fe\u6807">
  <!-- SPDX-License-Identifier: MIT -->
  <circle cx="50" cy="50" r="47" fill="#FFFEFC"/>
  <path d="M50 3 A47 47 0 0 0 50 97 A23.5 23.5 0 0 1 50 50 A23.5 23.5 0 0 0 50 3Z" fill="#B6332D"/>
  <circle cx="50" cy="26.5" r="6.5" fill="#FFFEFC"/>
  <circle cx="50" cy="73.5" r="6.5" fill="#B6332D"/>
  <circle cx="50" cy="50" r="47" fill="none" stroke="#B6332D" stroke-width="1.5"/>
</svg>
'''


def render_icon(size=256):
    """Same red-left Taiji geometry as the application header, supersampled."""
    scale = 2048 / 100
    image = Image.new('RGBA', (2048, 2048), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(values):
        return tuple(round(value * scale) for value in values)

    draw.ellipse(box((3, 3, 97, 97)), fill=WHITE)
    draw.pieslice(box((3, 3, 97, 97)), start=90, end=270, fill=RED)
    draw.ellipse(box((26.5, 3, 73.5, 50)), fill=RED)
    draw.ellipse(box((26.5, 50, 73.5, 97)), fill=WHITE)
    draw.ellipse(box((43.5, 20, 56.5, 33)), fill=WHITE)
    draw.ellipse(box((43.5, 67, 56.5, 80)), fill=RED)
    draw.ellipse(box((3, 3, 97, 97)), outline=RED, width=round(1.5 * scale))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    image = render_icon()
    image.save(assets / 'taiji.png')
    image.save(assets / 'taiji.ico', sizes=[(size, size) for size in SIZES])
    (assets / 'taiji.svg').write_text(SVG, encoding='utf-8')
    print('Generated assets/taiji.svg, taiji.png and seven-size taiji.ico')


if __name__ == '__main__':
    main()
