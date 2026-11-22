"""SPDX-License-Identifier: MIT
Native Windows OCR with an optional independent image OCR utility fallback.
The main process never loads Tesseract/tesserocr libraries.
"""
from __future__ import annotations

import json
from contextlib import ExitStack
import math
import os
import re
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

from .native import NativeCore
from .ocr_regions import RegionRefiner, action_label_layout, retain_action_labels, unchanged_action_box, warm_ink_mask, warm_text_boxes
from .palette_rows import PaletteReview, merge_readings
from .frame_cache import FrameCache
from .tuning import DEFAULT_SCENE_CHANGE_SENSITIVITY, DEFAULT_TRANSLATION_HOLD_MS

MAX_RESPONSE_CHARS=1048576


def changed_source_indices(before, after, lines, *, sensitivity=50):
    """Bounded glyph-pixel freshness check, not an OCR/optical-flow substitute.

    Compare only old/new foreground-colored pixels inside source boxes. Motion
    outside text (background video, clocks elsewhere) must not blank dialogue.
    """
    from PIL import Image,ImageChops
    if before.size!=after.size:return set(range(len(lines)))
    changed=set();pixel_budget=16*1024*1024
    mismatch_ratio = .10 - .0009*sensitivity
    pixel_scale = 1.3 - .006*sensitivity
    for index,line in enumerate(lines[:512]):
        if line.get('_center_label'):
            if '_aoi_button' in line:
                from .aoi_menu import read_button
                rect = tuple(line[k] for k in ('x','y','w','h'))
                if read_button(after, rect, line['_aoi_button']) is not None:
                    continue
            if not unchanged_action_box(before, after, line):
                changed.add(index)
            continue
        x,y,w,h=(int(line[k]) for k in ('x','y','w','h'))
        box=(max(0,x),max(0,y),min(before.width,x+w),min(before.height,y+h))
        if box[2]<=box[0] or box[3]<=box[1]:changed.add(index);continue
        pixel_budget-=(box[2]-box[0])*(box[3]-box[1])
        if pixel_budget<0:changed.add(index);continue
        a,b=before.crop(box).convert('RGB'),after.crop(box).convert('RGB')
        fg=tuple(line.get('fg',(255,255,255)))[:3];bg=tuple(line.get('bg',(0,0,0)))[:3]
        contrast=max(abs(f-bg) for f,bg in zip(fg,bg));tolerance=max(12,min(64,contrast*.25))
        def maximum(image):
            r,g,b=image.split();return ImageChops.lighter(ImageChops.lighter(r,g),b)
        color=Image.new('RGB',a.size,fg)
        old_mask=maximum(ImageChops.difference(a,color)).point(lambda value:255 if value<=tolerance else 0)
        new_mask=maximum(ImageChops.difference(b,color)).point(lambda value:255 if value<=tolerance else 0)
        ink=ImageChops.lighter(old_mask,new_mask)
        count=ink.histogram()[255]
        pixel_threshold = max(12,min(40,contrast*.18))*pixel_scale
        difference=maximum(ImageChops.difference(a,b)).point(lambda value:255 if value>pixel_threshold else 0)
        mismatches=ImageChops.multiply(difference,ink).histogram()[255] if count else difference.histogram()[255]
        if mismatches>=max(4,count*mismatch_ratio):changed.add(index)
        a.close();b.close();color.close();old_mask.close();new_mask.close();ink.close();difference.close()
    return changed


def validate_response(response,width,height):
    """Validate the independent helper's untrusted IPC result before rendering."""
    if not isinstance(response,dict) or 'error' in response:
        raise RuntimeError('Portable OCR helper failed')
    lines=response.get('lines');elapsed=response.get('ocr_ms')
    if not isinstance(lines,list) or len(lines)>512 or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=120000:
        raise RuntimeError('Invalid OCR response')
    anchors=response.get('vision_anchors',[])
    if not isinstance(anchors,list) or len(anchors)>128:
        raise RuntimeError('Invalid OCR anchors')
    total=0
    for line in [*lines,*anchors]:
        if not isinstance(line,dict):raise RuntimeError('Invalid OCR response')
        text=line.get('text')
        if not isinstance(text,str) or len(text)>16000 or '\x00' in text or any(0xd800<=ord(c)<=0xdfff for c in text):
            raise RuntimeError('Invalid OCR text')
        total+=len(text)
        if total>64000:raise RuntimeError('OCR output exceeds limit')
        for key in ('x','y','w','h'):
            if type(line.get(key)) is not int:raise RuntimeError('Invalid OCR bounds')
        if not (0<=line['x']<line['x']+line['w']<=width and 0<=line['y']<line['y']+line['h']<=height):
            raise RuntimeError('Invalid OCR bounds')
        confidence=line.get('confidence')
        if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=100:
            raise RuntimeError('Invalid OCR confidence')
        if 'separated_cell' in line and type(line['separated_cell']) is not bool:
            raise RuntimeError('Invalid OCR cell boundary')
    return response


