#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NKC_Galgame_Translator contributors
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""Independent image OCR utility. No imports from NKC_Galgame_Translator.

stdin: one bounded JSON object per line; image_path is frame.bmp under --input-root.
stdout: {"lines": [{"text": "...", "x": 0, "y": 0, "w": 10, "h": 20,
                      "confidence": 90.0}], "ocr_ms": 12.3}.
Errors return {"error": "..."}. A {"quit": true} request exits cleanly.
Any program may use this generic image/JSON interface. Tesseract and models
retain their own Apache-2.0 licenses; tesserocr retains its MIT license.
"""
import argparse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import json
import math
import os
import re
import struct
from pathlib import Path
import sys
import time

MAX_REQUEST_CHARS=16384
MAX_RESPONSE_BYTES=1048576


def set_rgb_image(engine,image):
    """Return the raw buffer: caller retains it through all recognition calls."""
    if image.mode!='RGB' or not (1<=image.width<=4096 and 1<=image.height<=4096):
        raise ValueError('Invalid RGB frame')
    pixels=image.tobytes('raw','RGB')
    if len(pixels)!=image.width*image.height*3:raise ValueError('Invalid pixel buffer')
    engine.SetImageBytes(pixels,image.width,image.height,3,image.width*3)
    return pixels


def load_image(path, input_root):
    """Decode only our bounded, uncompressed RGB BMP frames; no format guessing."""
    from PIL import Image
    if not isinstance(path,str) or len(path)>4096 or any(ord(c)<32 for c in path):
        raise ValueError('Invalid input')
    if path.replace('/','\\').startswith(('\\\\','\\??\\')):
        raise ValueError('Invalid input')
    frame=Path(path)
    if any(':' in part for part in frame.parts[1:]):raise ValueError('Invalid input')
    # The producer owns a unique temp directory and only submits its frame.bmp.
    if frame.name!='frame.bmp' or frame.parent.absolute()!=input_root.absolute():
        raise ValueError('Invalid input')
    if frame.is_symlink() or getattr(frame.lstat(),'st_file_attributes',0)&0x400:
        raise ValueError('Invalid input')
    size=frame.stat().st_size
    if size<54 or size>4096*4096*4+1024:raise ValueError('Invalid BMP size')
    with frame.open('rb') as stream:
        header=stream.read(54)
        if header[:2]!=b'BM':raise ValueError('Only BMP is supported')
        offset=struct.unpack_from('<I',header,10)[0]
        dib,width,height,planes,bits,compression=struct.unpack_from('<IiiHHI',header,14)
        if dib!=40 or not 1<=width<=4096 or not 1<=abs(height)<=4096 or planes!=1 or bits not in (24,32) or compression!=0:
            raise ValueError('Unsupported BMP frame')
        stride=((width*bits+31)//32)*4
        if offset!=54 or size!=offset+stride*abs(height):raise ValueError('Invalid BMP bounds')
        stream.seek(0)
        with Image.open(stream,formats=['BMP']) as image:
            if image.size!=(width,abs(height)):raise ValueError('Invalid BMP dimensions')
            image.load()
            return image.convert('RGB')


def split_word_cells(line, words, language):
    """Split only large measured gaps; never estimate a glyph's position.

    Input word rectangles come from the OCR iterator in the input-image space.
    Three row-heights of empty horizontal space establish separate cells. A
    normal word space or English name stays part of its original physical row.
    """
    ordered=sorted(words,key=lambda item:item['x'])
    if len(ordered)<2 or len(ordered)>512:
        return [line]
    groups=[[]]
    right=None
    for word in ordered:
        if right is not None and word['x']-right>=max(24,3*line['h']):
            groups.append([])
        groups[-1].append(word)
        right=max(right or 0,word['x']+word['w'])
    if len(groups)==1:
        return [line]
    result=[]
    for group in groups:
        left=min(word['x'] for word in group);top=min(word['y'] for word in group)
        right=max(word['x']+word['w'] for word in group)
        bottom=max(word['y']+word['h'] for word in group)
        text=' '.join(word['text'] for word in group)
        if language.startswith('jpn'):
            text=re.sub(r'(?<=[\u3040-\u30ff\u3400-\u9fff]) +(?=[\u3000-\u30ff\u3400-\u9fff])','',text)
        result.append({'text':text,'x':left,'y':top,'w':right-left,'h':bottom-top,
                       'confidence':line['confidence'],'separated_cell':True})
    return result


def read_lines(engine,tesserocr,language):
    iterator=engine.GetIterator()
    lines=[];current=None;words=[]
    if iterator is None:
        return lines
    def text_at(item,level):
        try:
            return (item.GetUTF8Text(level) or '').strip()
        except RuntimeError as exc:
            if 'No text returned' in str(exc):return ''
            raise
    def flush():
        if current is not None:
            lines.extend(split_word_cells(current,words,language))
            if len(lines)>512 or any(len(item['text'])>16000 for item in lines) or sum(len(item['text']) for item in lines)>64000:
                raise ValueError('OCR output exceeds limit')
    for word in tesserocr.iterate_level(iterator,tesserocr.RIL.WORD):
        if word.Empty(tesserocr.RIL.WORD):continue
        if current is None or word.IsAtBeginningOf(tesserocr.RIL.TEXTLINE):
            flush();current=None;words=[]
            text=text_at(word,tesserocr.RIL.TEXTLINE)
            bounds=word.BoundingBox(tesserocr.RIL.TEXTLINE)
            if not text or not bounds:continue
            if language.startswith('jpn'):
                text=re.sub(r'(?<=[\u3040-\u30ff\u3400-\u9fff]) +(?=[\u3000-\u30ff\u3400-\u9fff])','',text)
            left,top,right,bottom=bounds
            current={'text':text,'x':left,'y':top,'w':right-left,'h':bottom-top,
                     'confidence':word.Confidence(tesserocr.RIL.TEXTLINE)}
        text=text_at(word,tesserocr.RIL.WORD)
        bounds=word.BoundingBox(tesserocr.RIL.WORD)
        if text and bounds:
            left,top,right,bottom=bounds
            words.append({'text':text,'x':left,'y':top,'w':right-left,'h':bottom-top})
            if len(words)>512:raise ValueError('OCR row exceeds word limit')
    flush()
    return lines


def _overlapping(first, second):
    return (max(first['x'],second['x']) < min(first['x']+first['w'],second['x']+second['w'])
            and max(first['y'],second['y']) < min(first['y']+first['h'],second['y']+second['h']))


def color_contrast(image,background):
    """Map RGB distance from measured background to dark ink/light paper."""
    from PIL import Image,ImageChops
    with Image.new('RGB',image.size,background) as flat,ImageChops.difference(image,flat) as delta:
        bands=delta.split()
        try:
            with ImageChops.lighter(bands[0],bands[1]) as first:
                with ImageChops.lighter(first,bands[2]) as distance:
                    with distance.point([255-min(255,max(0,v-8)*4) for v in range(256)]) as ink:
                        return ink.convert('RGB')
        finally:
            for band in bands:band.close()


def flat_color_frame(image):
    """Normalize chromatic text on an overwhelmingly flat background only.

    RGB contrast, unlike luminance inversion, retains equal-luminance colors.
    Monochrome and complex game pictures keep their established OCR path.
    """
    from PIL import Image
    with image.resize((128,128),Image.Resampling.NEAREST) as sample:
        colors=sample.getcolors(16384) or []
    if not colors:return image
    count,background=max(colors,key=lambda item:item[0])
    if count<16384*.80:return image
    colored=sum(n for n,c in colors if max(abs(c[k]-background[k]) for k in range(3))>=48
                and (max(c)-min(c)>=32 or max(background)-min(background)>=32))
    if colored<8:return image
    return color_contrast(image,background)


def find_text_surfaces(image, *, single_rows=False):
    """Find bounded, genuinely flat rectangular panels in the whole frame.

    Long uninterrupted scan lines propose a surface; four solid edges and a
    dominant interior color establish it. These are image-derived regions, not
    arbitrary tiles. Complex art is left to the ordinary whole-frame engines.
    """
    from PIL import Image
    width,height=image.size
    if image.mode!='RGB' or not (1<=width<=4096 and 1<=height<=4096):
        raise ValueError('Invalid RGB frame')
    with image.quantize(colors=64,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE) as palette:
        indices=palette.tobytes()
    runs=re.compile(rb'(.)\1{79,}',re.DOTALL)
    proposals=[];seen=set();examined=0
    for y in range(0,height,4):
        for match in runs.finditer(indices[y*width:(y+1)*width]):
            left,right=match.span();color=indices[y*width+left]
            if any(l<=left and right<=r and t<=y<b for l,t,r,b in proposals):continue
            top=bottom=y
            while top>0 and indices[(top-1)*width+left]==color and indices[(top-1)*width+right-1]==color:top-=1
            while bottom+1<height and indices[(bottom+1)*width+left]==color and indices[(bottom+1)*width+right-1]==color:bottom+=1
            box=(left,top,right,bottom+1)
            if box in seen:continue
            seen.add(box);examined+=1
            if examined>512:break
            w,h=right-left,bottom-top+1
            if w<80 or h<(24 if single_rows else 48) or w*h>min(6000000,width*height*.85):continue
            edge=(indices[top*width+left:top*width+right].count(color)
                  +indices[bottom*width+left:bottom*width+right].count(color))
            if edge<1.95*w:continue
            with image.crop(box) as crop,crop.resize((min(128,w),min(128,h)),Image.Resampling.NEAREST) as sample:
                colors=sample.getcolors(sample.width*sample.height) or []
            count,bg=max(colors,default=(0,(0,0,0)))
            if count<sample.width*sample.height*.55:continue
            contrast=sum(n for n,c in colors if max(abs(c[k]-bg[k]) for k in range(3))>=48)
            if not .005<=contrast/(sample.width*sample.height)<=.40:continue
            proposals=[old for old in proposals if not(left<=old[0] and top<=old[1] and old[2]<=right and old[3]<=bottom+1)]
            proposals.append(box)
        if examined>512:break
    accepted=[];area=0
    for box in sorted(proposals,key=lambda b:(-(b[2]-b[0])*(b[3]-b[1]),b[1],b[0])):
        left,top,right,bottom=box;cost=(right-left)*(bottom-top)
        if any(max(left,l)<min(right,r) and max(top,t)<min(bottom,b) for l,t,r,b in accepted):continue
        if area+cost>min(8000000,width*height):continue
        accepted.append(box);area+=cost
        if len(accepted)==8:break
    return sorted(accepted,key=lambda b:(b[1],b[0]))


def surface_rows(normalized):
    """Actual ink row bands; do not divide height by OCR text/newline counts."""
    with normalized.convert('L') as gray:
        data=bytearray(gray.tobytes())
    width,height=normalized.size
    # Window borders are long vertical ink strokes, not part of every text
    # row. Suppress them in discovery only; OCR still sees the original crop.
    for x in range(width):
        if sum(data[y*width+x]<128 for y in range(height))>=height*.70:
            data[x::width]=b'\xff'*height
    active=[]
    for y in range(height):
        count=sum(v<128 for v in data[y*width:(y+1)*width])
        if 2<=count<=width*.75:active.append(y)
    bands=[]
    for y in active:
        if not bands or y-bands[-1][-1]>2:bands.append([y])
        else:bands[-1].append(y)
    result=[]
    for band in bands:
        top,bottom=band[0],band[-1]+1;h=bottom-top
        if not 5<=h<=80:continue
        xs=[x for x in range(width) if any(data[y*width+x]<128 for y in band)]
        if not xs:continue
        cells=[[xs[0]]]
        for x in xs[1:]:
            if x-cells[-1][-1]>=max(24,3*h):cells.append([x])
            else:cells[-1].append(x)
        for cell in cells:
            if cell[-1]-cell[0]+1>=max(12,h):
                result.append((cell[0],top,cell[-1]+1,bottom))
    return result[:64]


def read_text_surfaces(engine,tesserocr,image,language,regions,cache=None):
    """Quality pass on discovered panels; small text is normalized before read.

    Results below the normal 55% threshold remain diagnostics, not translations.
    Exact crop bytes participate in the cache key; no reuse across changed ink.
    """
    from PIL import Image,ImageOps,ImageFilter
    output=[];budget=0;count=0
    for left,top,right,bottom in regions:
        with image.crop((left,top,right,bottom)) as crop:
            with crop.resize((min(128,crop.width),min(128,crop.height)),Image.Resampling.NEAREST) as sample:
                bg=max(sample.getcolors(16384) or [(0,crop.getpixel((0,0)))])[1]
            with color_contrast(crop,bg) as normalized:
                physical=surface_rows(normalized)
                small=[row for row in physical if row[3]-row[1]<=24]
                if len(small)<2 and not (language.startswith('jpn') and len(small)==1 and crop.height<=52):continue
                # Read a complete surface before its physical bands. Nearby
                # icons may overlap several baselines, making a projection
                # alone insufficient to discover those rows.
                scale=min(2,4000//max(crop.size))
                cost=crop.width*crop.height*scale*scale
                if scale>=1 and budget+cost<=8000000:
                    budget+=cost
                    pixels=normalized.tobytes();key=('panel-v1',language,normalized.size,hashlib.sha256(pixels).digest())
                    found=cache.get(key,pixels) if cache else None
                    if found is None:
                        with normalized.resize((crop.width*scale,crop.height*scale),Image.Resampling.LANCZOS) as enlarged,ImageOps.expand(enlarged,12,'white') as bordered:
                            retained=set_rgb_image(engine,bordered)
                            engine.SetPageSegMode(tesserocr.PSM.AUTO);engine.Recognize()
                            found=read_lines(engine,tesserocr,language)
                        if cache:cache.put(key,pixels,found)
                    for line in found:
                        lx=max(0,math.floor((line['x']-12)/scale));ly=max(0,math.floor((line['y']-12)/scale))
                        lr=min(crop.width,math.ceil((line['x']+line['w']-12)/scale));lb=min(crop.height,math.ceil((line['y']+line['h']-12)/scale))
                        if lx<lr and ly<lb:
                            output.append({**line,'x':left+lx,'y':top+ly,'w':lr-lx,'h':lb-ly})
                    # Coarse bitmap glyphs can become harder at 2x. A bounded
                    # smoothed native-scale pass supplies independent evidence;
                    # it does not replace a stronger existing reading.
                    if (language.startswith('jpn') and sum(l['confidence'] for l in found)/max(1,len(found))<75
                            and budget+crop.width*crop.height<=8000000):
                        budget+=crop.width*crop.height
                        pixels=normalized.tobytes();key=('panel-soft-v1',language,normalized.size,hashlib.sha256(pixels).digest())
                        alternate=cache.get(key,pixels) if cache else None
                        if alternate is None:
                            with normalized.filter(ImageFilter.GaussianBlur(1)) as softened,ImageOps.expand(softened,12,'white') as bordered:
                                retained=set_rgb_image(engine,bordered);engine.SetPageSegMode(tesserocr.PSM.AUTO);engine.Recognize()
                                alternate=read_lines(engine,tesserocr,language)
                            if cache:cache.put(key,pixels,alternate)
                        for line in alternate:
                            lx=max(0,line['x']-12);ly=max(0,line['y']-12)
                            lr=min(crop.width,line['x']+line['w']-12);lb=min(crop.height,line['y']+line['h']-12)
                            if lx<lr and ly<lb:output.append({**line,'x':left+lx,'y':top+ly,'w':lr-lx,'h':lb-ly})
                for x,y,r,b in physical:
                    h=b-y
                    # Large pixel fonts are already handled by the pixel cell
                    # refiner. This pass targets small text, in any palette.
                    if h>24:continue
                    box=(max(0,x-2),max(0,y-2),min(crop.width,r+2),min(crop.height,b+2))
                    with normalized.crop(box) as row:
                        scale=2
                        cost=row.width*row.height*scale*scale
                        if budget+cost>8000000 or count>=48:break
                        budget+=cost;count+=1
                        pixels=row.tobytes();key=('surface-v1',language,row.size,hashlib.sha256(pixels).digest())
                        found=cache.get(key,pixels) if cache else None
                        if found is None:
                            with row.resize((row.width*scale,row.height*scale),Image.Resampling.LANCZOS) as enlarged,ImageOps.expand(enlarged,12,'white') as bordered:
                                retained=set_rgb_image(engine,bordered)
                                engine.SetPageSegMode(tesserocr.PSM.SINGLE_LINE);engine.Recognize()
                                found=read_lines(engine,tesserocr,language)
                            if cache:cache.put(key,pixels,found)
                    for line in found:
                        lx=max(0,box[0]+math.floor((line['x']-12)/scale));ly=max(0,box[1]+math.floor((line['y']-12)/scale))
                        lr=min(crop.width,box[0]+math.ceil((line['x']+line['w']-12)/scale))
                        lb=min(crop.height,box[1]+math.ceil((line['y']+line['h']-12)/scale))
                        if lx>=lr or ly>=lb or not line['text']:continue
                        output.append({**line,'x':left+lx,'y':top+ly,'w':lr-lx,'h':lb-ly})
    return output


def merge_surface_detections(primary,supplemental):
    """Accept complete measured rows, replacing only clearly weaker same rows."""
    merged=[dict(row) for row in primary]
    for row in sorted(supplemental,key=lambda v:-v['confidence']):
        if row['confidence']<55:continue
        overlaps=[old for old in merged if _overlapping(row,old)]
        # Ignore an avatar decoded as a Latin prefix outside a measured panel.
        if len(overlaps)==1 and row['confidence']>=90:
            old=overlaps[0]
            if (old['h']>row['h']*1.5 and old['x']+row['h']<row['x']
                    and old['text'].replace(' ','').endswith(row['text'].replace(' ',''))
                    and any('\u3041'<=c<='\u30ff' for c in row['text'])):
                merged.remove(old)
                overlaps=[]
        if overlaps:
            if any(abs((old['y']+old['h']/2)-(row['y']+row['h']/2))>min(old['h'],row['h'])*.3
                   or old['x']<row['x']-2 or old['x']+old['w']>row['x']+row['w']+2
                   or row['confidence']<old['confidence']+5 for old in overlaps):continue
            merged=[old for old in merged if old not in overlaps]
        if len(merged)<512:merged.append(dict(row))
    if sum(len(row['text']) for row in merged)>64000:raise ValueError('OCR output exceeds limit')
    return sorted(merged,key=lambda row:(row['y'],row['x']))


def find_contrast_rows(image):
    """Find measured flat colored/selected rows, without guessing text boxes."""
    from PIL import Image
    if image.mode!='RGB' or not (1<=image.width<=4096 and 1<=image.height<=4096):
        raise ValueError('Invalid RGB frame')
    width,height=image.size
    with image.quantize(colors=64,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE) as palette:
        indices=palette.tobytes()
    runs=re.compile(rb'(.)\1{47,}',re.DOTALL)
    regions=[];seen=set();extents={};examined=0;area=0
    for y in range(height):
        row=indices[y*width:(y+1)*width]
        for match in runs.finditer(row):
            left,right=match.span()
            color=indices[y*width+left]
            if any(l<=left and right<=r and t<=y<b for l,t,r,b in regions):continue
            key=(left,right,color)
            if any(t<=y<b for t,b in extents.get(key,())):continue
            # The same horizontal extent can occur on several separate rows;
            # only memoize its discovered vertical interval, not its x pair.
            top=bottom=y
            while top>0 and y-top<=128 and indices[(top-1)*width+left]==color and indices[(top-1)*width+right-1]==color:top-=1
            while bottom+1<height and bottom-y<=128 and indices[(bottom+1)*width+left]==color and indices[(bottom+1)*width+right-1]==color:bottom+=1
            box=(left,top,right,bottom+1)
            extents.setdefault(key,[]).append((top,bottom+1))
            if box in seen:continue
            seen.add(box);examined+=1
            if examined>256:return regions
            w,h=right-left,bottom-top+1
            if not (10<=h<=128 and w>=max(48,h*2) and left>0 and right<width and top>0 and bottom+1<height):continue
            if w*h>min(1000000,width*height//3) or area+w*h>min(2000000,width*height//2):continue
            # Solid edges and contrasting space immediately outside establish
            # a local rectangle. Thin rules and irregular pictures fail here.
            edge=indices[top*width+left:top*width+right].count(color)+indices[bottom*width+left:bottom*width+right].count(color)
            outside=2*w-indices[(top-1)*width+left:(top-1)*width+right].count(color)-indices[(bottom+1)*width+left:(bottom+1)*width+right].count(color)
            if edge<1.9*w or outside<1.5*w:continue
            with image.crop(box) as crop,color_contrast(crop,image.getpixel((left,top))) as normalized,normalized.convert('L') as gray:
                histogram=gray.histogram()
            ink=sum(histogram[:128])
            if not .025<=ink/(w*h)<=.5:continue
            regions.append(box);area+=w*h
            if len(regions)>=8:return regions
    return regions


def _read_contrast_rows(engine,tesserocr,image,language,regions):
    """Supplement proven local contrast rows, preserving measured bounds."""
    from PIL import Image,ImageOps
    output=[]
    for left,top,right,bottom in regions:
        with image.crop((left,top,right,bottom)) as crop,color_contrast(crop,image.getpixel((left,top))) as normalized:
            for scale in ((1,.5) if normalized.height>=24 else (1,)):
                accepted=[]
                size=(max(1,round(normalized.width*scale)),max(1,round(normalized.height*scale)))
                sx,sy=size[0]/normalized.width,size[1]/normalized.height
                with normalized.resize(size,Image.Resampling.LANCZOS) as resized,ImageOps.expand(resized,12,'white') as bordered:
                    pixels=set_rgb_image(engine,bordered)
                    engine.SetPageSegMode(tesserocr.PSM.SINGLE_LINE)
                    engine.Recognize()
                    lines=read_lines(engine,tesserocr,language)
                for line in lines:
                    x=max(left,left+math.floor((line['x']-12)/sx));y=max(top,top+math.floor((line['y']-12)/sy))
                    right_ink=min(right,left+math.ceil((line['x']+line['w']-12)/sx))
                    bottom_ink=min(bottom,top+math.ceil((line['y']+line['h']-12)/sy))
                    if line['confidence']<70 or x>=right_ink or y>=bottom_ink:continue
                    accepted.append({**line,'x':x,'y':y,'w':right_ink-x,'h':bottom_ink-y})
                if accepted:
                    output.extend(accepted);break
    return output


class ContrastCache:
    """Exact local RGB reuse; geometry is always rebased onto the current row."""
    def __init__(self,max_bytes=16*1024*1024,max_entries=64):
        self.max_bytes=max_bytes;self.max_entries=max_entries
        self.entries=OrderedDict();self.bytes=0;self.hits=0;self.misses=0

    def get(self,key,pixels):
        entry=self.entries.get(key)
        if entry is None or entry[0]!=pixels:
            self.misses+=1;return None
        self.hits+=1;self.entries.move_to_end(key)
        return [dict(line) for line in entry[1]]

    def put(self,key,pixels,lines):
        charge=len(pixels)+1048576  # conservative bounded JSON/result allowance
        if charge>self.max_bytes:return
        previous=self.entries.pop(key,None)
        if previous:self.bytes-=previous[2]
        self.entries[key]=(pixels,[dict(line) for line in lines],charge);self.bytes+=charge
        while self.bytes>self.max_bytes or len(self.entries)>self.max_entries:
            _,entry=self.entries.popitem(last=False);self.bytes-=entry[2]


def read_contrast_rows(engine,tesserocr,image,language,regions,cache=None):
    if cache is None:return _read_contrast_rows(engine,tesserocr,image,language,regions)
    output=[]
    for box in regions:
        left,top,right,bottom=box
        with image.crop(box) as crop:pixels=crop.tobytes('raw','RGB')
        key=(language,right-left,bottom-top,hashlib.sha256(pixels).digest())
        lines=cache.get(key,pixels)
        if lines is None:
            actual=_read_contrast_rows(engine,tesserocr,image,language,[box])
            lines=[{**line,'x':line['x']-left,'y':line['y']-top} for line in actual]
            cache.put(key,pixels,lines)
        output.extend({**line,'x':line['x']+left,'y':line['y']+top} for line in lines)
    return output


def merge_frame_detections(primary, supplemental):
    """Add uncovered physical rows only; never duplicate or override a cell."""
    merged=[dict(item) for item in primary]
    for item in supplemental:
        if len(merged)>=512:break
        if (item['confidence']>=(80 if primary else 55)
                and (not primary or sum(c.isalpha() for c in item['text'])>=3)
                and not any(_overlapping(item,old) for old in merged)):
            merged.append(dict(item))
    if sum(len(item['text']) for item in merged)>64000:
        raise ValueError('OCR output exceeds limit')
    return sorted(merged,key=lambda item:(item['y'],item['x']))


def refine_pixel_line(engine, tesserocr, working, source):
    """Refine text within one discovered cell, never infer or change coordinates."""
    from PIL import Image, ImageFilter, ImageOps
    item=dict(source)
    x,y,w,h=(item[k] for k in ('x','y','w','h'))
    box=(max(0,x-4),max(0,y-4),min(working.width,x+w+4),min(working.height,y+h+4))
    with working.crop(box) as original:
        crop=original.filter(ImageFilter.GaussianBlur(.6))
    try:
        original_conf=item['confidence']
        for sx,sy in ((.5,.5),(.6,.85)):
            candidate=crop.resize((max(1,round(crop.width*sx)),max(1,round(crop.height*sy))),Image.Resampling.LANCZOS)
            bordered=ImageOps.expand(candidate,12,'white')
            candidate.close()
            try:
                pixels=set_rgb_image(engine,bordered)
                engine.SetPageSegMode(tesserocr.PSM.SINGLE_LINE)
                engine.Recognize()
                text=engine.GetUTF8Text().strip()
                confidence=float(engine.MeanTextConf())
            finally:
                bordered.close()
            required=original_conf-5 if sx==.5 else original_conf+5
            if text and '\n' not in text and len(text)<=16000 and confidence>=max(55,required):
                item['text']=text
                item['confidence']=confidence
                break
    finally:
        crop.close()
    return item


class RegionalRefiner:
    """Bounded persistent workers, one private Tesseract engine per worker.

    The caller completes whole-frame discovery before submitting any region.
    No engine or iterator is concurrently touched by multiple threads.
    """
    def __init__(self,tesserocr,workers=2):
        if type(workers) is not int or not 1<=workers<=8:
            raise ValueError('Invalid refinement worker count')
        self.tesserocr=tesserocr
        self.workers=workers
        self._pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='ocr-cell')
        self._local=threading.local()
        self._engines=[]
        self._lock=threading.Lock()
        # Only text/confidence are reused. Geometry always comes from the
        # current complete-frame detection, never from a previous position.
        self._cache=OrderedDict()
        self.cache_hits=0
        self.cache_misses=0

    def _read_one(self,job):
        working,source,language=job
        cached=getattr(self._local,'engine',None)
        if cached is None or cached[0]!=language:
            if cached is not None:
                self._local.engine=None
                with self._lock:self._engines.remove(cached[1])
                cached[1].End()
            engine=self.tesserocr.PyTessBaseAPI(path='.',lang=language,
                psm=self.tesserocr.PSM.SINGLE_LINE,oem=self.tesserocr.OEM.LSTM_ONLY)
            self._local.engine=(language,engine)
            with self._lock:self._engines.append(engine)
        return refine_pixel_line(self._local.engine[1],self.tesserocr,working,source)

    def _one(self,job):
        try:
            return self._read_one(job)
        except Exception:
            # One bad crop/model retry cannot erase the full-frame evidence.
            return {**job[1],'_refine_failed':True}

    def refine(self,working,lines,language):
        # The aggregate crop budget prevents overlapping detections from
        # multiplying a frame into an unbounded amount of image processing.
        jobs=[];indices=[];keys=[];budget=0
        output=[dict(item) for item in lines]
        for index,item in enumerate(lines[:64]):
            if item['confidence']>=94 or not 16<=item['h']<=100 or len(item['text'])<3:
                continue
            cost=(item['w']+8)*(item['h']+8)
            if budget+cost>2000000:continue
            budget+=cost
            x,y,w,h=(item[k] for k in ('x','y','w','h'))
            box=(max(0,x-4),max(0,y-4),min(working.width,x+w+4),min(working.height,y+h+4))
            with working.crop(box) as crop:
                key=(language,item['text'],item['confidence'],crop.size,
                     hashlib.sha256(crop.tobytes()).digest())
            if key in self._cache:
                self.cache_hits+=1
                output[index].update(self._cache[key]);self._cache.move_to_end(key)
                continue
            self.cache_misses+=1
            keys.append(key);indices.append(index);jobs.append((working,item,language))
        # map preserves source order even when workers complete out of order.
        for index,key,item in zip(indices,keys,self._pool.map(self._one,jobs)):
            failed=item.pop('_refine_failed',False)
            output[index]=item
            if failed:continue
            self._cache[key]={'text':item['text'],'confidence':item['confidence']}
            self._cache.move_to_end(key)
            while len(self._cache)>256:self._cache.popitem(last=False)
        return output

    def close(self):
        self._pool.shutdown(wait=True,cancel_futures=True)
        for engine in self._engines:engine.End()
        self._engines.clear()
        self._cache.clear()


class ParallelDiscovery:
    """One persistent, isolated engine for the supplemental whole-frame pass.

    The primary engine stays on the caller thread. Both scans read the same
    immutable RGB buffer. Results merge in primary/supplemental order, never
    completion order. No separate unknown tiles or shared engine state.
    """
    def __init__(self,tesserocr):
        self.tesserocr=tesserocr
        self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='ocr-whole-frame')
        self._engine=None;self._language=None

    def _read(self,working,language):
        if self._engine is None or self._language!=language:
            if self._engine is not None:self._engine.End();self._engine=None
            self._engine=self.tesserocr.PyTessBaseAPI(path='.',lang=language,
                psm=self.tesserocr.PSM.SPARSE_TEXT,oem=self.tesserocr.OEM.LSTM_ONLY)
            self._language=language
        pixels=set_rgb_image(self._engine,working)
        self._engine.Recognize()
        return read_lines(self._engine,self.tesserocr,language)

    def submit(self,working,language):return self._pool.submit(self._read,working,language)

    def close(self):
        self._pool.shutdown(wait=True,cancel_futures=True)
        if self._engine is not None:self._engine.End();self._engine=None


def recognize(engine, tesserocr, image, language, mode='standard', refiner=None, discovery=None, contrast_cache=None, vision_anchors=None, japanese_panel_engine=None):
    """Whole-frame discovery, measured cell decomposition, then parallel read."""
    from PIL import Image, ImageOps, ImageStat
    working = image
    if mode == 'pixel':
        working=flat_color_frame(image)
        if working is image and ImageStat.Stat(image.resize((32,32),Image.Resampling.NEAREST).convert('L')).median[0] < 128:
            working=ImageOps.invert(image)
    supplemental=None
    try:
        if mode=='pixel' and discovery is not None:
            supplemental=discovery.submit(working,language)
        pixels=set_rgb_image(engine,working)
        engine.SetPageSegMode(tesserocr.PSM.AUTO)
        engine.Recognize()
        lines=read_lines(engine,tesserocr,language)
        if supplemental is not None:
            lines=merge_frame_detections(lines,supplemental.result())
        elif not lines or mode=='pixel':
            engine.SetPageSegMode(tesserocr.PSM.SPARSE_TEXT)
            engine.Recognize()
            lines=merge_frame_detections(lines,read_lines(engine,tesserocr,language))
        # All discovery passes inspect the complete same immutable frame.
        # Refinement never partitions an unknown frame into independent tiles.
        if mode=='pixel' and language=='eng':
            if refiner is not None:
                lines=refiner.refine(working,lines,language)
            else:
                budget=0
                for index,item in enumerate(lines[:64]):
                    if item['confidence']>=94 or not 16<=item['h']<=100 or len(item['text'])<3:continue
                    cost=(item['w']+8)*(item['h']+8)
                    if budget+cost>2000000:continue
                    budget+=cost
                    lines[index]=refine_pixel_line(engine,tesserocr,working,item)
        if mode=='pixel':
            for item in read_contrast_rows(engine,tesserocr,image,language,find_contrast_rows(image),contrast_cache):
                # A high-contrast selected value can be numeric. It still has
                # measured word bounds; no invented span or dictionary repair.
                if len(lines)<512 and not any(_overlapping(item,old) for old in lines):lines.append(item)
            if sum(len(item['text']) for item in lines)>64000:
                raise ValueError('OCR output exceeds limit')
            lines.sort(key=lambda item:(item['y'],item['x']))
        # Whole-frame discovery remains first. A second, evidence-bounded pass
        # recovers small text on actual flat panels in both standard and pixel
        # modes; local polarity does not affect neighboring text surfaces.
        panels=find_text_surfaces(image,single_rows=language.startswith('jpn'))
        surface=read_text_surfaces(japanese_panel_engine or engine,tesserocr,image,
                                   'jpn' if japanese_panel_engine else language,panels,contrast_cache)
        if vision_anchors is not None:
            seen=set()
            for row in sorted(surface,key=lambda r:-r['confidence']):
                # This path measures small-text surfaces. A tall rectangle
                # spanning a button's border/fill is not a proven glyph row;
                # leave it to ordinary OCR instead of authorizing AI coverage.
                if row['h']>24:continue
                key=tuple(row[k] for k in ('x','y','w','h'))
                duplicate=any(abs(row['y']-old['y'])<=2 and abs(row['h']-old['h'])<=3
                    and abs(row['x']-old['x'])<=3 and abs(row['w']-old['w'])<=6 for old in vision_anchors)
                if key not in seen and not duplicate and len(vision_anchors)<128:
                    vision_anchors.append(dict(row));seen.add(key)
        lines=merge_surface_detections(lines,surface)
        return lines
    finally:
        # Wait even on primary failure: the supplemental task still owns the
        # image until it completes. Closing the PIL frame early is unsafe.
        if supplemental is not None:
            try:supplemental.result()
            except Exception:pass
        if working is not image:working.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path)
    parser.add_argument("--tessdata", required=True, type=Path)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--refine-workers", type=int, choices=range(1,9), default=2)
    args = parser.parse_args()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    # Resolve every CLI path against the launch directory before changing cwd.
    # Tesseract's Windows model loader uses narrow filenames and cannot reliably
    # open an absolute Unicode tessdata path. Python changes cwd with wide APIs;
    # then Tesseract only sees ASCII '.', 'jpn.traineddata', 'eng.traineddata'.
    launch_directory = Path.cwd()
    try:
        if args.packages:
            args.packages = args.packages.resolve()
            sys.path.insert(0, str(args.packages))
        # Best-effort resolution also supports restricted Windows environments
        # that permit directory access but deny final-path handle inspection.
        # is_dir below still requires that each working directory exists.
        args.tessdata = args.tessdata.resolve()
        args.input_root = args.input_root.resolve()
        if not args.tessdata.is_dir() or not args.input_root.is_dir():
            raise ValueError('Invalid OCR working directory')
    except (OSError, ValueError):
        print(json.dumps({'error':'OCR working directories are unavailable'}),flush=True)
        return 2
    engines = {}
    try:
        import tesserocr
    except ImportError:
        print(json.dumps({"error": "Portable tesserocr is not installed; install its official Windows x64 wheel into vendor/ocr."}))
        return 2
    try:
        os.chdir(args.tessdata)
    except OSError:
        print(json.dumps({'error':'OCR working directories are unavailable'}),flush=True)
        return 2
    refiner=RegionalRefiner(tesserocr,args.refine_workers)
    contrast_cache=ContrastCache()
    discovery=ParallelDiscovery(tesserocr)
    try:
        while True:
            raw=sys.stdin.readline(MAX_REQUEST_CHARS+1)
            if not raw:break
            if len(raw)>MAX_REQUEST_CHARS or not raw.endswith('\n'):
                print(json.dumps({'error':'Invalid OCR request'}),flush=True)
                break
            try:
                request = json.loads(raw)
                if not isinstance(request,dict) or not set(request)<= {'image_path','language','mode','quit'}:
                    raise ValueError('Invalid OCR request')
                if request=={'quit':True}:
                    break
                if 'quit' in request:raise ValueError('Invalid OCR request')
                language = request.get("language", "jpn+eng")
                if language not in {"jpn", "eng", "jpn+eng", "chi_sim", "chi_sim+eng"}:
                    raise ValueError("Unsupported OCR language")
                mode=request.get('mode','standard')
                if mode not in {'standard','pixel','line'}:
                    raise ValueError('Unsupported OCR mode')
                if language not in engines:
                    engines[language] = tesserocr.PyTessBaseAPI(path='.',
                        lang=language, psm=tesserocr.PSM.AUTO, oem=tesserocr.OEM.LSTM_ONLY)
                engine = engines[language]
                start = time.perf_counter()
                image_path=request['image_path']
                if isinstance(image_path,str) and not Path(image_path).is_absolute():
                    image_path=str(launch_directory/image_path)
                with load_image(image_path,args.input_root) as image:
                    # tesserocr.SetImage(PIL) internally uses pixReadMem. The raw
                    # RGB API avoids all Leptonica file/format decoders instead.
                    anchors=[]
                    if language=='jpn+eng' and 'jpn' not in engines:
                        engines['jpn']=tesserocr.PyTessBaseAPI(path='.',lang='jpn',oem=tesserocr.OEM.LSTM_ONLY)
                    if mode=='line':
                        pixels=image.tobytes()
                        key=('warm-row-v1',language,image.size,hashlib.sha256(pixels).digest())
                        lines=contrast_cache.get(key,pixels)
                        if lines is None:
                            retained=set_rgb_image(engine,image)
                            engine.SetPageSegMode(tesserocr.PSM.SINGLE_LINE)
                            engine.Recognize()
                            lines=read_lines(engine,tesserocr,language)
                            contrast_cache.put(key,pixels,lines)
                    else:
                        lines=recognize(engine,tesserocr,image,language,mode,refiner,discovery,contrast_cache,anchors,
                                        engines.get('jpn') if language=='jpn+eng' else None)
                response = {"lines":lines,"vision_anchors":anchors,"ocr_ms":(time.perf_counter()-start)*1000}
            except Exception:
                response = {"error": "OCR input or recognition failed"}
            encoded=json.dumps(response, ensure_ascii=False,allow_nan=False)
            if len(encoded.encode('utf-8'))>MAX_RESPONSE_BYTES:
                encoded=json.dumps({'error':'OCR output exceeds limit'})
            print(encoded, flush=True)
    finally:
        discovery.close()
        refiner.close()
        for engine in engines.values():
            engine.End()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
