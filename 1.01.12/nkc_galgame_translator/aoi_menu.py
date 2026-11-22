# SPDX-License-Identifier: MIT
"""Read the five title actions from their neutral glyphs on a colored control."""
from PIL import Image, ImageStat

# Compact occupancy signatures of the Japanese labels at 32 by 12 cells.
# The position proposes a candidate. Only a matching glyph can produce a row.
_LABELS = (
    ('\u306f\u3058\u3081\u304b\u3089', '\u5f00\u59cb\u6e38\u620f', '\u958b\u59cb\u904a\u6232', '8030400e91320402b903c680b903cf809102a5909106a59f9105a559b1152151f9152901d9276901f0e2cb0630c08204'),
    ('\u3064\u3065\u304d\u304b\u3089', '\u7ee7\u7eed\u6e38\u620f', '\u7e7c\u7e8c\u904a\u6232', '0010800e00108002f9f3e680c9908f800413e5900410455f0411c5590c13e551083201013862090170e30b060001c204'),
    ('\u30ae\u30e3\u30e9\u30ea\u30fc', '\u753b\u5eca', '\u756b\u5eca', '0c0000002003c08038000080f80000802003c08020f0009f38d04080f860408020404100204081000041830000410200'),
    ('\u30aa\u30d7\u30b7\u30e7\u30f3', '\u9009\u9879', '\u9078\u9805', '101000001002001011f10018fc10000910122701300220013020400150204702502081069041800410c3071811800000'),
    ('\u3084\u3081\u308b', '\u9000\u51fa', '\u9000\u51fa', '0400407c2604400c2307e0083f87f018f0c6d03030ca987e30cb88c317890981100b1871100e304b1004606e1800c03c'),
)
TRANSLATIONS = {source: (zh, tw) for source, zh, tw, _ in _LABELS}
_SIGNATURES = tuple(int(entry[3], 16) for entry in _LABELS)


def read_button(image, rect, index):
    x, y, w, h = rect
    if w < 64 or h < 12 or x < 0 or y < 0 or x+w > image.width or y+h > image.height:
        return None
    left = image.getpixel((x+w//80, y+h//2))
    right = image.getpixel((x+w-1-w//80, y+h//2))
    if min(left[2]-left[0], right[2]-right[0]) < 20 or max(abs(a-b) for a,b in zip(left,right)) > 25:
        return None
    patch = image.crop((x,y,x+w,y+h))
    red = patch.getchannel('R')
    peak = red.getextrema()[1]
    if peak-left[0] < 45:
        return None
    cutoff = (peak+left[0])//2
    mask = red.point(lambda v: 255 if v >= cutoff else 0)
    bounds = mask.getbbox()
    if not bounds:
        return None
    a,b,c,d = bounds
    if (abs(a+c-w) > .10*w or abs(b+d-h) > .22*h or not .45*h < d-b < .86*h
            or not .22*w < c-a < .77*w):
        return None
    cells = mask.crop(bounds).resize((32,12), Image.Resampling.BOX)
    bits = int.from_bytes(cells.point(lambda v: 255 if v>=94 else 0).convert('1').tobytes(),'big')
    distances = [(bits ^ signature).bit_count() for signature in _SIGNATURES]
    if distances[index] > 68 or distances[index]+12 > min(value for i,value in enumerate(distances) if i!=index):
        return None
    core = red.point(lambda v: 255 if v >= peak-6 else 0)
    fg = [round(v) for v in ImageStat.Stat(patch,mask=core).median]
    if max(fg)-min(fg) > 32:
        return None
    # One common line-height for this column, including the dimmed control.
    # Keep the horizontal mask tied to the actually measured glyphs.
    margin = max(1,round(h*.10))
    pad = max(1,round(h*.045))
    return dict(x=x,y=y,w=w,h=h,text=_LABELS[index][0],confidence=100,fg=fg,bg=list(left),
                _source_ink=[x+a-pad,y+margin,c-a+2*pad,h-2*margin],
                _aoi_button=index, _center_label=True, _layout_cell=True, _source_font_style='sans')


def title_buttons(image):
    width,height=image.size
    scale=min(width/1920,height/1080)
    if scale < .24:
        return []
    left=(width-1920*scale)/2
    top=(height-1080*scale)/2
    rows=[]
    for i in range(len(_LABELS)):
        rect=(round(left+1302*scale),round(top+(464+100*i)*scale),
              round(320*scale),round(52*scale))
        row=read_button(image,rect,i)
        if row is not None:
            rows.append(row)
    return rows


def with_buttons(lines, buttons):
    def intersects(row, button):
        x,y,w,h=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
        return (button['x']<=x+w/2<button['x']+button['w'] and
                button['y']<=y+h/2<button['y']+button['h'])
    if buttons and all(b.get('_aoi_toolbar') for b in buttons):
        left=min(b['x'] for b in buttons); right=max(b['x']+b['w'] for b in buttons)
        top=min(b['y'] for b in buttons); bottom=max(b['y']+b['h'] for b in buttons)
        def toolbar_text(row):
            x,y,w,h=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
            return left-3<=x and x+w<=right+3 and top-3<=y and y+h<=bottom+3
        lines=[row for row in lines if not toolbar_text(row)]
    return [row for row in lines if not any(intersects(row,b) for b in buttons)] + buttons
