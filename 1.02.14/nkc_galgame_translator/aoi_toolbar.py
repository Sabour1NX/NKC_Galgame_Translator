# SPDX-License-Identifier: MIT
"""Measure the three labels in the Aoichan dialogue toolbar from their pixels."""

from .i18n import ui_source
from PIL import Image, ImageStat
from .ocr_regions import _active_spans

# Occupancy sampled from the game's English HUD, independent of the target language.
LABELS = {
    'LOG': ('\u8bb0\u5f55', '\u8a18\u9304'),
    'AUTO': ('\u81ea\u52a8', '\u81ea\u52d5'),
    'SETTINGS': (ui_source('Settings'), '\u8a2d\u5b9a'),
}
_SIGNATURES = tuple(int(value,16) for value in (
    '00018018c00fe0fec00c3183c0183183c0183180c018330fc018331fc0183103c0183183c00c3183ff8ff1e7ff87c07c',
    '30427f3c304218363842186238421863684218636c4218434c4218437c4218637c421863c6461862c67c183e80001000',
    '66ee0026a8462155a804255588040584880405846e0405b22e04239128042391980423c5a8042355ee04217700000000',
))


_SMALL_SIGNATURES = tuple(int(value,16) for value in (
    'c003f03fc00c30c3c00c30c3c00c0cc0c00c0cc0c00c0cc0c00c0cc3c00c0cc0c00c0cc0c00c30c3ffc3f03fffc3f03f',
    '38827f1f388208233882082338820823d8820820d8820820d8820820fc820823fc820823c4820823c47c081fc47c081f',
    'fefe4d77b0424d55b0424d5590424d445e424f425e424f4278424b5130424b5130424b51b0424b55fe424977fe424977',
))


def toolbar_buttons(image):
    width,height=image.size
    scale=max(1,min(width/1920,height/1080))
    left,top=max(0,width-round(276*scale)),max(0,height-round(33*scale))
    patch=image.crop((left,top,width,height))
    mask=patch.getchannel('R').point(lambda v:255 if v>=136 else 0)
    for start,stop in _active_spans(mask.getprojection()[1],1):
        line_height=stop-start
        if not 6<=line_height<=68:
            continue
        band=mask.crop((0,start,mask.width,stop))
        spans=_active_spans(band.getprojection()[0],max(3,round(line_height*.48)))
        for i in range(len(spans)-2):
            cluster=spans[i:i+3]
            if any(not .55*line_height<=b[0]-a[1]<=2.4*line_height for a,b in zip(cluster,cluster[1:])):
                continue
            result=[]
            for label,(a,b),signature,small,ratio in zip(LABELS,cluster,_SIGNATURES,_SMALL_SIGNATURES,(1.85,2.5,5.1)):
                glyph=band.crop((a,0,b,line_height))
                bounds=glyph.getbbox()
                gh=bounds[3]-bounds[1]
                if abs((b-a)/gh-ratio)>ratio*.28:
                    break
                glyph=glyph.crop(bounds)
                cells=glyph.resize((32,12),Image.Resampling.BOX)
                actual=int.from_bytes(cells.point(lambda v:255 if v>=94 else 0).convert('1').tobytes(),'big')
                distance=(actual^signature).bit_count()
                if gh<=12:
                    distance=min(distance,(actual^small).bit_count())
                if distance>111:
                    break
                x,y=left+a,top+start+bounds[1]
                w=b-a;pad=max(4,round(gh*.30))
                margin=max(pad+2,round(gh*.48),(round(2.4*gh)-w+1)//2)
                l,t=x-margin,y-pad
                if l<0 or t<0 or x+w+margin>width or y+gh+pad>height:
                    break
                bg=list(image.getpixel((l,y+gh//2)))
                if bg[2]-bg[0]<14:
                    break
                fg=[round(v) for v in ImageStat.Stat(image.crop((x,y,x+w,y+gh)),mask=glyph).median]
                result.append(dict(text=label,confidence=100,x=l,y=t,w=w+2*margin,h=gh+2*pad,
                                   _source_ink=[x,y,w,gh],fg=fg,bg=bg,_center_label=True,
                                   _layout_cell=True,_aoi_toolbar=True,_source_font_style='sans'))
            if len(result)==3:
                return result
    return []
