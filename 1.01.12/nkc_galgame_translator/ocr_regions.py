# SPDX-License-Identifier: MIT
"""Whole-frame OCR region refinement; no OCR engine or screen capture here."""
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from PIL import Image, ImageChops


class _VisualBoundary(str, Enum):
    TOP = 'local_pixel_separator_above'


def has_visual_separator(line):
    # Identity, not JSON text or provider output, establishes local provenance.
    return line.get('_row_boundary') is _VisualBoundary.TOP


def separator_above(image, line, previous):
    """Detect a nearly solid horizontal rule in the actual inter-row gap."""
    if previous is None:return False
    top=previous['y']+previous['h'];bottom=line['y']
    left=max(line['x'],previous['x']);right=min(line['x']+line['w'],previous['x']+previous['w'])
    if not (0<=top<bottom<=image.height and 0<=left<right<=image.width):return False
    if not 1<=bottom-top<=min(32,line['h']*.6) or right-left<max(24,line['h']*2):return False
    bg=line.get('bg')
    if not isinstance(bg,(tuple,list)) or len(bg)!=3:return False
    with image.crop((left,top,right,bottom)) as gap:
        with gap.resize((min(256,gap.width),gap.height),Image.Resampling.NEAREST) as sample:
            for y in range(sample.height):
                with sample.crop((0,y,sample.width,y+1)) as scan:
                    counts=scan.getcolors(scan.width) or ()
                    # Single color occupying most of a row is a rule, unlike
                    # scattered letters, icons, or a textured picture.
                    if any(count>=sample.width*.85 and max(abs(color[k]-bg[k]) for k in range(3))>=48
                           for count,color in counts):return True
    return False


def refine_ink(image, source):
    """Calibrate actual ink only where the row margins establish flat background.

    Complex/ambiguous backgrounds retain the OCR rectangle. We never invent
    glyph coordinates from string length, expand into adjacent cells or move
    the outer overlay box. The refined ink drives font size and baseline.
    """
    line=dict(source)
    original=line.get('_source_ink')
    if not isinstance(original,(list,tuple)) or len(original)!=4:
        return line
    if any(type(value) is not int for value in original):return line
    x,y,w,h=original
    left,top,right,bottom=(line['x'],line['y'],line['x']+line['w'],line['y']+line['h'])
    if not (0<=left<=x<x+w<=right<=image.width and 0<=top<=y<y+h<=bottom<=image.height):
        return line
    strips=[]
    if left<x:strips.append((left,y,x,y+h))
    if x+w<right:strips.append((x+w,y,right,y+h))
    if not strips:return line
    colors=[]
    for box in strips:
        with image.crop(box) as strip:
            with strip.resize((min(4,strip.width),min(32,strip.height)),Image.Resampling.NEAREST) as sample:
                for count,color in sample.getcolors(128) or ():
                    colors.extend([color]*count)
    # A color gradient/textured margin does not establish a reliable ink mask.
    if not colors or any(max(c[k] for c in colors)-min(c[k] for c in colors)>24 for k in range(3)):
        return line
    bg=tuple(sorted(c[k] for c in colors)[len(colors)//2] for k in range(3))
    with image.crop((x,y,x+w,y+h)) as crop:
        background=Image.new('RGB',crop.size,bg)
        difference=ImageChops.difference(crop,background)
        bands=difference.split()
        mask=ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2]).point(lambda v:255 if v>=24 else 0)
        bounds=mask.getbbox()
        count=mask.histogram()[255]
        # Dominant high-contrast ink is actual source color, not merely a
        # guessed white/black display color. This enables colored game text.
        ink_colors=[(amount,color) for amount,color in (crop.getcolors(4096) or ())
                    if max(abs(color[k]-bg[k]) for k in range(3))>=64]
        dominant=max(ink_colors,default=(0,None),key=lambda item:item[0])
        support=sum(amount for amount,color in ink_colors
                    if dominant[1] is not None and max(abs(color[k]-dominant[1][k]) for k in range(3))<=24)
        background.close();difference.close()
        for band in bands:band.close()
        mask.close()
    if not bounds or not .01<=count/(w*h)<=.75:return line
    ix,iy,ir,ib=bounds
    # Large changes indicate an unreliable OCR box/foreground, not proof of a
    # tighter whole line. Keep source evidence in that case.
    # Button cells can include unusually large vertical padding. A strongly
    # supported foreground color plus flat margins establishes actual ink even
    # below half the OCR box height; one-pixel decorations still cannot qualify.
    height_floor=max(5,h*.30) if dominant[1] is not None and support>=max(8,count*.75) else max(1,h*.5)
    if ir-ix<max(1,w*.5) or ib-iy<height_floor:return line
    # Keep a one-pixel antialias fringe inside the original OCR ink box.
    ix=max(0,ix-1);iy=max(0,iy-1);ir=min(w,ir+1);ib=min(h,ib+1)
    line['_source_ink']=[x+ix,y+iy,ir-ix,ib-iy]
    if dominant[1] is not None and support>=max(4,count*.25):
        line['fg']=list(dominant[1])
    return line