class PortableOcr:
    def __init__(self, root: Path, refine_workers=2):
        if type(refine_workers) is not int or not 1<=refine_workers<=8:
            raise ValueError("Invalid OCR refinement workers")
        self.refine_workers=refine_workers
        self.root = root
        self.packages = root / "vendor" / "ocr"
        self.tessdata = root / "models" / "tessdata"
        self._process = None
        self._responses = queue.Queue(maxsize=2)
        self._lock = threading.RLock()
        self._temp = None

    def available(self):
        wheel_installed = (self.packages / "tesserocr").is_dir() or any(self.packages.glob("tesserocr*.pyd"))
        return (wheel_installed or self._helper_exe().is_file()) and all((self.tessdata / f"{lang}.traineddata").is_file() for lang in ("jpn", "eng"))

    def _helper_exe(self):
        return self.root / "tools" / "ocr_helper" / "ocr_helper.exe"

    def _start(self):
        if self._process and self._process.poll() is None:
            return
        if self._process or self._temp:self.close()
        if not self.available():
            raise RuntimeError("\u65e5\u8bed OCR \u4e0d\u53ef\u7528\uff1a\u7cfb\u7edf\u672a\u5b89\u88c5\u65e5\u8bed OCR\uff0c\u9879\u76ee\u5185\u4e5f\u7f3a\u5c11\u4fbf\u643a\u5f15\u64ce\u3002\u9700\u8981 vendor/ocr \u7684\u5b98\u65b9 tesserocr Windows x64 wheel\uff0c\u4ee5\u53ca models/tessdata \u4e0b\u7684 jpn.traineddata \u548c eng.traineddata\uff1b\u4e0d\u4f1a\u81ea\u52a8\u5f39\u7a97\u6216\u5b89\u88c5\u7cfb\u7edf\u7ec4\u4ef6\u3002")
        helper_exe = self._helper_exe()
        python = Path(sys.executable)
        if helper_exe.is_file():
            command = [str(helper_exe)]
        elif getattr(sys, "frozen", False):
            # A frozen GUI cannot execute an arbitrary Python utility as itself.
            candidate = self.root / "runtime" / "python.exe"
            if not candidate.is_file():
                raise RuntimeError("Portable OCR helper requires tools/ocr_helper/ocr_helper.exe or runtime/python.exe in this packaged build.")
            python = candidate
            command = [str(python), "-I", "-u", str(self.root / "tools" / "ocr_helper.py")]
        else:
            command = [str(python), "-I", "-u", str(self.root / "tools" / "ocr_helper.py")]
        data_dir = self.root / "data"
        data_dir.mkdir(exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix="ocr-", dir=data_dir)
        command += ["--packages", str(self.packages), "--tessdata", str(self.tessdata),"--input-root",self._temp.name,"--refine-workers",str(self.refine_workers)]
        environment = dict(os.environ)
        environment["OMP_THREAD_LIMIT"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        for name in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP'):environment.pop(name,None)
        try:
            self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0), env=environment,
                cwd=str(self.root))
        except OSError:
            self._temp.cleanup();self._temp=None
            raise RuntimeError('Portable OCR helper could not start') from None
        self._responses = queue.Queue(maxsize=2)
        process, responses = self._process, self._responses
        def read_responses():
            try:
                while True:
                    line=process.stdout.readline(MAX_RESPONSE_CHARS+1)
                    if not line:break
                    if len(line)>MAX_RESPONSE_CHARS or not line.endswith('\n'):
                        raise ValueError('OCR response exceeds limit')
                    responses.put(json.loads(line), timeout=1)
            except Exception:
                pass
            finally:
                try: responses.put_nowait({"error":"Portable OCR helper exited"})
                except queue.Full: pass
        threading.Thread(target=read_responses, daemon=True, name="ocr-helper-output").start()

    def recognize(self, image, language='jpn+eng', mode='standard'):
        with self._lock:
            if (not isinstance(language,str) or language not in {'jpn','eng','jpn+eng','chi_sim','chi_sim+eng'}
                    or not isinstance(mode,str) or mode not in {'standard','pixel','line'}):
                raise ValueError('Invalid portable OCR language or mode')
            if not (1<=image.width<=4096 and 1<=image.height<=4096):
                raise ValueError('OCR image must be between 1 and 4096 pixels per dimension')
            self._start()
            path = Path(self._temp.name) / "frame.bmp"
            image.convert('RGB').save(path, format="BMP")
            request = json.dumps({"image_path":str(path),"language":language,"mode":mode}) + "\n"
            try:
                self._process.stdin.write(request)
                self._process.stdin.flush()
                response = self._responses.get(timeout=20)
            except (OSError, queue.Empty) as exc:
                self.close()
                raise RuntimeError("Portable OCR helper failed or timed out") from exc
            try:
                return validate_response(response,image.width,image.height)
            except RuntimeError:
                self.close()
                raise

    def close(self):
        with self._lock:
            if self._process:
                process, self._process = self._process, None
                if process.poll() is None:
                    try:
                        process.stdin.write('{"quit":true}\n'); process.stdin.flush()
                        process.wait(timeout=1)
                    except (OSError, subprocess.TimeoutExpired):
                        process.kill(); process.wait(timeout=2)
                for stream in (process.stdin, process.stdout):
                    if stream: stream.close()
            if self._temp:
                self._temp.cleanup(); self._temp = None


