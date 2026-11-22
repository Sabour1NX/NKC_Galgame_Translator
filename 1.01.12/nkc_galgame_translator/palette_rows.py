# SPDX-License-Identifier: MIT
"""Read small captions on flat local surfaces alongside the full-frame engine."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import re
from PIL import Image, ImageChops, ImageOps
from .ocr_regions import _active_spans


def _patches(image):
    for top in range(0,image.height,24):
        bottom=min(top+48,image.height)
        if bottom-top<12:
            break
        previous=None
        start=0
        for left in range(0,image.width+64,64):
            bg=None
            if left<image.width:
                with image.crop((left,top,min(left+64,image.width),bottom)) as tile:
                    with tile.resize((12,10),Image.Resampling.NEAREST) as sample:
                        count,color=max(sample.getcolors(120))
                if count>=72:
                    bg=color
            if previous!=bg:
                if previous is not None:
                    yield max(0,start-24),top,min(left+24,image.width),bottom,previous
                start,previous=left,bg


def _candidates(patch,mask,left,top,bg,expected=None):
    _,vertical=mask.getprojection()
    for t,b in _active_spans(vertical,2):
        h=b-t
        if not 7<=h<=36 or t<2 or b+2>mask.height:
            continue
        with mask.crop((0,t,mask.width,b)) as band:
            xs,_=band.getprojection()
        for x,end in _active_spans(xs,max(9,round(h*.95))):
            w=end-x
            if not h*1.2<=w<=min(1600,96*h) or x<2 or end+2>mask.width:
                continue
            with patch.crop((x,t,end,b)) as glyph:
                colors=sorted(glyph.getcolors(w*h),reverse=True)
            if len(colors)<2 or colors[0][1]!=bg or colors[0][0]<w*h*.48:
                continue
            n,fg=max(((n,c) for n,c in colors if _distance(c,bg)>=48),default=(0,bg))
            if n<w*h*.055 or n<(w*h-colors[0][0])*.51:
                continue
            if expected and _distance(fg,expected)>8:
                continue
            yield left+x,top+t,left+end,top+b,bg,fg


def _isolated_candidates(patch,mask,left,top,bg,expected=None):
    horizontal,_=mask.getprojection()
    for l,r in _active_spans(horizontal,9):
        with mask.crop((l,0,r,mask.height)) as strip:
            _,vertical=strip.getprojection()
        for t,b in _active_spans(vertical,2):
            h=b-t
            if not 7<=h<=23 or t<2 or b+2>mask.height:
                continue
            with mask.crop((l,t,r,b)) as band:
                xs,_=band.getprojection()
            for a,z in _active_spans(xs,max(8,h//2)):
                x,end=l+a,l+z
                w=end-x
                if not h*1.3<=w<=min(360,24*h) or x<2 or end+2>mask.width:
                    continue
                with patch.crop((x,t,end,b)) as glyph:
                    colors=sorted(glyph.getcolors(w*h),reverse=True)
                if len(colors)<2 or colors[0][1]!=bg or colors[0][0]<w*h*.52:
                    continue
                n,fg=max(((n,c) for n,c in colors if _distance(c,bg)>=48),default=(0,bg))
                if n<w*h*.065 or n<(w*h-colors[0][0])*.56:
                    continue
                if expected and _distance(fg,expected)>8:
                    continue
                yield left+x,top+t,left+end,top+b,bg,fg


def _distance(a,b):
    return max(abs(x-y) for x,y in zip(a,b))


def _mask(patch,color,table):
    with Image.new('RGB',patch.size,color) as solid,ImageChops.difference(patch,solid) as delta:
        red,green,blue=delta.split()
        with red,green,blue,ImageChops.lighter(red,green) as rg,ImageChops.lighter(rg,blue) as peak:
            return peak.point(table)


_CONTRAST=[255 if n>=48 else 0 for n in range(256)]
_SIMILAR=[255 if n<=8 else 0 for n in range(256)]


def _patch_rows(size,pixels,bg):
    found={}
    with Image.frombytes('RGB',size,pixels) as patch:
        with _mask(patch,bg,_CONTRAST) as mask:
            for row in (*_candidates(patch,mask,0,0,bg), *_isolated_candidates(patch,mask,0,0,bg)):
                found[row[:4]]=row
        # Different inks can touch on neighboring baselines (e.g. a counter).
        with patch.resize((max(1,patch.width//2),max(1,patch.height//2)),Image.Resampling.NEAREST) as sample:
            colors=sorted(sample.getcolors(sample.width*sample.height),reverse=True)
        palette=[color for count,color in colors if count>=8 and _distance(color,bg)>=48]
        if palette:
            for fg in palette[:3]:
                with _mask(patch,fg,_SIMILAR) as mask:
                    for row in (*_candidates(patch,mask,0,0,bg,fg), *_isolated_candidates(patch,mask,0,0,bg,fg)):
                        found[row[:4]]=row
    return tuple(found.values())


def find_rows(image,scan=_patch_rows):
    found={}
    for l,t,r,b,bg in _patches(image):
        with image.crop((l,t,r,b)) as patch:
            local=scan(patch.size,patch.tobytes(),bg)
        for x,y,right,bottom,bg,fg in local:
            box=(l+x,t+y,l+right,t+bottom)
            found[box]=(*box,bg,fg)
    return sorted(found.values(),key=lambda row:(row[1],row[0],-(row[2]-row[0])))



def normalized_row(image,row):
    l,t,r,b,bg,fg=row
    channel=max(range(3),key=lambda k:abs(fg[k]-bg[k]))
    with image.crop((l,t,r,b)) as patch,patch.getchannel(channel) as ink:
        delta=fg[channel]-bg[channel]
        return ink.point(lambda n:max(0,min(255,round(255-255*(n-bg[channel])/delta))))


class PaletteReview:
    def __init__(self,reader):
        self.reader=reader
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='ocr-small-captions')
        self.read=lru_cache(maxsize=192)(self._read)
        # Full byte keys include size and background. Unchanged panels can move
        # without reusing coordinates; only the relative geometry is cached.
        self.scan=lru_cache(maxsize=128)(_patch_rows)

    def _read(self,size,pixels):
        with Image.frombytes('L',size,pixels) as ink:
            # Antialiased reduction recovers kana strokes from nearest-neighbor game scaling.
            with ink.resize(tuple(max(1,round(n*.75)) for n in size),Image.Resampling.LANCZOS) as scaled:
                with ImageOps.expand(scaled,10,fill=255) as padded:
                    rows=self.reader.recognize(padded,'jpn','line')['lines']
        if len(rows)!=1:
            return None
        row=rows[0]
        if not any('\u3041'<=c<='\u30ff' or '\u4e00'<=c<='\u9fff' for c in row['text']):
            return None
        return row['text'],row['confidence']

    def submit(self,image,threshold):
        return self.pool.submit(self._review,image,threshold)

    def _review(self,image,threshold):
        output=[]
        if not self.reader.available():
            return output
        accepted=[]
        for row in find_rows(image,self.scan)[:40]:
            l,t,r,b,bg,fg=row
            if any(bg==old[4] and _distance(fg,old[5])<=8 and l>=old[0]-1 and r<=old[2]+1
                   and min(b,old[3])-max(t,old[1])>=.8*(b-t) for old in accepted):
                continue
            with normalized_row(image,row) as ink:
                try:
                    result=self.read(ink.size,ink.tobytes())
                except (OSError,RuntimeError):
                    break
            if result and result[1]>=max(72,threshold):
                accepted.append(row)
                output.append(dict(x=max(0,l-1),y=max(0,t-1),w=min(image.width,r+1)-max(0,l-1),
                                   h=min(image.height,b+1)-max(0,t-1),_source_ink=[l,t,r-l,b-t],
                                   fg=list(fg),bg=list(bg),text=result[0],confidence=result[1]))
        return output

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True)
        self.read.cache_clear()
        self.scan.cache_clear()
        self.reader.close()


def merge_readings(lines,readings):
    """Split a fused object when multiple independent physical rows explain it."""
    def bounds(row):
        return row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
    def covers(row,candidate):
        x,y,w,h=bounds(row)
        l,t,cw,ch=bounds(candidate)
        return min(x+w,l+cw)-max(x,l)>=cw*.72 and min(y+h,t+ch)-max(y,t)>=ch*.70
    def same_baseline(row,candidate):
        x,y,w,h=bounds(row)
        l,t,cw,ch=bounds(candidate)
        return (min(h,ch)>=max(h,ch)*.70 and
                min(x+w,l+cw)-max(x,l)>=min(w,cw)*.62 and
                min(y+h,t+ch)-max(y,t)>=min(h,ch)*.8
                and _distance(row.get('bg',[0,0,0]),candidate.get('bg',[0,0,0]))<=18)
    accepted=[]
    for candidate in sorted(readings,key=lambda r:(-bounds(r)[2],-r['confidence'])):
        if not any(same_baseline(c,candidate) or covers(c,candidate) or covers(candidate,c) for c in accepted):
            accepted.append(candidate)
    kept=[]
    blocked=set()
    for original in lines:
        # Full-frame detectors often include a caption in the upper padding of
        # a numeric counter. Keep the digits and the measured caption separate.
        if re.fullmatch(r'[0-9][0-9 /.,:%]*',original['text']):
            x,y,w,h=(original[k] for k in ('x','y','w','h'))
            boundary=y
            for item in accepted:
                l,t,cw,ch=bounds(item)
                if (t <= y+h*.38 and y < t+ch+1 <= y+h*.55 and
                        min(x+w,l+cw)-max(x,l)>=cw*.6):
                    boundary=max(boundary,t+ch+1)
            if boundary>y:
                # Numeric objects are source-preserved; tighten their barrier
                # rather than passing an overlapping rectangle to the renderer.
                original={**original,'y':boundary,'h':y+h-boundary,
                          '_source_ink':[x,boundary,w,y+h-boundary]}
        matches=[i for i,item in enumerate(accepted) if covers(original,item) or same_baseline(original,item)]
        x,y,w,h=bounds(original)
        if len(matches)>=2:
            parts=[bounds(accepted[i]) for i in matches]
            # A couple of small same-row fragments do not explain a full OCR
            # box. Replacing the box in that case exposes the unmapped glyphs.
            from statistics import median
            left=min(r[0] for r in parts)
            right=max(r[0]+r[2] for r in parts)
            height=median(r[3] for r in parts)
            width=sum(r[2] for r in parts)
            by_x=sorted(parts)
            distinct_rows=max(r[1] for r in parts)-min(r[1] for r in parts)>=height*.78
            distinct_cells=all(b[0]-(a[0]+a[2])>=height*1.1 for a,b in zip(by_x,by_x[1:]))
            chars=sum(sum(c.isalnum() for c in accepted[i]['text']) for i in matches)
            original_chars=sum(c.isalnum() for c in original['text'])
            if ((distinct_rows or distinct_cells) and left<=x+w*.25
                    and right>=x+w*.76 and width>=w*.85 and chars>=original_chars*.65):
                continue
            blocked.update(matches)
        elif matches:
            i=matches[0]
            candidate=accepted[i]
            l,t,cw,ch=bounds(candidate)
            full_width=l<=x+max(2,w*.04) and l+cw>=x+w-max(2,w*.04)
            strong_read=candidate['confidence']>=original.get('confidence',0)-3
            same_text=candidate['text'].replace(' ','')==original['text'].replace(' ','')
            if full_width and ch>=h*.55 and (strong_read or same_text):
                continue
            blocked.add(i)
        kept.append(original)
    kept.extend(row for i,row in enumerate(accepted) if i not in blocked)
    return sorted(kept,key=lambda row:(row['y'],row['x']))[:512]
