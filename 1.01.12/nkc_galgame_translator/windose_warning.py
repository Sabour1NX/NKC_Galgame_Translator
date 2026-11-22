# SPDX-License-Identifier: MIT
"""Recover the known Windose caution sentence only after checking its visible ink."""
from dataclasses import dataclass
from PIL import Image
from .ocr_regions import _active_spans

# Source text and Chinese localization of the two physical lines in this edition.
FIRST='\u66b4\u529b\u7684\u3060\u3063\u305f\u308a\u3001\u7cbe\u795e\u306b\u8ca0\u8377\u306e\u304b\u304b\u308b\u30b7\u30fc\u30f3\u304c\u3042\u308b\u304b\u3089\u3001\u5fc3\u304c\u3088\u308f\u3063\u3066\u3044\u308b\u4eba\u306f\u307e\u305a\u4f11\u3082'
SOURCE=FIRST+'\n\u3046\uff01'
SIMPLIFIED='\u6e38\u620f\u542b\u6709\u66b4\u529b\u573a\u666f\uff0c\u6709\u4e9b\u753b\u9762\u4e5f\u53ef\u80fd\u5e26\u6765\u5fc3\u7406\u8d1f\u62c5\u3002\u5982\u679c\u4f60\u73b0\u5728\u72b6\u6001\u4e0d\u597d\uff0c\u8bf7\u5148\u4f11\u606f\u3002'
TRADITIONAL='\u904a\u6232\u542b\u6709\u66b4\u529b\u5834\u666f\uff0c\u6709\u4e9b\u756b\u9762\u4e5f\u53ef\u80fd\u5e36\u4f86\u5fc3\u7406\u8ca0\u64d4\u3002\u5982\u679c\u4f60\u73fe\u5728\u72c0\u614b\u4e0d\u597d\uff0c\u8acb\u5148\u4f11\u606f\u3002'
# Downsampled ink densities, measured on the original two lines. Neither
# matching OCR words alone nor an absolute screen position authorizes a replacement.
SIGNATURES=(bytes.fromhex('3b212f15170b1525173116191d25060434242512041a2b1d00001a141a1d1f248e6b611c3f1e4a7457734e514734132a554e4b2a08364045163e2b224d605a5f7874583950234a843e6c6663583f302c594e5732062c3e503230382754636247795c503e3728526d4869544647454f325360485f193c403e44263e3d4345516f4d4346172f1955905474603b32380f165557482d1a345745222940425f585f49555a4b2f39245d685a5b5c362f3d1225434c422e2646413c282a3a404f47343e'),bytes.fromhex('000000001aa1a6a6a6955959592f00000000000000000000000000000078ffff0000000003141515152b7878784000000000000000000000000000000078ffff3a3a3a3a4892959595959595956a3a350500000000000000000000000078ffff7a7a7a7a69100d0d0d0d0d0d0d78f2db170000000000000000000000003f8787000000000003030303186565657c97890e0000000000000000000000002f6565000000001aa1a6a6a6955959592f0000000000000000000000000000002a5959'))


@dataclass(frozen=True)
class WarningGeometry:
    rows: tuple


def verified(line):
    return isinstance(line.get('_windose_geometry'),WarningGeometry)


def _measure(image,x,middle,scale,index):
    left=max(0,round(x-scale*.6))
    right=min(image.width,round(x+scale*(55 if index==0 else 4)))
    top=max(0,round(middle-scale*.88))
    bottom=min(image.height,round(middle+scale*.88))
    if right<=left or bottom<=top:
        return None
    with image.crop((left,top,right,bottom)) as patch:
        colors=patch.getcolors(patch.width*patch.height)
        bg=max(colors)[1]
        fg=max(((n,c) for n,c in colors if bg[1]-c[1]>48 and c[2]-c[1]>48),default=(0,None))[1]
        if fg is None or min(bg)<175:
            return None
        with patch.getchannel('G') as green,green.point(lambda v:255 if v<(bg[1]+fg[1])/2 else 0) as mask:
            with mask.crop((0,0,min(mask.width,round(scale*2.4)),mask.height)) as prefix:
                _,ys=prefix.getprojection()
            for y,end in sorted(_active_spans(ys,2),key=lambda v:abs(top+sum(v)/2-middle)):
                h=end-y
                if not scale*.38<=h<=scale*1.25:
                    continue
                with mask.crop((0,y,mask.width,end)) as band:
                    xs,_=band.getprojection()
                    for l,r in _active_spans(xs,max(3,round(h*1.05))):
                        if (l==0 and left>0) or abs(left+l-x)>scale*.65:
                            continue
                        aspect=(r-l)/h
                        if not ((34<aspect<48) if index==0 else (1.1<aspect<2.1)):
                            continue
                        with band.crop((l,0,r,h)) as ink,ink.resize((32,6),Image.Resampling.BILINEAR) as small:
                            distance=sum(abs(a-b) for a,b in zip(small.tobytes(),SIGNATURES[index]))/(32*6*255)
                        if distance < (.060 if index==0 else .106):
                            return (left+l,top+y,r-l,h),bg,fg
    return None


def recover(image,lines):
    opening=next((r for r in lines if '\u73fe\u4ee3' in r['text'] and '\u65e5\u672c' in r['text']),None)
    if not opening:
        return lines
    scale=opening['h']
    if not 8<=scale<=120:
        return lines
    hits=[r for r in lines if opening['y']+scale*2<r['y']<opening['y']+scale*6 and
          any(word in r['text'] for word in ('\u3060\u3063\u305f\u308a','\u5fc3\u304c\u3088\u308f','\u304b\u304b\u308b\u30b7','\u304c\u304b\u308b\u30b7','\u66b4\u529b\u7684'))]
    for hit in hits:
        # Whole-window OCR can return only the middle of the opening sentence.
        # The short continuation gives an independent left margin when available.
        margins=[r['x'] for r in lines if hit['y']+scale*.65<r['y']<hit['y']+scale*2.6
                 and ''.join(r['text'].split()) in ('\u3046!','\u3046\uff01','\u3046')]
        margins.append(opening['x'])
        first=None
        for x in dict.fromkeys(margins):
            first=_measure(image,x,hit['y']+hit['h']/2,scale,0)
            if first:
                break
        if not first:
            continue
        (l,t,w,h),bg,fg=first
        tail=_measure(image,x,t+h*2.1,scale,1)
        if not tail or max(abs(a-b) for a,b in zip(bg,tail[1]))>10:
            continue
        (lx,ty,tw,th)=tail[0]
        if not h*.25 < ty-t-h < h*1.6:
            continue
        left=max(0,min(l,lx)-1);top=max(0,t-1)
        right=min(image.width,max(l+w,lx+tw)+1);bottom=min(image.height,ty+th+1)
        physical=tuple((a-left,b-top,c,d) for a,b,c,d in (first[0],tail[0]))
        complete=dict(text=SOURCE,x=left,y=top,w=right-left,h=bottom-top,
                      fg=list(fg),bg=list(bg),confidence=100.,
                      _windose_geometry=WarningGeometry(physical))
        kept=[]
        for row in lines:
            a,b,c,d=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
            if a+c<=left or right<=a or b+d<=top or bottom<=b:
                kept.append(row)
            elif not (left-scale<=a and a+c<=right+scale and top-scale*.6<=b+d/2<bottom):
                # Do not remove a neighboring paragraph which spans this region.
                return lines
        return sorted(kept+[complete],key=lambda r:(r['y'],r['x']))
    return lines