def filter_portable_lines(lines, min_confidence=55):
    """Reject weak image detections before translation; preserve raw evidence."""
    threshold = float(min_confidence)
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("OCR confidence threshold must be between 0 and 100")
    accepted, rejected = [], []
    for source in lines:
        item = dict(source)
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            confidence = 0.0
        item["confidence"] = max(0.0, min(100.0, confidence))
        if item["confidence"] < threshold:
            item["rejected_reason"] = "below_confidence_threshold"
            rejected.append(item)
        else:
            accepted.append(item)
    return accepted, rejected


def looks_like_pixel_frame(image):
    """Bounded routing hint: monochrome ink or a flat-palette colored HUD.

    This is an image hint, not a language/text classifier. Native mode remains
    available when a monochrome non-pixel application happens to match it.
    """
    from PIL import Image
    sample=image.resize((128,128),Image.Resampling.NEAREST).convert('RGB')
    colors=sample.getcolors(16384)
    if not colors:
        return False
    dark=sum(count for count,color in colors if max(color)<40)
    light=sum(count for count,color in colors if min(color)>215)
    monochrome=len(colors)<=160 and dark>=16384*.35 and light>=16384*.015 and dark+light>=16384*.75
    # Decorative blue/colored cockpit borders can occupy a third of a classic
    # game's frame. Require stronger palette concentration and a dark majority
    # instead of treating those frames as smooth-font Windows UI by default.
    colored_hud=(len(colors)<=96 and dark>=16384*.50 and light>=16384*.01
                 and sum(sorted((count for count,_ in colors),reverse=True)[:16])>=16384*.94)
    count,background=max(colors,key=lambda item:item[0])
    chromatic_ink=sum(n for n,c in colors if max(abs(c[k]-background[k]) for k in range(3))>=48
                      and (max(c)-min(c)>=32 or max(background)-min(background)>=32))
    flat_color=(count>=16384*.80 and chromatic_ink>=16384*.01)
    return monochrome or colored_hud or flat_color


def place_image_result(result, x, y):
    """Copy image-relative OCR output to screen coordinates; never rewrite text."""
    output=dict(result)
    for field in ('lines','vision_anchors'):
        if field not in result:continue
        placed=[]
        for source in result[field]:
            line={**source,'x':source['x']+x,'y':source['y']+y}
            if '_source_ink' in source:
                ix,iy,iw,ih=source['_source_ink']
                line['_source_ink']=[ix+x,iy+y,iw,ih]
            placed.append(line)
        output[field]=placed
    return output


def _row_background(image, ink, padded):
    """Sample beside this row, never the selected menu item immediately above.

    Small unoccupied side margins preserve inverse selection colors even in
    densely stacked tables. At an image boundary use the bounded row histogram.
    """
    x,y,w,h=ink;left,top,right,bottom=padded
    strips=[]
    if left<x:strips.append((left,y,x,y+h))
    if x+w<right:strips.append((x+w,y,right,y+h))
    if not strips:strips.append((left,top,right,bottom))
    histogram={}
    for box in strips:
        with image.crop(box) as strip:
            for count,color in strip.getcolors(strip.width*strip.height) or ():
                histogram[color]=histogram.get(color,0)+count
    return list(max(histogram,key=histogram.get)) if histogram else [25,25,25]


