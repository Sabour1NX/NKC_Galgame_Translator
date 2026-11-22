# SPDX-License-Identifier: MIT
"""Read the bright subtitle layer over Aoichan's animated scenes."""
import re
import unicodedata
from difflib import SequenceMatcher
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat
from .ocr_regions import _active_spans

MINT_SAVE_CAPTION = '\u5c31\u5bdd\u6642\u306b\u9032\u884c\u72b6\u6cc1\u304c\u81ea\u52d5\u7684\u306b\u4fdd\u5b58\u3055\u308c\u307e\u3059\u3002'
SAVE_HELP={
    '\u3053\u306e\u30b2\u30fc\u30e0\u306f\u30aa\u30fc\u30c8\u30bb\u30fc\u30d6\u3068\u306a\u3063\u3066\u304a\u308a\u307e\u3059\u3002':('\u672c\u6e38\u620f\u91c7\u7528\u81ea\u52a8\u5b58\u6863\u3002','\u672c\u904a\u6232\u63a1\u7528\u81ea\u52d5\u5b58\u6a94\u3002'),
    MINT_SAVE_CAPTION:('\u5c31\u5bdd\u65f6\u4f1a\u81ea\u52a8\u4fdd\u5b58\u6e38\u620f\u8fdb\u5ea6\u3002','\u5c31\u5be2\u6642\u6703\u81ea\u52d5\u5132\u5b58\u904a\u6232\u9032\u5ea6\u3002')}


_NAME_READING = re.compile('^[\u201c"\u300e\u300c][\u58ee\u58ef\u8475][\u201d"\u300f\u300d](?=[.\u2026 ]+\u78ba\u304b\u306b\u7537\u6027\u3068\u3044\u3063\u3066\u3082\u901a\u3058\u308b\u540d\u524d)', re.M)
_ADVANCE_SUFFIX = re.compile('([\u3002\uff01\uff1f!?\u300d\u300f\u201d])(?:[ \\t]*(?:[\u25b6\u25ba\u25b8\u23f5\xbb\u226b]+|[\u3002\uff0e.]))+[ \\t]*$', re.M)
OPENING_PROMPT = '\u30aa\u30fc\u30d7\u30cb\u30f3\u30b0\u3092\u30b9\u30ad\u30c3\u30d7\u3057\u307e\u3059\u304b\uff1f'
OPENING_TRANSLATIONS = ('\u8981\u8df3\u8fc7\u5f00\u573a\u5417\uff1f','\u8981\u8df3\u904e\u958b\u5834\u55ce\uff1f')
OPENING_CHOICES = {
    '\u30b9\u30ad\u30c3\u30d7\u3057\u306a\u3044': ('\u4e0d\u8df3\u8fc7', '\u4e0d\u8df3\u904e'),
    '\u30b9\u30ad\u30c3\u30d7\u3059\u308b': ('\u8df3\u8fc7', '\u8df3\u904e'),
}
_OPENING_OCR = re.compile('^[>\u25b6\u25ba]?\u30aa\u30fc\u30d7\u30cb\u30f3\u30b0\u3092\u30b9\u30ad\u30c3\u30d7\u3057\u307e\u3059\u304b\\?[\u300d\u300f\u3002]*$')
_RENTAL_CLAUSES = {
    '\u683c\u5b89': ('\u79df\u91d1\u7279\u60e0','\u79df\u91d1\u7279\u60e0'),
    '\u99c5\u30c1\u30ab': ('\u90bb\u8fd1\u8f66\u7ad9','\u9130\u8fd1\u8eca\u7ad9'),
    '\u6577\u91d1\u793c\u91d1\u306a\u3057': ('\u514d\u62bc\u91d1\u3001\u514d\u793c\u91d1','\u514d\u62bc\u91d1\u3001\u514d\u79ae\u91d1'),
    '\u5373\u5165\u5c45\u53ef\u80fd': ('\u53ef\u7acb\u5373\u5165\u4f4f','\u53ef\u5373\u523b\u5165\u4f4f'),
    '\u30b7\u30a7\u30a2\u30cf\u30a6\u30b9': ('\u5408\u79df\u623f','\u5408\u79df\u623f'),
}
_RENTAL_TOKEN = re.compile('|'.join(_RENTAL_CLAUSES))
_RENTAL_NARRATION = re.compile('[.\u2026]*\u76ee\u306b[\u6b62\u7559]\u307e\u3063\u305f\u306e\u306f\u305d\u3093\u306a\u5e83\u544a[\u3002.\u2026]*$')