def _active_spans(projection, gap):
    spans = []
    for i, value in enumerate(projection):
        if value:
            if not spans or i - spans[-1][1] >= gap:
                spans.append((i, i+1))
            else:
                spans[-1] = (spans[-1][0], i+1)
    return spans


def warm_ink_mask(image):
    """Red/pink ink on a light surface can be faint in a grayscale OCR pass."""
    red, green, blue = image.split()
    with red, green, blue, ImageChops.subtract(red, green) as saturation, ImageChops.subtract(blue, red) as cool:
        with saturation.point(lambda v: 255 if v >= 32 else 0) as warm, cool.point(lambda v: 255 if v <= 35 else 0) as hue:
            with ImageChops.multiply(warm, hue) as visible:
                if not visible.getbbox():
                    return visible.copy()
                # Reject reds in dark areas before finding physical baselines.
                # Pixel UI warnings sit on a light surface even at low contrast.
                size = ((image.width+31)//32,(image.height+31)//32)
                with image.convert('L') as gray, gray.point(lambda v:255 if v>=205 else 0) as light:
                    with light.resize(size,Image.Resampling.BOX) as density:
                        with density.point(lambda v:255 if v>=150 else 0) as allowed:
                            with allowed.resize(image.size,Image.Resampling.NEAREST) as tiles:
                                return ImageChops.multiply(visible,tiles)


def warm_text_boxes(image, mask):
    """Find physical rows of warm ink with flat light margins, including short headings."""
    width,height = image.size
    _, vertical = mask.getprojection()
    result = []
    for top,bottom in _active_spans(vertical, 3):
        h = bottom-top
        if not 5 <= h <= 36:
            continue
        with mask.crop((0,top,width,bottom)) as band:
            horizontal, _ = band.getprojection()
        for left,right in _active_spans(horizontal,max(12,h*2)):
            w=right-left
            if not max(12,h) <= w <= 640:
                continue
            if top<3 or bottom+3>height or left<2 or right+2>width:
                continue
            with mask.crop((left,top,right,bottom)) as ink:
                count=ink.histogram()[255]
            if not max(10,w*h*.06)<=count<=w*h*.67:
                continue
            with image.crop((left,top-3,right,top)) as above, image.crop((left,bottom,right,bottom+3)) as below:
                colors=above.getcolors(3*w) or []
                amount,bg=max(colors,default=(0,(0,0,0)))
                if (amount<3*w*.85 or min(bg)<195
                        or not any(color==bg and n>=3*w*.85 for n,color in (below.getcolors(3*w) or []))):
                    continue
            with image.crop((left,top,right,bottom)) as source:
                colors=source.getcolors(w*h) or []
            fg=max(((n,c) for n,c in colors if c[0]-c[1]>=32 and c[2]-c[0]<=35),
                   default=(0,(0,0,0)))[1]
            result.append((left,top,right,bottom,bg,fg))
            if len(result)>=12:
                return result
    return result


_ACTION_LABELS = frozenset({'ok', 'cancel', 'yes', 'no', 'retry', 'abort', 'ignore'})


def _label_box(line):
    x, y, width, height = (line[k] for k in ('x', 'y', 'w', 'h'))
    return x, y, x+width, y+height


def _boxes_intersect(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def _blank_margin(image, box, bg):
    if box[0] >= box[2] or box[1] >= box[3]:
        return True
    with image.crop(box) as patch:
        return all(abs(low-value) <= 12 and abs(high-value) <= 12
                   for (low, high), value in zip(patch.getextrema(), bg))


def action_label_layout(image, lines, regions=None):
    """Fit short actions in verified flat space around their original center."""
    adjusted = []
    boxes = [_label_box(line) for line in lines]
    for index, line in enumerate(lines):
        adjusted.append(line)
        ink = line.get('_source_ink')
        if line['text'].strip().casefold() not in _ACTION_LABELS or not ink:
            continue
        x, y, w, h = ink
        bg, fg = line.get('bg'), line.get('fg')
        if not (6 <= h <= 64 and 4 <= w <= 6*h and bg and fg
                and max(abs(a-b) for a, b in zip(fg, bg)) >= 64):
            continue
        # The two sides are widened equally. The same space is used for
        # comparable actions; glyph cleanup still uses the original ink box.
        pad = max(2, (4*h-w+1)//2)
        left, top, right, bottom = x-pad, y-2, x+w+pad, y+h+2
        box = (left, top, right, bottom)
        bounds = (regions or ((0, 0, image.width, image.height),))[line.get('_selection_id', 0)]
        rx, ry, rw, rh = bounds
        if not (rx <= left < right <= rx+rw and ry <= top < bottom <= ry+rh):
            continue
        if any(index != other and _boxes_intersect(box, candidate) for other,candidate in enumerate(boxes)):
            continue
        margins = ((left, top, right, y), (left, y+h, right, bottom),
                   (left, y, x, y+h), (x+w, y, right, y+h))
        if all(_blank_margin(image, part, bg) for part in margins):
            adjusted[-1] = {**line, 'x': left, 'y': top, 'w': right-left, 'h': bottom-top,
                            '_center_label': True, '_layout_cell': True}
            boxes[index] = box
    return adjusted


def unchanged_action_box(before, after, line):
    if before.size != after.size:
        return False
    box = _label_box(line)
    with before.crop(box) as old, after.crop(box) as new:
        return ImageChops.difference(old, new).getbbox() is None


def retain_action_labels(before, after, previous, observed):
    """Focus artwork outside a validated label cannot revise its OCR text."""
    lines = list(observed)
    for prior in previous:
        if not prior.get('_center_label') or not unchanged_action_box(before, after, prior):
            continue
        box = _label_box(prior)
        overlaps = [index for index, line in enumerate(lines)
                    if _boxes_intersect(box, _label_box(line))]
        if not overlaps:
            if len(lines) < 512:
                lines.append(prior)
        elif len(overlaps) == 1:
            index, = overlaps
            candidate = lines[index]
            x0, y0, x1, y1 = _label_box(candidate)
            ix, iy, iw, ih = prior['_source_ink']
            # Only replace the one OCR observation at this same glyph. A newly
            # painted wider line, or a neighbor, must keep its own identity.
            if (candidate.get('_selection_id') == prior.get('_selection_id')
                    and _boxes_intersect((ix, iy, ix+iw, iy+ih), (x0, y0, x1, y1))
                    and box[0]-3 <= x0 < x1 <= box[2]+3
                    and box[1]-3 <= y0 < y1 <= box[3]+3):
                lines[index] = prior
    return lines


class RegionRefiner:
    """Bounded, deterministic per-frame processing after whole-frame discovery."""
    def __init__(self,workers=2):
        if type(workers) is not int or not 1<=workers<=8:
            raise ValueError('OCR refinement workers must be between 1 and 8')
        self.workers=workers
        self._pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='ocr-geometry')

    def refine(self,image,lines):
        if len(lines)>512:raise ValueError('Too many OCR regions')
        output=[dict(line) for line in lines]
        for line in output:line.pop('_row_boundary',None)
        # Find the nearest preceding overlapping row before dispatching jobs.
        # An unrelated neighboring column cannot create a false separator.
        previous={}
        for index,line in enumerate(output):
            candidates=[other for other in output if other is not line
                        and other['y']+other['h']<=line['y']
                        and min(other['x']+other['w'],line['x']+line['w'])-max(other['x'],line['x'])>=min(other['w'],line['w'])*.5]
            previous[index]=max(candidates,key=lambda row:row['y']+row['h'],default=None)
        indices=[];jobs=[];remaining=min(image.width*image.height*2,4000000)
        for index,line in enumerate(output):
            area=line['w']*line['h']
            if area<=0 or area>remaining:continue
            remaining-=area;indices.append(index);jobs.append((line,previous[index]))
        def refine(job):
            row,above=job
            row=refine_ink(image,row)
            if separator_above(image,row,above):row['_row_boundary']=_VisualBoundary.TOP
            return row
        for index,line in zip(indices,self._pool.map(refine,jobs)):
            output[index]=line
        return output

    def close(self):
        self._pool.shutdown(wait=True,cancel_futures=True)


def source_ink_color(image,box,bg):
    """Return the dominant contrasting ink only when a flat row supports it."""
    x,y,w,h=box
    if w<1 or h<1 or min(x,y)<0 or x+w>image.width or y+h>image.height:return None
    with image.crop((x,y,x+w,y+h)) as crop:
        crop.thumbnail((320,72),Image.Resampling.NEAREST)
        colors=crop.getcolors(4096)
        if not colors:return None
        def distance(a,b):return max(abs(u-v) for u,v in zip(a,b))
        if sum(n for n,c in colors if distance(c,bg)<24)<crop.width*crop.height*.30:return None
        ink=[(n,c) for n,c in colors if distance(c,bg)>=52]
        if not ink:return None
        _,dominant=max(ink)
        support=sum(n for n,c in ink if distance(c,dominant)<=32)
        if support>=max(4,.55*sum(n for n,c in ink)):return list(dominant)