class OcrCore:
    """Drop-in NativeCore API, with Japanese fallback when its optional files exist."""
    def __init__(self, dll_path=None, min_confidence=55, mode='auto', refine_workers=2,
                 cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None):
        filter_portable_lines([], min_confidence)
        if not isinstance(mode,str) or mode not in {'auto','native','pixel'}:
            raise ValueError('Invalid OCR mode')
        if type(refine_workers) is not int or not 1<=refine_workers<=8:
            raise ValueError("Invalid OCR refinement workers")
        if type(cuda_enabled) is not bool or type(cuda_memory_mb) is not int or not 256<=cuda_memory_mb<=16384:
            raise ValueError('Invalid CUDA OCR settings')
        if type(cuda_quality) is not int or not 0<=cuda_quality<=100:
            raise ValueError('Invalid CUDA OCR quality')
        self.refine_workers=refine_workers
        self.mode=mode
        self.min_confidence = float(min_confidence)
        self.native = NativeCore(dll_path)
        root = Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]
        self.portable = PortableOcr(root,refine_workers=refine_workers)
        self._page_reader = PortableOcr(root,refine_workers=1)
        self._palette=PaletteReview(PortableOcr(root,refine_workers=1))
        self.cuda=None
        self._cuda_failed=False
        self._cuda_retry_at=0.
        self.cuda_status='disabled'
        if cuda_enabled:
            from .cuda_ocr import CudaOcr
            self.cuda=cuda_instance if cuda_instance is not None else CudaOcr(root,memory_mb=cuda_memory_mb,quality=cuda_quality)
            # A failed startup probe is not proof that the next frame cannot
            # run on CUDA, for example after another game releases its VRAM.
            self.cuda_status='ready' if self.cuda.available() else 'not_installed'
        self._regions=RegionRefiner(refine_workers)
        self._lock = threading.RLock()
        self._native_languages = self.native.languages()
        self._capture_language = None
        self._frames=FrameCache()
        self._capture_regions = None
        self._style_matcher = None
        self._source_callback = None
        self._source_reference = None
        self._live = None
        self._attention_core = None

    def enable_live_capture(self, review_plan=None, *, frame_review=None, cursor_attention=False, supersample=False,
                            scene_change_sensitivity=DEFAULT_SCENE_CHANGE_SENSITIVITY,
                            translation_hold_ms=DEFAULT_TRANSLATION_HOLD_MS):
        from .live_capture import LiveCapture
        if self._live is None:
            self._live = LiveCapture(self)
        self._live.review_plan = review_plan
        self._live.frame_review = frame_review
        self._live.ocr_interval = .05 if supersample else .13
        self._live.scene_change_sensitivity = scene_change_sensitivity
        self._live.set_fade_hold(translation_hold_ms / 1000)
        from .pointer_attention import cursor_position
        self._live.pointer_provider = cursor_position if cursor_attention else None

    def recognize_attention(self,image,language):
        # Separate local engine, lock, worker and frame cache. The crop lane
        # neither re-enters the fullscreen OCR session nor competes for VRAM.
        if self._attention_core is None:
            self._attention_core=OcrCore(mode=self.mode, min_confidence=self.min_confidence,
                                         refine_workers=1, cuda_enabled=False)
        self._attention_core._aoi=getattr(self,'_aoi',False)
        return self._attention_core.recognize_image(image,language)

    def set_ready_callback(self,callback):
        if getattr(self,'_live',None) is not None:
            self._live.ready_callback=callback

    @property
    def recognition_pending(self):
        return bool(self._live and self._live.pending)

    def cancel_pending(self):
        if self._live is not None:
            self._live.reset()

    def set_auto_font_style(self, enabled, target='zh-Hans'):
        from .font_style import SourceStyleMatcher
        with self._lock:
            self.native.set_auto_font_style(enabled,target)
            self._style_matcher=SourceStyleMatcher() if enabled else None

    def set_capture_regions(self, regions):
        from .selection_regions import capture_plan
        plan = capture_plan(regions)
        # These are already relative to the bounding capture, not screen points.
        checked = tuple(tuple(r) for r in regions) if plan else None
        with self._lock:
            if checked != self._capture_regions:
                self._capture_regions = checked
                self.reset()

    def prepare_capture_image(self, image):
        from .selection_regions import mask_regions
        return mask_regions(image, self._capture_regions)

    def languages(self):
        langs = list(self._native_languages)
        if self.mode=='auto' and self.cuda is not None and self.cuda.available():
            for tag in ('ja-JP','en-US','zh-Hans'):
                if not any(lang.lower().startswith(tag.split('-')[0]) for lang in langs):langs.append(tag)
        if self.mode!='native' and self.portable.available() and not any(lang.startswith("ja") for lang in langs):
            langs.append("ja-JP")
        if self.mode!='native' and self.portable.available() and not any(lang.startswith("en") for lang in langs):
            langs.append("en-US")
        return langs

    def capture_ocr(self,x,y,w,h,language="en"):
        live = getattr(self,'_live',None)
        if live is not None:
            return live.capture(x,y,w,h,language)
        with self._lock:
            if not isinstance(language,str) or len(language)>64 or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language):
                raise ValueError('Invalid OCR language')
            if self._capture_language != language:
                self.reset()
                self._capture_language=language
            captured = self.native.capture_bgra(x,y,w,h)
            if captured.get('pending'):
                return {**captured,'lines':[],'ocr_ms':0}
            if not captured["changed"]:
                return {"changed":False,"lines":[],"capture_ms":captured["capture_ms"],"ocr_ms":0}
            from PIL import Image
            image = Image.frombytes("RGB",(w,h),captured["bgra"],"raw","BGRX")
            try:
                self.notify_source_frame(image,x,y)
                response = self.recognize_image(image,language)
                response = self.retain_action_labels(image, response)
                response = self.verify_source_result(image,response,x,y)
            except Exception:
                self.native.reset()
                raise
            finally:
                image.close()
            return {**place_image_result(response,x,y),'changed':True,'capture_ms':captured['capture_ms']}

    def set_source_change_callback(self, callback):
        """Install/detach without taking the model lock; callers never capture."""
        self._source_callback=callback

    def _notify_boxes(self,lines,indices,origin):
        callback=self._source_callback
        if callback is not None and indices:
            callback([{'x':lines[i]['x']+origin[0],'y':lines[i]['y']+origin[1],
                       'w':lines[i]['w'],'h':lines[i]['h']} for i in sorted(indices)])

    def notify_source_frame(self,image,x,y):
        reference=self._source_reference
        if self._source_callback is None or reference is None:return
        before,lines,origin=reference
        changed=changed_source_indices(before,image,lines)
        self._notify_boxes(lines,changed,origin)

    def retain_action_labels(self, image, result):
        reference = self._source_reference
        if reference is None or not any(line.get('_center_label') for line in reference[1]):
            return result
        before, previous, _ = reference
        return {**result, 'lines': retain_action_labels(before, image, previous, result['lines'])}

    def verify_source_result(self,image,result,x,y):
        """Do not publish OCR coordinates whose source moved during recognition."""
        if self._source_callback is None:return result
        lines=result.get('lines',[])[:512]
        rejected=set()
        if lines:
            captured=self.native.capture_bgra(x,y,image.width,image.height)
            if captured.get('pending'):
                rejected=set(range(len(lines)))
            elif captured.get('changed'):
                from PIL import Image
                with Image.frombytes('RGB',image.size,captured['bgra'],'raw','BGRX') as after:
                    self.notify_source_frame(after,x,y)
                    rejected=changed_source_indices(image,after,lines)
        if rejected:
            self._notify_boxes(lines,rejected,(x,y))
            self.native.reset()
        accepted=[dict(line) for i,line in enumerate(lines) if i not in rejected]
        if self._source_reference is not None:self._source_reference[0].close()
        self._source_reference=(image.copy(),accepted,(x,y)) if accepted else None
        return {**result,'lines':accepted,'source_stale':bool(rejected),'freshness_checked':True}

    def recognize_image(self,image,language='en',mode=None):
        with self._lock:
            began=time.perf_counter()
            selected=self.mode if mode is None else mode
            if selected not in ('auto','native','pixel') or not isinstance(language,str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language):
                raise ValueError('Invalid OCR mode or language')
            if not (1<=image.width<=4096 and 1<=image.height<=4096):raise ValueError('Invalid OCR image dimensions')
            with self.prepare_capture_image(image) as rgb, ExitStack() as managed:
                aoi=getattr(self,'_aoi',False)
                if aoi and not getattr(self,'_live',None) and language.split('-')[0].lower()=='ja':
                    from .aoi_dialogue import erase_advance_markers
                    cleaned = erase_advance_markers(rgb)
                    if cleaned is not rgb:
                        rgb = managed.enter_context(cleaned)
                pixels=rgb.tobytes()
                key=self._frames.key(pixels,(rgb.size,language,selected,getattr(self,"_windose",False),aoi,self.min_confidence,self._capture_regions,self._style_matcher is not None))
                cached=self._frames.get(key,pixels)
                if cached is not None:
                    cached.update(ocr_ms=(time.perf_counter()-began)*1000,region_refine_ms=0,frame_cache_hit=True)
                    return cached
                review = (self._palette.submit(rgb,self.min_confidence)
                          if selected=='auto' and language.split('-')[0].lower()=='ja' else None)
                try:
                    result=self._recognize_image_uncached(rgb,language,selected)
                finally:
                    # Both paths borrow rgb until their work is complete.
                    extra=review.result() if review is not None else []
                result['cuda_status']=self.cuda_status
                self._read_warm_rows(rgb, language, result)
                if extra:
                    result["lines"]=merge_readings(result["lines"],extra)
                if getattr(self,'_windose',False) and language.split('-')[0].lower()=='ja':
                    from .windose_warning import recover
                    result['lines']=recover(rgb,result['lines'])
                from .selection_regions import scope_lines
                if aoi and language.split('-')[0].lower()=='ja':
                    from .aoi_dialogue import recover, repair_ocr_rows
                    from .aoi_menu import title_buttons, with_buttons
                    buttons=title_buttons(rgb)
                    if len(buttons)<5:
                        main_rows=repair_ocr_rows(rgb,result['lines'])
                        result['lines']=recover(rgb,main_rows,self.portable,self.min_confidence)
                    result['lines']=with_buttons(result['lines'],buttons)
                if aoi and language.split('-')[0].lower() in ('ja','en'):
                    from .aoi_menu import with_buttons
                    from .aoi_toolbar import toolbar_buttons
                    result['lines']=with_buttons(result['lines'],toolbar_buttons(rgb))
                result['lines'] = action_label_layout(
                    rgb, scope_lines(result['lines'], self._capture_regions), self._capture_regions)
                from .ocr_regions import source_ink_color
                for row in result['lines']:
                    fg=row.get('fg');bg=row.get('bg')
                    if fg and bg and max(fg)-min(fg)<12 and not row.get('_subtitle_read') and '_aoi_button' not in row:
                        bounds=row.get('_source_ink') or tuple(row[k] for k in ('x','y','w','h'))
                        measured=source_ink_color(rgb,bounds,bg)
                        if measured and max(measured)-min(measured)>28:row['fg']=measured
                if 'vision_anchors' in result:
                    result['vision_anchors'] = scope_lines(result['vision_anchors'], self._capture_regions)
                if self._style_matcher is not None:
                    for line in result['lines']:
                        if '_aoi_button' not in line:
                            line['_source_font_style']=self._style_matcher.classify(rgb,line)
                result['ocr_ms']=(time.perf_counter()-began)*1000
                self._frames.put(key,pixels,result)
                result['frame_cache_hit']=False
                return result

    def _read_warm_rows(self, image, language, result):
        """Run a small independent black-on-white OCR pass for weak warm rows."""
        from PIL import Image, ImageOps
        group=language.split('-')[0].lower()
        if group not in ('ja','en'):
            return
        lines=result['lines']
        with warm_ink_mask(image) as mask:
            candidates=warm_text_boxes(image,mask)
            # A nearby portrait can touch a warning's horizontal projection.
            # The primary OCR's existing warm box is also an independent ROI.
            for line in lines:
                fg=line.get('fg',(0,0,0))
                if fg[0]-fg[1]<32 or fg[2]-fg[0]>35 or line.get('confidence',0)>=90:
                    continue
                x,y,w,h=(line[name] for name in ('x','y','w','h'))
                if h>48 or w>640 or len(candidates)>=12:
                    continue
                bounds=(max(0,x-5),max(0,y-5),min(image.width,x+w+5),min(image.height,y+h+5))
                with image.crop(bounds) as patch, mask.crop(bounds) as ink:
                    for l,t,r,b,bg,color in warm_text_boxes(patch,ink):
                        candidate=(l+bounds[0],t+bounds[1],r+bounds[0],b+bounds[1],bg,color)
                        if candidate not in candidates:
                            candidates.append(candidate)
            for x,y,right,bottom,bg,fg in candidates[:12]:
                w,h=right-x,bottom-y
                matches=[]
                for line in lines:
                    lx,ly,lw,lh=line.get('_source_ink') or tuple(line[k] for k in ('x','y','w','h'))
                    if (min(right,lx+lw)-max(x,lx)>=min(w,lw)*.6
                            and min(bottom,ly+lh)-max(y,ly)>=min(h,lh)*.6):
                        matches.append(line)
                if any(row.get('confidence',0)>=90 and row.get('fg',[0,0,0])[0]>=170 for row in matches):
                    continue
                region=dict(x=x-2,y=y-2,w=w+4,h=h+4,bg=bg,fg=fg,
                            _source_ink=[x,y,w,h])
                readings=[]
                if self.portable.available():
                    with mask.crop((x,y,right,bottom)) as crop, ImageOps.invert(crop) as black:
                        for scale in (1,2):
                            with black.resize((w*scale,h*scale),Image.Resampling.NEAREST) as scaled:
                                with ImageOps.expand(scaled,12,fill=255) as bordered, bordered.convert('RGB') as rgb:
                                    try:
                                        readings.extend(self.portable.recognize(rgb,'jpn' if group=='ja' else 'eng','line')['lines'])
                                    except (RuntimeError, OSError):
                                        break
                            if any(row['confidence']>=82 for row in readings):
                                break
                if group=='ja':
                    readings=[row for row in readings
                              if any('\u3041' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' for c in row['text'])]
                best=max(readings,key=lambda r:r['confidence'],default=None)
                if best and best['confidence']>=max(self.min_confidence,60):
                    # Cloud anchors describe candidate positions, never accepted OCR.
                    match = matches[0] if len(matches)==1 else None
                    primary = match.get('confidence',0) if match else 0
                    # Whole-frame and isolated-line confidences are not
                    # calibrated together. Accept a strong physical-line
                    # reading when it is close to a weaker primary reading.
                    better = best['confidence']>=primary+1 or (
                        best['confidence']>=82 and primary<90 and best['confidence']>=primary-5)
                    if (not matches and len(lines)<512) or (
                            match and better and match['h']<=h*2.5 and match['w']<=w*1.5):
                        if matches:
                            lines.remove(matches[0])
                        lines.append({**region,'text':best['text'],'confidence':best['confidence']})
                        continue
                if not matches:
                    anchors=result.setdefault('vision_anchors',[])
                    if len(anchors)<128:
                        anchors.append({**region,'text':'','_vision_only':True})
        lines.sort(key=lambda row:(row['y'],row['x']))

    def _recognize_image_uncached(self,image,language='en',mode=None):
        """Recognize one fixed local PIL image, without capturing or changing hashes.

        Returns image-relative lines. A caller can validate freshness before
        applying place_image_result. Neither this method nor auto uploads images.
        """
        with self._lock:
            selected=self.mode if mode is None else mode
            if not isinstance(selected,str) or selected not in {'auto','native','pixel'}:
                raise ValueError('Invalid OCR mode')
            if not isinstance(language,str) or len(language)>64 or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language):
                raise ValueError('Invalid OCR language')
            if not (1<=image.width<=4096 and 1<=image.height<=4096):
                raise ValueError('Invalid OCR image dimensions')
            image=image.convert('RGB')
            group=language.lower().split('-')[0]
            prefer_pixel=(selected=='auto' and group=='en' and self.portable.available()
                          and looks_like_pixel_frame(image))
            # One persistent GPU worker handles the full frame before bounded
            # local geometry refinement. Failure is latched until reconfigured;
            # do not retry expensive DLL/session startup on every game frame.
            if self.cuda is not None and selected=='auto' and group in {'en','ja','zh'} and not self._cuda_failed and not prefer_pixel and time.monotonic()>=self._cuda_retry_at:
                if self.cuda.available():
                    try:
                        response=self._cuda_recognize(image,language)
                        validate_response(response,image.width,image.height)
                        result=self._cuda_regions(image,response)
                        self.cuda_status='active'
                        return result
                    except Exception as failure:
                        code=getattr(failure,'code','recognition_failed')
                        self._cuda_failed=code in {'dependency_missing','model_invalid','cuda_unavailable'}
                        self._cuda_retry_at=time.monotonic()+12
                        self.cuda_status='failed'
                        if code!='cuda_memory':
                            self.cuda.close()
                else:self.cuda_status='not_installed'
            elif self.cuda is not None:
                self.cuda_status=('pixel_priority' if prefer_pixel else 'cpu_mode' if selected!='auto'
                                  else 'unsupported_language' if group not in {'en','ja','zh'} else 'failed')
            available=any(tag.lower().split('-')[0]==group for tag in self._native_languages)
            portable_supported=group in {'en','ja'} and self.portable.available()
            pixel=(selected=='pixel' or (selected=='auto' and group=='en' and looks_like_pixel_frame(image)))
            use_portable=selected!='native' and portable_supported and (pixel or not available)
            if not use_portable:
                if selected=='pixel' and group in {'en','ja'} and not portable_supported:
                    self.portable._start()  # Clear dependency error, no silent mode downgrade.
                result=self.native.recognize_bgra(image.tobytes('raw','BGRX'),image.width,image.height,language)
                for line in result['lines']:
                    if line.pop('separated_cell',False):line['_layout_cell']=True
                    if 'ink_bounds' in line:line['_source_ink']=line.pop('ink_bounds')
                started=time.perf_counter()
                result['lines']=self._regions.refine(image,result['lines'])
                result['region_refine_ms']=(time.perf_counter()-started)*1000
                result['ocr_stages']=['whole_frame','measured_cells','parallel_ink_refine']
                result['refine_workers']=self.refine_workers
                return result
            start=time.perf_counter()
            if group=='ja' and not pixel:
                response=self.portable.recognize(image)  # Legacy mixed Japanese default.
            else:
                response=self.portable.recognize(image,'eng' if group=='en' else 'jpn+eng','pixel' if pixel else 'standard')
            w,h=image.size
            lines = []
            accepted, rejected = filter_portable_lines(response["lines"], self.min_confidence)
            def region_from_item(item):
                left = max(0,int(item["x"])-2); top = max(0,int(item["y"])-2)
                right = min(w,int(item["x"]+item["w"])+3); bottom = min(h,int(item["y"]+item["h"])+3)
                if right <= left or bottom <= top: return None
                bg = _row_background(image,(item['x'],item['y'],item['w'],item['h']),
                                     (left,top,right,bottom))
                brightness = (bg[0]*299+bg[1]*587+bg[2]*114)/1000
                fg = [20,20,20] if brightness > 140 else [245,245,245]
                region={"text":item["text"],"x":left,"y":top,"w":right-left,"h":bottom-top,
                        "bg":bg,"fg":fg,"confidence":item["confidence"],
                        '_source_ink':[item['x'],item['y'],item['w'],item['h']]}
                if item.get('separated_cell'):region['_layout_cell']=True
                return region
            lines=[region_from_item(item) for item in accepted]
            lines=[line for line in lines if line is not None]
            anchors=[region_from_item(item) for item in response.get('vision_anchors',[])]
            anchors=[{**line,'_vision_only':True} for line in anchors if line is not None]
            refine_start=time.perf_counter()
            lines=self._regions.refine(image,lines)
            anchors=self._regions.refine(image,anchors)
            return {"lines":lines,"vision_anchors":anchors,"ocr_ms":(time.perf_counter()-start)*1000,
                    "region_refine_ms":(time.perf_counter()-refine_start)*1000,
                    "ocr_stages":["whole_frame","measured_surfaces","measured_cells","parallel_ink_refine"],
                    "refine_workers":self.refine_workers,
                    "engine":"portable-tesseract-pixel" if pixel else "portable-tesseract",
                    "min_confidence":self.min_confidence,"rejected_lines":rejected}

    def _cuda_recognize(self,image,language):
        try:
            return self.cuda.recognize(image,language)
        except Exception as failure:
            if getattr(failure,'code',None)!='cuda_memory' or max(image.size)<=1280:
                raise
        from PIL import Image
        width,height=image.size
        scale=1280/max(image.size)
        with image.resize((max(1,round(width*scale)),max(1,round(height*scale))),Image.Resampling.BILINEAR) as reduced:
            result=self.cuda.recognize(reduced,language)
            sx,sy=width/reduced.width,height/reduced.height
            for item in result['lines']:
                x,y,w,h=(item[k] for k in ('x','y','w','h'))
                left,top=math.floor(x*sx),math.floor(y*sy)
                right,bottom=math.ceil((x+w)*sx),math.ceil((y+h)*sy)
                item.update(x=left,y=top,w=min(width,right)-left,h=min(height,bottom)-top)
        return result

    def _cuda_regions(self,image,response):
        """Keep model coordinates in source pixels and use measured local ink."""
        accepted,rejected=filter_portable_lines(response['lines'],self.min_confidence)
        width,height=image.size
        lines=[]
        for item in accepted:
            ink=(item['x'],item['y'],item['w'],item['h'])
            left,top=max(0,ink[0]-2),max(0,ink[1]-2)
            right,bottom=min(width,ink[0]+ink[2]+2),min(height,ink[1]+ink[3]+2)
            bg=_row_background(image,ink,(left,top,right,bottom))
            brightness=sum(c*w for c,w in zip(bg,(299,587,114)))/1000
            lines.append({'text':item['text'],'x':left,'y':top,'w':right-left,'h':bottom-top,
                          'bg':bg,'fg':[20,20,20] if brightness>140 else [245,245,245],
                          'confidence':item['confidence'],'_source_ink':list(ink)})
        started=time.perf_counter()
        lines=self._regions.refine(image,lines)
        refine_ms=(time.perf_counter()-started)*1000
        return {**response,'lines':lines,'rejected_lines':rejected,
                'region_refine_ms':refine_ms,'ocr_compute_ms':response['ocr_ms'],
                'ocr_ms':response.get('client_ms',response['ocr_ms'])+refine_ms,
                'ocr_stages':['whole_frame_cuda','parallel_ink_refine'],
                'refine_workers':self.refine_workers,'min_confidence':self.min_confidence}

    def reset(self):
        live = getattr(self,'_live',None)
        if live is not None:
            live.reset()
            self.native.reset()
            return
        with self._lock:
            self.native.reset()
            self._capture_language=None
            if self._source_reference is not None:
                self._source_reference[0].close()
                self._source_reference = None

    def recognize_fresh(self,image,language):
        with self._lock:
            self._frames.clear()
            return self.recognize_image(image,language)

    def request_quality_review(self):
        """Refresh recognition without resetting stable source evidence."""
        if getattr(self,'_live',None) is not None:
            self._live.force_recognition=True
            self._live.submitted=-1
            self._live.next_ocr=0.
        else:
            self.request_refresh()

    def request_refresh(self):
        """Capture-worker-only refresh: retain target/ROIs and reload source pixels."""
        if getattr(self,'_live',None) is not None:
            # Clear result geometry now; the worker clears its image cache
            # before the next recognition without blocking this UI request.
            self.reset()
            self._live.force_recognition=True
            return
        with self._lock:
            self._frames.clear()
            self.reset()

    def show_overlay(self,regions):
        self.native.show_overlay(regions)

    def set_overlay_font(self,family):
        self.native.set_overlay_font(family)

    def set_overlay_options(self, **options):
        self.native.set_overlay_options(**options)

    def hide_overlay(self):
        self.native.hide_overlay()

    def set_game_executable(self,executable):
        self._windose = executable.casefold()=='windose.exe'
        self._aoi = executable.casefold()=='aoichan.exe'

    def set_target(self,hwnd,pid):
        self.native.set_target(hwnd,pid)

    def close(self):
        if self._live is not None:
            if self.cuda is not None:
                self.cuda.cancel()
            self._live.close()
            self._live = None
        if self._attention_core is not None:
            self._attention_core.close()
            self._attention_core = None
        with self._lock:
            self._source_callback=None
            if self._source_reference is not None:self._source_reference[0].close();self._source_reference=None
            self._frames.clear()
            if self.cuda is not None:self.cuda.close()
            self._palette.close()
            self._regions.close(); self.portable.close(); self._page_reader.close(); self.native.close()

    def __enter__(self): return self
    def __exit__(self,*_): self.close()