def repair_caption(text):
    """Normalize verified subtitle readings and isolated OCR decorations."""
    text = _ADVANCE_SUFFIX.sub(r'\1', _NAME_READING.sub('“\u8475”', text))
    if not any(term in text for term in ('\u30b9\u30ad\u30c3\u30d7','\u30bb\u30fc\u30d6','\u9032\u884c\u72b6\u6cc1')):
        return text
    lines = text.split('\n')
    for index, line in enumerate(lines):
        compact = unicodedata.normalize('NFKC', ''.join(line.split()))
        if _OPENING_OCR.fullmatch(compact):
            lines[index] = OPENING_PROMPT
        else:
            caption = compact.lstrip('>▶►').rstrip('\u3002')+'\u3002'
            if caption in SAVE_HELP:
                lines[index] = caption
    return '\n'.join(lines)


def opening_fragment(text):
    return ''.join(text.split()).lstrip('>\uff1e▶►') == '\u30aa\u30fc\u30d7\u30cb\u30f3\u30b0\u3092\u30b9'


def name_caption(text, traditional):
    caption = ''.join(repair_caption(text).split())
    if _NAME_READING.match(caption) and caption.rstrip('\u3002').endswith('\u901a\u3058\u308b\u540d\u524d\u3067\u306f\u3042\u308b'):
        return ('“\u8475”……\u786e\u5b9e\u662f\u4e2a\u7528\u4f5c\u7537\u6027\u540d\u5b57\u4e5f\u8bf4\u5f97\u901a\u7684\u540d\u5b57\u3002',
                '“\u8475”……\u78ba\u5be6\u662f\u500b\u7528\u4f5c\u7537\u6027\u540d\u5b57\u4e5f\u8aaa\u5f97\u901a\u7684\u540d\u5b57\u3002')[traditional]
    return None


def rental_ad_caption(source, traditional):
    """Accept observed flyer clauses with or without OCR punctuation or line breaks."""
    text = ''.join(unicodedata.normalize('NFKC', repair_caption(source)).split())
    narration = _RENTAL_NARRATION.search(text)
    flyer = text[:narration.start()] if narration else text
    flyer = flyer.strip('“”\u300c\u300d\u300e\u300f"')
    flyer = re.sub('[!\u3001,\u30fb\u3002]+', '', flyer)
    parts = _RENTAL_TOKEN.findall(flyer)
    if ''.join(parts) != flyer or not (parts or narration):
        return None
    translated = ['\uff01'.join(_RENTAL_CLAUSES[part][traditional] for part in parts)+'\uff01'] if parts else []
    if narration:
        translated.append(('……\u8fd9\u5219\u79df\u623f\u5e7f\u544a\u5438\u5f15\u4e86\u6211\u7684\u76ee\u5149\u3002','……\u9019\u5247\u79df\u5c4b\u5ee3\u544a\u5438\u5f15\u4e86\u6211\u7684\u76ee\u5149\u3002')[traditional])
    return '\n'.join(translated)


