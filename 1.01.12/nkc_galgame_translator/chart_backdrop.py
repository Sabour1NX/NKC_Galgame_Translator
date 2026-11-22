# SPDX-License-Identifier: MIT
"""Static artwork behind the resource chart."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .themes import mix


def load_picture(path):
    path = Path(path)
    if not path.is_absolute() or path.drive.startswith("\\\\"):
        raise ValueError("Choose a local image.")
    with Image.open(path, formats=("JPEG", "PNG", "BMP")) as image:
        if image.width * image.height > 24_000_000:
            raise ValueError("Image is too large.")
        image.thumbnail((2048, 1024), Image.Resampling.LANCZOS)
        return ImageOps.exif_transpose(image).convert("RGBA")


def backdrop(size, theme, panel, custom, icon):
    width, height = size
    if custom is not None:
        photo = ImageOps.fit(custom, size, method=Image.Resampling.LANCZOS)
        base = Image.new("RGB", size, panel)
        base.paste(photo, mask=photo.getchannel("A"))
        return Image.blend(base, Image.new("RGB", size, panel), .48)
    if theme == "nishokuchou":
        base = Image.new("RGB", size, panel)
        with Image.open(icon) as original:
            mark = original.convert("RGBA").resize((height - 8, height - 8), Image.Resampling.LANCZOS)
        base.paste(mark, (int(width * .64), 4), mark)
        return base
    if theme != "neon":
        return None
    gradient = Image.new("RGB", (256, 1))
    brush = ImageDraw.Draw(gradient)
    for x in range(256):
        fraction = x / 255
        amount = max(0, 1 - abs(fraction - .7) / .68)
        brush.point((x, 0), fill=mix("#171029", "#513567", amount))
    base = gradient.resize(size, Image.Resampling.BILINEAR)
    brush = ImageDraw.Draw(base)
    radius = height * .48
    center_x, center_y = width * .68, height * .52
    for y in range(height):
        offset = (y - center_y) / radius
        if abs(offset) >= 1:
            continue
        if offset > .06 and int((offset - .06) * 27) % 5 < 2:
            continue
        reach = radius * (1 - offset * offset) ** .5
        t = (1 + offset) / 2
        color = (mix("#FFE0A8", "#FFA1BD", t / .41) if t < .41
                 else mix("#FFA1BD", "#E850CB", (t - .41) / .59))
        brush.line((center_x - reach, y, center_x + reach, y), fill=mix("#4E3673", color, .74))
    return base
