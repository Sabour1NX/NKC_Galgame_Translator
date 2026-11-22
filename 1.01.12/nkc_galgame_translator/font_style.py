# SPDX-License-Identifier: MIT
"""Approximate screenshot font styles, with bounded local evidence and caching.

This is style matching, not recovery of a game's original font file. No model,
font download, registry write or API request is involved.
"""
from collections import OrderedDict
from functools import lru_cache
import hashlib
import os
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

STYLES = ('sans', 'serif', 'mono', 'pixel')
SAMPLES = {'zh': '\u4e2d\u6587\u8bd1\u6587', 'ja': '\u65e5\u672c\u8a9e\u3042\u3044\u3046\u30a2\u30a4\u30a6', 'ko': '한국어번역',
           'en': 'Ag', 'fr': 'éàçœ', 'de': 'äöüß', 'es': 'ñá¿'}


@lru_cache(maxsize=16)
def _sample_font(filename):
    try:
        return ImageFont.truetype(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename), 36)
    except OSError:
        return None


def _normalized(image):
    box = image.getbbox()
    return image.crop(box).resize((192, 32), Image.Resampling.BILINEAR) if box else None


class SourceStyleMatcher:
    def __init__(self):
        self.cache = OrderedDict()

    def classify(self, image, line):
        text = str(line.get('text', '')).strip()
        box = line.get('_source_ink', [line[k] for k in ('x','y','w','h')])
        x,y,w,h = box
        if not text or len(text)>96 or h<8 or not (0<=x<x+w<=image.width and 0<=y<y+h<=image.height):
            return 'sans'
        # At most 65,536 source pixels are inspected per object.
        with image.crop((x,y,x+w,y+h)) as crop:
            crop.thumbnail((1024,64))
            key=(text,hashlib.sha256(crop.tobytes()).digest(),tuple(line.get('fg', (255,255,255))),tuple(line.get('bg',(0,0,0))))
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            style=self._classify(crop,text,line)
        self.cache[key]=style
        while len(self.cache)>256:self.cache.popitem(last=False)
        return style

    def _classify(self, crop, text, line):
        fg, bg = line.get('fg',(255,255,255)), line.get('bg',(0,0,0))
        contrast=sum((a-b)**2 for a,b in zip(fg,bg))
        if contrast<1200:return 'sans'
        pixels=list(crop.get_flattened_data())
        values=[255 if sum((v-b)**2 for v,b in zip(pixel,bg))>contrast*.32 else 0 for pixel in pixels]
        mask=Image.new('L',crop.size);mask.putdata(values)
        with mask:
            # Aliased, enlarged pixel fonts have long shared edge runs. A flat
            # palette alone is insufficient: ordinary antialiasing is retained.
            colors=crop.getcolors(64)
            runs=[]
            for y in range(crop.height):
                row=values[y*crop.width:(y+1)*crop.width];start=None
                for x,v in enumerate(row+[0]):
                    if v and start is None:start=x
                    elif not v and start is not None:runs.append(x-start);start=None
            if colors and len(colors)<=4 and runs and sorted(runs)[len(runs)//2]>=3:
                return 'pixel'
            normalized=_normalized(mask)
        if normalized is None:return 'sans'
        candidates=(('sans','arial.ttf'),('serif','times.ttf'),('mono','consola.ttf'))
        if any(ord(c)>0x2e80 for c in text):
            candidates=(('sans','msyh.ttc'),('serif','simsun.ttc'))
        scores=[]
        with normalized:
            for style,filename in candidates:
                font=_sample_font(filename)
                if font is None:continue
                bbox=font.getbbox(text)
                if bbox[2]-bbox[0]>8192:continue
                with Image.new('L',(max(1,bbox[2]-bbox[0]),max(1,bbox[3]-bbox[1]))) as sample:
                    ImageDraw.Draw(sample).text((-bbox[0],-bbox[1]),text,font=font,fill=255)
                    ref=_normalized(sample)
                    if ref is None:continue
                    with ref, ImageChops.difference(normalized,ref) as difference:
                        scores.append((ImageStat.Stat(difference).mean[0],style))
        return min(scores)[1] if scores else 'sans'


def candidates(style, target):
    group=target.lower().split('-')[0]
    serif=style=='serif';mono=style in ('mono','pixel')
    if group=='zh':
        preferred=('SimSun','NSimSun') if serif else ('NSimSun','SimSun') if mono else ('Microsoft YaHei UI','Microsoft YaHei')
    elif group=='ja':
        preferred=('Yu Mincho','MS Mincho') if serif else ('MS Gothic','Meiryo') if mono else ('Yu Gothic UI','Meiryo')
    elif group=='ko':
        preferred=('Batang','Gulim') if serif else ('GulimChe','Malgun Gothic') if mono else ('Malgun Gothic','Gulim')
    else:
        preferred=('Times New Roman','Georgia') if serif else ('Consolas','Courier New') if mono else ('Segoe UI','Arial')
    return tuple(dict.fromkeys((*preferred,'Microsoft YaHei UI','SimSun','Yu Gothic','Malgun Gothic','Segoe UI')))


class TargetFontSelector:
    def __init__(self, supports, target):
        self.supports=supports
        self.target=target
        self.cache=OrderedDict()

    def choose(self, style, text):
        style=style if style in STYLES else 'sans'
        # Whitespace needs no visible glyph. Include representative target
        # script even before the first meaningful translated token arrives.
        sample=SAMPLES.get(self.target.lower().split('-')[0],'Ag')
        charset=''.join(sorted(set(c for c in text+sample if not c.isspace())))
        if len(charset)>4096 or any(ord(c)>0xffff or 0xd800<=ord(c)<=0xdfff for c in charset):
            return None
        key=(style,charset)
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        family=next((face for face in candidates(style,self.target) if self.supports(face,charset)),None)
        result=(family,style=='pixel') if family else None
        self.cache[key]=result
        while len(self.cache)>256:self.cache.popitem(last=False)
        return result