def _advance_arrow_start(mask, *, detached_from=None):
    """Locate separate or touching right-facing advance triangles."""
    spans = _active_spans(mask.getprojection()[0],1)
    reference_height = mask.height if detached_from is None else detached_from[0]
    candidates = []
    if len(spans)>=2 and (len(spans)>=3 or detached_from is not None):
        text_end = spans[-3][1] if detached_from is None else detached_from[1]
        candidates.append((text_end,spans[-2:]))
    if spans and (len(spans)>=2 or detached_from is not None):
        left,right = spans[-1]
        width = right-left
        if .30*reference_height<=width<=1.10*reference_height:
            with mask.crop((left,0,right,mask.height)) as tail:
                pixels = tail.tobytes()
                density = [sum(pixels[x::width]) for x in range(width)]
            middle = range(max(1,round(width*.35)),min(width,round(width*.65)+1))
            split = max(middle,key=lambda i:density[i]-density[i-1],default=0)
            if split and density[split]-density[split-1]>=255*.13*reference_height:
                text_end = spans[-2][1] if detached_from is None else detached_from[1]
                candidates.append((text_end,((left,left+split),(left+split,right))))
    for text_end,pair in candidates:
        if pair[0][0]-text_end<max(3,.16*reference_height) or pair[1][0]-pair[0][1]>max(3,.18*reference_height):
            continue
        top_edges = []
        for a,b in pair:
            width = b-a
            with mask.crop((a,0,b,mask.height)) as tile:
                bounds = tile.getbbox()
                if bounds is None:
                    break
                _,top,_,bottom = bounds
                pixels = tile.tobytes()
                density = [sum(pixels[x::width]) for x in range(width)]
            half = width//2
            if (not .15*reference_height<=width<=.55*reference_height
                    or detached_from is None and top<.42*reference_height
                    or not .18*reference_height<=bottom-top<=.56*reference_height
                    or sum(density[:half])<1.45*sum(density[-half:])):
                break
            top_edges.append(top)
        if len(top_edges)==2 and abs(top_edges[0]-top_edges[1])<=max(2,.12*reference_height):
            return pair[0][0]
    return None

def _without_advance_arrow(mask):
    start = _advance_arrow_start(mask)
    return mask if start is None else mask.crop((0,0,start,mask.height))


def _subtitle_bands(image):
    w,h = image.size
    if h<250 or w/h>3:
        return [(0,0,w,h)]
    return [(w//8,int(h*.40),w-w//8,int(h*.60)),
            (w//8,int(h*.83),int(w*.81),h)]


def erase_advance_markers(image):
    """Remove matched arrow silhouettes on an OCR-only image before box selection."""
    found = []
    for left,top,right,bottom in _subtitle_bands(image):
        with image.crop((left,top,right,bottom)) as patch:
            r,g,b = patch.split()
            light = ImageChops.darker(ImageChops.darker(r,g),b)
        masks = [light.point(lambda value:255 if value>=threshold else 0) for threshold in (208,172,138)]
        masks.append(_mint_ink(r,g,b))
        for mask in masks:
            last_text = None
            for y,end in _active_spans(mask.getprojection()[1],4):
                if not 5<=end-y<=88:
                    last_text = None
                    continue
                band = mask.crop((0,y,mask.width,end))
                bounds = band.getbbox()
                if not bounds:
                    continue
                start = _advance_arrow_start(band)
                if start is None and last_text and y-last_text[0]<=max(6,last_text[1]//3):
                    if bounds[0]-last_text[2]<=1.8*last_text[1] and len(_active_spans(band.getprojection()[0],1))<=2:
                        start = _advance_arrow_start(band,detached_from=last_text[1:])
                if start is not None:
                    trail = band.crop((start,0,band.width,band.height)).getbbox()
                    _,a,c,d = trail
                    found.append((left+start,top+y+a,left+start+c,top+y+d))
                if bounds[2]-bounds[0]>=3*(end-y) and end-y>=10:
                    last_text = (end,end-y,start if start is not None else bounds[2])
    if not found:
        return image
    cleaned = image.copy()
    markers = tuple(sorted(set(found)))
    cleaned.info['_aoi_advance_markers'] = (image.size,markers)
    for x,y,right,bottom in markers:
        pad = 2
        # Sample below the marker at the same horizontal position on the
        # subtitle plate. The renderer still receives the original capture.
        area = (max(0,x-pad),max(0,y-pad),min(image.width,right+pad),min(image.height,bottom+pad))
        sample_top = min(image.height-1,bottom+pad)
        with image.crop((area[0],sample_top,area[2],sample_top+1)) as sample:
            cleaned.paste(sample.resize((area[2]-area[0],area[3]-area[1])),area)
    return cleaned


def _text_right(image, ink, limit):
    frame_size,markers = image.info.get('_aoi_advance_markers',(None,()))
    if frame_size!=image.size:
        return limit
    x,y,w,h = ink
    return min((left for left,top,_,bottom in markers
                if x+w<=left<limit and y+h*.35<=top<y+h+8 and bottom>=y+h*.60),
               default=limit)


def _mint_ink(r,g,b):
    green = g.point(lambda value:255 if value>=138 else 0)
    above_red = ImageChops.subtract(g,r).point(lambda value:255 if value>=52 else 0)
    above_blue = ImageChops.subtract(g,b).point(lambda value:255 if value>=9 else 0)
    return ImageChops.multiply(green,ImageChops.multiply(above_red,above_blue))


def repair_ocr_rows(image, rows):
    """Keep subtitle coverage away from the advance arrow on the main OCR path."""
    result = []
    budget = 650_000
    for row in rows:
        text = repair_caption(row['text'])
        if opening_fragment(text):
            continue
        updated = {**row, 'text':text}
        x,y,w,h = row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
        if (not row.get('_center_label') and '\n' not in text and 9<=h<=88 and
                3*h<=w and w*h<=budget and 0<=x<x+w<=image.width and 0<=y<y+h<=image.height):
            budget -= w*h
            with image.crop((x,y,x+w,y+h)) as tile:
                r,g,b = tile.split()
                mint = _mint_ink(r,g,b)
                bright = ImageChops.darker(ImageChops.darker(r,g),b).point(lambda v:255 if v>=190 else 0)
                mint_count=mint.histogram()[255]
                white_count=ImageChops.subtract(bright,mint).histogram()[255]
                minimum=max(12,h//2)
                mixed=mint_count>=minimum and white_count>=minimum
                if mixed:
                    bright=ImageChops.lighter(bright,mint)
                elif text==MINT_SAVE_CAPTION and mint_count:
                    bright=mint
                trimmed = _without_advance_arrow(bright)
                ink = trimmed.getbbox()
                if (ink and ink[2]-ink[0]>=.72*w and
                        .045*w*h<=trimmed.histogram()[255]<=.48*w*h):
                    lx,top,right,bottom = ink
                    if mixed:
                        updated['_subtitle_read'] = True
                    if bright is mint:
                        updated['_subtitle_read'] = True
                        updated['fg'] = [round(channel) for channel in ImageStat.Stat(tile,mask=mint).median]
                    pad = max(4,min(8,round((bottom-top)*.16)))
                    updated['_source_ink'] = [x+lx,y+top,right-lx,bottom-top]
                    right_limit = x+trimmed.width if trimmed is not bright else row['x']+row['w']
                    width_limit = min(x+right+min(3,pad),right_limit)
                    updated['w'] = _text_right(image,updated['_source_ink'],width_limit)-row['x']
                    updated['h'] = min(row['y']+row['h'],y+bottom+pad)-row['y']
        if updated['text']:
            result.append(updated)
    return result


def _outlined_candidates(patch, left, top):
    """Locate by the neutral outline, then read all bright ink inside the line."""
    r,g,b=patch.split()
    low=ImageChops.darker(ImageChops.darker(r,g),b)
    high=ImageChops.lighter(ImageChops.lighter(r,g),b)
    neutral=ImageChops.subtract(high,low).point(lambda v:255 if v<18 else 0)
    shadow=ImageChops.multiply(neutral,high.point(lambda v:255 if v<134 else 0))
    near=shadow.filter(ImageFilter.BoxBlur(2)).point(lambda v:255 if v>=6 else 0)
    bright=ImageChops.multiply(neutral,low.point(lambda v:255 if v>=195 else 0))
    bright=ImageChops.lighter(bright,_mint_ink(r,g,b))
    outlined=ImageChops.multiply(bright,near)
    for y,end in _active_spans(outlined.getprojection()[1],2):
        h=end-y
        if not 9<=h<=76:
            continue
        strip=outlined.crop((0,y,patch.width,end))
        for x,right in _active_spans(strip.getprojection()[0],max(7,round(h*1.05))):
            w=right-x
            if not 2.6*h<=w<=1800:
                continue
            # Downscaling weakens the outline on thin first/last strokes and punctuation.
            # Reclaim only adjacent bright pixels on this same measured baseline.
            margin=max(2,round(h*.32))
            left_edge=max(0,x-margin); right_edge=min(patch.width,right+margin)
            nearby=bright.crop((left_edge,y,right_edge,end)).getbbox()
            if nearby:
                x,right=left_edge+nearby[0],left_edge+nearby[2]
                w=right-x
            bounds=(x,y,right,end)
            ink=_without_advance_arrow(bright.crop(bounds))
            if ink.width < w:
                w=ink.width
                right=x+w
                bounds=(x,y,right,end)
            marks=strip.crop((x,0,right,h)).histogram()[255]
            total=ink.histogram()[255]
            if not .055*w*h<=total<=.52*w*h or marks<.64*total:
                continue
            fg=[round(c) for c in ImageStat.Stat(patch.crop(bounds),mask=ink).median]
            bg=list(patch.getpixel((x,max(0,y-3))))
            yield (left+x,top+y,w,h),ink,fg,bg


def _choice_bands(image):
    """Locate wide, bright control borders before reading their interiors."""
    w, h = image.size
    columns = 40
    if w < 120 or h < 36:
        return
    with image.resize((columns, h), Image.Resampling.BOX) as preview:
        # Both silver and teal focus borders have a bright green channel.
        levels = preview.getchannel('G').tobytes()
    bright = bytes(255 if i >= 145 else 0 for i in range(256))
    lines = levels.translate(bright)
    border = re.compile(b'\\xff{8,}')
    edges = []
    for y in range(h):
        row = lines[y*columns:(y+1)*columns]
        span = max(border.finditer(row), key=lambda m: m.end()-m.start(), default=None)
        if span is None:
            continue
        left, right = span.span()
        if (edges and y == edges[-1][1] and min(edges[-1][3],right)-max(edges[-1][2],left)>=8
                and abs(sum(edges[-1][2:])-left-right)<=2):
            edges[-1][1] = y+1
            edges[-1][2] = min(left, edges[-1][2])
            edges[-1][3] = max(right, edges[-1][3])
        else:
            edges.append([y,y+1,left,right])
    found = 0
    for upper, lower in zip(edges, edges[1:]):
        start, end = upper[1], lower[0]
        height = end-start
        left, right = max(upper[2],lower[2]), min(upper[3],lower[3])
        if (not 18 <= height <= 180 or max(upper[1]-upper[0],lower[1]-lower[0])>max(4,height//8)
                or abs(upper[2]-lower[2])+abs(upper[3]-lower[3])>3
                or (right-left)*w/columns < height*4):
            continue
        middle = (start+end)//2 * columns
        if max(levels[middle+left], levels[middle+right-1])>=132:
            continue
        inset = max(2,height//9)
        yield left*w//columns, start+inset, right*w//columns, end-inset
        found += 1
        if found >= 8:
            break


def candidates(image):
    w,h=image.size
    bands = _subtitle_bands(image)
    for left,top,right,bottom in _choice_bands(image):
        with image.crop((left,top,right,bottom)) as patch:
            r,g,b = patch.split()
            neutral = ImageChops.darker(ImageChops.darker(r,b),g).point(lambda v:255 if v>=178 else 0)
            yield from _masked_candidates(patch,neutral,left,top,bottom-top,1)
    # Outlined characters survive the scene texture even when highlights and
    # the animated advance arrow occupy the gap between two baselines.
    for left,top,right,bottom in reversed(bands):
        yield from _outlined_candidates(image.crop((left,top,right,bottom)),left,top)
    for left,top,right,bottom in bands:
        patch=image.crop((left,top,right,bottom))
        r,g,b=patch.split()
        threshold=180 if h<=800 else 210
        neutral=ImageChops.darker(ImageChops.darker(r,b),g).point(lambda v:255 if v>=threshold else 0)
        from heapq import merge
        max_height=min(80,max(36,h//14))
        mint=_masked_candidates(patch,_mint_ink(r,g,b),left,top,max_height,1.2)
        white=_masked_candidates(patch,neutral,left,top,max_height,.85)
        yield from merge(mint,white,key=lambda entry:(entry[0][1],entry[0][0]))


def _masked_candidates(patch,mask,left,top,max_height,gap_ratio):
    for y,end in _active_spans(mask.getprojection()[1],3):
        height=end-y
        if not 9<=height<=max_height:
            continue
        band=mask.crop((0,y,mask.width,end))
        for x,stop in _active_spans(band.getprojection()[0],max(9,round(height*gap_ratio))):
            ink=_without_advance_arrow(band.crop((x,0,stop,height)))
            bounds=ink.getbbox()
            if not bounds:
                continue
            lx,ty,rx,by=bounds
            width,line_height=rx-lx,by-ty
            if width<line_height*2.6 or width>1800:
                continue
            rect=(x+lx,y+ty,x+rx,y+by)
            ink=ink.crop(bounds)
            occupancy=ink.histogram()[255]/(width*line_height)
            if not .045<=occupancy<=.48:
                continue
            fg=[round(v) for v in ImageStat.Stat(patch.crop(rect),mask=ink).median]
            bg=list(patch.getpixel((x,max(0,y+ty-2))))
            yield (left+x+lx,top+y+ty,width,line_height),ink,fg,bg


def single_subtitle_rows(rows):
    """Choose one reading when independent OCR lanes describe the same subtitle."""
    def geometry(row):
        return row.get('_source_ink') or tuple(row[key] for key in ('x','y','w','h'))

    def same_row(first,second):
        if first.get('_selection_id',0)!=second.get('_selection_id',0):
            return False
        x,y,w,h = geometry(first)
        a,b,c,d = geometry(second)
        return (min(x+w,a+c)-max(x,a)>=.70*min(w,c)
                and min(y+h,b+d)-max(y,b)>=.64*min(h,d)
                and abs((2*y+h)-(2*b+d))<=.68*max(h,d)
                and max(h,d)<=1.55*min(h,d))

    measured = [row for row in rows if row.get('_subtitle_read')
                or row['text']==OPENING_PROMPT or row['text'] in SAVE_HELP]
    if not measured:
        return rows
    measured.sort(key=lambda row:(row['text'] in SAVE_HELP or row['text']==OPENING_PROMPT,
                                 bool(row.get('_subtitle_read')),row.get('confidence') or 0),reverse=True)
    chosen = []
    for row in measured:
        if not any(same_row(row,good) for good in chosen):
            chosen.append(row)
    return [row for row in rows if any(row is good for good in chosen)
            or not any(same_row(row,good) for good in chosen)]


def superseded_boxes(rows, measured):
    """Two independent readings can replace one coarse, spanning OCR box."""
    if len(measured)<2:
        return rows
    def redundant(row):
        if row.get('_subtitle_read') or row.get('_preserve_source'):
            return False
        x,y,w,h=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
        parts={}
        for sub in measured:
            if sub.get('_selection_id',0)!=row.get('_selection_id',0):
                continue
            a,b,c,d=sub['_source_ink']
            overlap=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
            if overlap>=.8*c*d:
                parts[(a,b,c,d)]=overlap
        if len(parts)<2 or sum(parts.values())<.48*w*h:
            return False
        ordered=sorted(parts,key=lambda p:p[1])
        tolerance=max(4,min(p[3] for p in ordered)//3)
        left=min(p[0] for p in ordered); right=max(p[0]+p[2] for p in ordered)
        bottom=ordered[-1][1]+ordered[-1][3]
        if (abs(left-x)>tolerance or abs(right-x-w)>tolerance or
                abs(ordered[0][1]-y)>tolerance or abs(bottom-y-h)>tolerance):
            return False
        return all(0<=second[1]-(first[1]+first[3])<=max(first[3],second[3])
                   for first,second in zip(ordered,ordered[1:]))
    return [row for row in rows if not redundant(row)]


def recover(image, rows, portable, minimum, *, limit=8, skip_ink=()):
    if not portable.available():
        return rows
    accepted=list(skip_ink)
    attempts=0
    for (x,y,w,h),ink,fg,bg in candidates(image):
        if attempts>=limit:
            break
        if any(a-3<=x and x+w<=a+c+5 and abs(y-b)<=2 and abs(h-d)<=3
               for a,b,c,d in accepted):
            continue
        attempts+=1
        if h<25:
            # Subpixel strokes can extend beyond the bright core at small sizes.
            # Include a little source context for recognition only.
            dx,dy=(max(2,h//4),1) if h<=17 else (0,0)
            rect=(max(0,x-dx),max(0,y-dy),min(image.width,x+w+dx),min(image.height,y+h+dy))
            patch=image.crop(rect).getchannel('G')
            scale=max(2,round(40/h))
            enlarged=ImageOps.autocontrast(patch,cutoff=(0,1)).resize(
                (patch.width*scale,patch.height*scale),Image.Resampling.BICUBIC)
            ink=enlarged.point(lambda v:255 if v>=152 else 0)
        with ImageOps.expand(ImageOps.invert(ink),10,fill=255).convert('RGB') as strip:
            readings=portable.recognize(strip,'jpn','line')['lines']
        if len(readings)!=1:
            continue
        result=readings[0]
        text=repair_caption(re.sub(r'\s+', '',result['text']).lstrip('>\uff1e'))
        if opening_fragment(text):
            continue
        # The help text has fixed wording. Correct small OCR errors only with
        # near-full-length visual evidence and both halves agreeing.
        matched=next((s for s in SAVE_HELP if len(text)>=len(s)-1 and
                      text.rstrip('\u3002').endswith(s.rstrip('\u3002')[-4:]) and
                      SequenceMatcher(None,text,s).ratio()>=.86 and
                      SequenceMatcher(None,text[:10],s[:10]).ratio()>=.7),None)
        if not matched and (result['confidence']<max(60,minimum) or not re.search('[\u3041-\u30ff]',text)):
            continue
        text=matched or text
        def inside(row):
            a,b,c,d=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
            overlap=max(0,min(a+c,x+w)-max(a,x))*max(0,min(b+d,y+h)-max(b,y))
            return overlap>=.65*c*d
        rows=[row for row in rows if not inside(row)]
        accepted.append((x,y,w,h))
        # Padding supplies background samples only. The font fits the actual
        # glyph height and shares the original baseline on every repaint.
        pad=max(4,min(8,round(h*.16)))
        l,t=max(0,x-pad),max(0,y-pad)
        right = _text_right(image,(x,y,w,h),min(image.width,x+w+min(3,pad)))
        rows.append(dict(x=l,y=t,w=right-l,h=min(image.height,y+h+pad)-t,
                         text=text,confidence=result['confidence'],_source_ink=[x,y,w,h],
                         fg=fg,bg=bg,_subtitle_read=True,
                         _layout_cell=text.endswith(('\u3002','\uff01','\uff1f','!','?'))))
    return superseded_boxes(rows,[row for row in rows if row.get('_subtitle_read')])
