# SPDX-License-Identifier: MIT
"""Single bounded AI recognition worker while capture continues checking freshness."""

from .i18n import ui_source
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import struct
import threading
import time
from PIL import Image
from .ocr import place_image_result, _row_background
from .layout import ScreenshotBaselines, _join_horizontal_fragments, mark_table_values
from .languages import detect_source_language
from .ocr_quality import rejection_reason
from .translatability import preservation_reason
from .translation import TranslationError
from .vision import ScreenshotRecognizer, VisionRecognizer
from .selection_regions import mask_regions, scope_lines, selection_groups


def anchor_signature(image, anchors, language):
    """Hash local geometry and its RGB union; exclude OCR text and other pixels.

    Each pixel is visited at most once, even with overlapping anchors. The hash
    retains only its digest, and temporary crops never exceed one input frame.
    """
    width,height=image.size
    if not (1<=width<=4096 and 1<=height<=4096) or not isinstance(anchors,(list,tuple)) or len(anchors)>512:
        raise ValueError('Invalid vision anchors')
    boxes=[]
    for line in anchors:
        if not isinstance(line,dict) or any(type(line.get(k)) is not int for k in ('x','y','w','h')):
            raise ValueError('Invalid vision anchor bounds')
        x,y,w,h=(line[k] for k in ('x','y','w','h'))
        if not (0<=x<x+w<=width and 0<=y<y+h<=height):
            raise ValueError('Invalid vision anchor bounds')
        boxes.append((x,y,w,h))
    boxes.sort()
    digest=hashlib.sha256(struct.pack('<III',width,height,len(boxes)))
    for box in boxes:digest.update(struct.pack('<IIII',*box))
    boundaries=sorted({edge for _,y,_,h in boxes for edge in (y,y+h)})
    for top,bottom in zip(boundaries,boundaries[1:]):
        spans=sorted((x,x+w) for x,y,w,h in boxes if y<=top and y+h>=bottom)
        merged=[]
        for left,right in spans:
            if merged and left<=merged[-1][1]:
                merged[-1]=(merged[-1][0],max(right,merged[-1][1]))
            else:merged.append((left,right))
        for left,right in merged:
            with image.crop((left,top,right,bottom)) as patch:
                digest.update(patch.tobytes())
    return language,width,height,digest.digest()


def _line_fingerprints(image, lines, language):
    """Bounded per-anchor evidence for retaining unchanged published source.

    Geometry and colors must match exactly. Unique crop area is capped at one
    frame; pathological overlapping anchors beyond that budget simply cannot
    be carried over. Only hashes, never another retained image, are returned.
    """
    width, height = image.size
    remaining = width * height
    crops = {}
    for line in lines[:512]:
        box = tuple(line[k] for k in ('x', 'y', 'w', 'h'))
        x, y, w, h = box
        if not (0 <= x < x+w <= width and 0 <= y < y+h <= height):
            continue
        if box not in crops:
            if w*h > remaining:
                continue
            remaining -= w*h
            with image.crop((x, y, x+w, y+h)) as patch:
                crops[box] = hashlib.sha256(patch.tobytes()).digest()
        colors = tuple(tuple(line.get(name, ())) for name in ('bg', 'fg'))
        key = (language, width, height, box, colors, crops[box])
        yield key, line


def _local_anchors(local, language):
    """Keep ignored rows as layout barriers, outside AI and stability keys."""
    prepared=[]
    candidates=[dict(row) for row in local.get('vision_anchors',[]) if row.get('_vision_only') is True][:512]
    def intersects(a,b):
        return max(a['x'],b['x'])<min(a['x']+a['w'],b['x']+b['w']) and max(a['y'],b['y'])<min(a['y']+a['h'],b['y']+b['h'])
    def contains(a,b):
        return a['x']<=b['x'] and a['y']<=b['y'] and b['x']+b['w']<=a['x']+a['w'] and b['y']+b['h']<=a['y']+a['h']
    original=[dict(row) for row in local['lines']]
    admitted=[]
    for row in candidates:
        overlaps=[old for old in original if intersects(row,old)]
        if any(not contains(row,old) or row.get('_selection_id')!=old.get('_selection_id') for old in overlaps):continue
        if any(intersects(row,old) for old in admitted):continue
        admitted.append(row)
        original=[old for old in original if not contains(row,old)]
    for row in (original+admitted)[:512]:
        line=dict(row)
        source=detect_source_language(line['text'],language)
        reason=None if line.get('_vision_only') else rejection_reason(line['text'],source) or preservation_reason(line['text'],source)
        line.pop('_preserve_source',None);line.pop('_ocr_rejection_reason',None)
        if reason:line.update(_preserve_source=True,_ocr_rejection_reason=reason)
        prepared.append(line)
    prepared=[line for group in selection_groups(prepared) for line in mark_table_values(group)]
    prepared=[line for group in selection_groups(prepared)
              for line in _join_horizontal_fragments(sorted(group,key=lambda line:(line['y'],line['x'])))]
    barriers=[line for line in prepared if line.get('_preserve_source')]
    lines=[]
    for line in prepared:
        if line.get('_preserve_source'):continue
        if any(max(line['x'],bad['x'])<min(line['x']+line['w'],bad['x']+bad['w'])
               and max(line['y'],bad['y'])<min(line['y']+line['h'],bad['y']+bad['h'])
               for bad in barriers):
            barriers.append({**line,'_preserve_source':True,'_ocr_rejection_reason':'overlapping_rejected_region'})
        else:lines.append(line)
    return {**local,'lines':lines},barriers


def _barrier_signature(lines):
    return tuple(sorted((line['x'],line['y'],line['w'],line['h'],
                         tuple(line.get('bg',())),tuple(line.get('fg',()))) for line in lines))


class VisionCore:
    def __init__(self,core,engine,*,interval=3.,settle=.45,recognizer=None,frame_mode=None):
        self.core=core;self.native=core.native;self._lock=threading.RLock()
        self.frame_mode = frame_mode
        factory = ScreenshotRecognizer if frame_mode else VisionRecognizer
        self.recognizer=recognizer or factory(engine)
        self._last_frame = None
        self.interval=max(1.,float(interval));self.settle=max(0.,float(settle))
        self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='vision-ocr')
        self._future=None;self._generation=0;self._cancel=threading.Event()
        self._frame=None;self._cache=OrderedDict();self._delivered=False
        self._raw_cache=OrderedDict()
        self._published={}
        self._preserved=[]
        self._capture_scope=None
        self._next_request=0.;self._ready_at=0.;self._closed=False
        self._live_enabled=False

    def enable_live_capture(self, **options):
        if self.frame_mode:
            self.native.prefer_game_capture(True)
            self.core.enable_live_capture(frame_review=self._plan_frame_review, **options)
        else:
            self.core.enable_live_capture(self._plan_live_review, **options)
        self._live_enabled=True

    def _plan_frame_review(self, local, language, known, cancel, selections):
        def recognize(source):
            start = time.perf_counter()
            try:
                with mask_regions(source, selections) as selected:
                    signature = (cancel, selected.size, hashlib.sha256(selected.tobytes()).digest())
                    if signature == self._last_frame or cancel.is_set():
                        return {'lines':[]}
                    cloud=self.recognizer.recognize_frame(selected,cancelled=cancel.is_set)
                    self._last_frame = signature
                    lines = self._cloud_regions(selected, cloud, selections)
                return {'lines':lines,'ocr_ms':(time.perf_counter()-start)*1000,'engine':'llm-screenshot'}
            except TranslationError as error:
                return {'lines':[],'vision_error':str(error)[:500]}
            except (OSError, ValueError):
                return {'lines':[],'vision_error':ui_source('LLM backend image recognition failed. Local OCR remains active.')}

        return self.interval, recognize

    def _cloud_regions(self, image, lines, selections):
        result = []
        remaining = image.width * image.height
        for item in scope_lines(lines, selections):
            x,y,w,h = (item[k] for k in ('x','y','w','h'))
            if w*h > remaining or h > image.height*.7:
                continue
            remaining -= w*h
            sx,sy,sw,sh = selections[item['_selection_id']] if selections else (0,0,*image.size)
            ink = (x,y,w,h)
            left,top,right,bottom = max(sx,x-2),max(sy,y-2),min(sx+sw,x+w+2),min(sy+sh,y+h+2)
            bg = _row_background(image,ink,(left,top,right,bottom))
            fg = [20,20,20] if sum(c*k for c,k in zip(bg,(299,587,114))) > 140000 else [245,245,245]
            from .ocr_regions import source_ink_color
            measured=source_ink_color(image,ink,bg)
            if measured is not None:fg=measured
            if item.get('_ink_rows'):
                item={**item,'_cloud_baselines':ScreenshotBaselines(tuple(
                    (a-left,b-top,c,d) for a,b,c,d in item['_ink_rows']))}
            result.append({**item,'x':left,'y':top,'w':right-left,'h':bottom-top,
                           'bg':bg,'fg':fg,'_source_ink':ink,'_cloud_ocr':True,'_sampled_fg':measured is not None})
        return result

    def _plan_live_review(self,image,local,language,known,cancel):
        from .live_capture import append_new
        eligible = append_new(known,local['lines'])
        prepared, barriers = _local_anchors({**local,'lines':eligible},language)
        _, review = self._cuda_review_partition(prepared)
        def needs_review(row):
            confidence = row.get('confidence')
            return row.get('_vision_only') or type(confidence) not in (int,float) or confidence<90
        review = [row for row in append_new(known,review) if needs_review(row)]
        if not review:
            return local,None
        available = append_new(review,local['lines'])

        def recognize(source):
            try:
                rows = self.recognizer.recognize(source,deepcopy(review),language,cancelled=cancel.is_set)
                return {**local,'lines':rows,'ocr_ms':0,'engine':'vision+local'}
            except Exception as exc:
                error=str(exc)[:500] if isinstance(exc,TranslationError) else ui_source('AI image reading failed; local OCR remains in use.')
                return {**local,'lines':[row for row in review if not row.get('_vision_only')],
                        'ocr_ms':0,'vision_error':error}

        return {'lines':[*available,*barriers],'review_interval':self.interval},recognize

    @property
    def pending(self):
        return self._future is not None and not self._future.done()

    @property
    def recognition_pending(self):
        """Includes settling time before a cloud review is submitted."""
        if self._live_enabled:
            return self.core.recognition_pending
        with self._lock:
            return self._frame is not None and not self._delivered

    def __getattr__(self,name):
        return getattr(self.core,name)

    def cancel_pending(self):
        if self._live_enabled:
            self.core.cancel_pending()
        with self._lock:
            self._cancel.set();self._generation+=1;self._frame=None;self._delivered=False
            self._capture_scope=None
            self._published.clear()
            self._preserved=[]

    def reset(self):
        self.cancel_pending()
        self.core.reset()

    def request_refresh(self):
        """Invalidate cached transcripts without abandoning the bounded worker.

        The old future retains its sole worker slot until it exits, but its
        cancellation token and generation forbid it from publishing or caching.
        No target selection, archive or configured region is changed.
        """
        with self._lock:
            self.cancel_pending()
            self._cache.clear();self._raw_cache.clear()
            self._next_request=0.;self._ready_at=0.
            refresh=getattr(self.core,'request_refresh',self.core.reset)
            refresh()

    def _recognize(self,generation,key,image,local,language,cancel):
        started=time.perf_counter()
        error=''
        try:
            # A failed recognizer must not be able to alter the local fallback
            # geometry/colors by mutating an anchor it was given.
            trusted,review=self._cuda_review_partition(local)
            reviewed=(self.recognizer.recognize(image,deepcopy(review),language,cancelled=cancel.is_set)
                      if review else [])
            lines=sorted([*trusted,*reviewed],key=lambda row:(row['y'],row['x']))
        except Exception as exc:
            lines=[line for line in local['lines'] if not line.get('_vision_only')]
            error=str(exc)[:500] if isinstance(exc,TranslationError) else ui_source('AI image reading failed; local OCR remains in use.')
        result={**local,'lines':lines,'engine':'vision+local' if not error else 'local-fallback',
                'ocr_ms':(time.perf_counter()-started)*1000,'vision_error':error}
        return generation,key,result

    @staticmethod
    def _cuda_review_partition(local):
        """Cloud review only for uncertain neural OCR; never infer confidence for Windows OCR."""
        cuda = local.get('engine') == 'rapidocr-cuda'
        trusted,review=[],[]
        for row in local['lines']:
            confidence=row.get('confidence')
            reliable = not row.get('_vision_only') and not row.get('_ocr_rejection_reason') and (
                (cuda and type(confidence) in (int, float) and 95 <= confidence <= 100)
                or (row.get('_center_label') and type(confidence) in (int, float) and 90 <= confidence <= 100))
            (trusted if reliable else review).append(deepcopy(row))
        return trusted,review

    def _cached(self,key,now):
        cached=self._cache.get(key)
        if cached and (cached[1] is None or now<cached[1]):
            self._cache.move_to_end(key)
            return cached[0]
        return None

    def _remember_raw(self,raw,key,preserved):
        self._raw_cache[raw]=(key,deepcopy(preserved));self._raw_cache.move_to_end(raw)
        while len(self._raw_cache)>16:self._raw_cache.popitem(last=False)

    def _remember_published(self, image, result, language):
        self._published = {key: deepcopy(line) for key, line in
                           _line_fingerprints(image, result['lines'], language)}

    def _unchanged_published(self, image, local, language):
        return [deepcopy(self._published[key]) for key, _ in
                _line_fingerprints(image, local['lines'], language) if key in self._published]

    def _place(self, result, x, y):
        preserved=deepcopy(self._preserved)
        if self._frame and hasattr(self.core,'verify_source_result'):
            result=self.core.verify_source_result(self._frame[1],result,x,y)
            if result.get('source_stale'):
                self.cancel_pending()
                self.core.reset()
        return place_image_result({**result,'lines':[*result['lines'],*preserved]},x,y)

    def set_capture_regions(self, regions):
        with self._lock:
            if tuple(regions) != getattr(self.core, '_capture_regions', None):
                self.reset()
                self._raw_cache.clear()
                self._cache.clear()
                self._published.clear()
                self.core.set_capture_regions(regions)

    def capture_ocr(self,x,y,w,h,language='en'):
        if self._live_enabled:
            return self.core.capture_ocr(x,y,w,h,language)
        with self._lock:
            if self._closed:raise RuntimeError('Vision core is closed')
            scope=(x,y,w,h,language)
            if scope!=self._capture_scope:
                # The raw native hash contains no language. Focus cancellation
                # also needs one fresh capture even when the pixels stay equal.
                self.core.reset();self._capture_scope=scope
            captured=self.native.capture_bgra(x,y,w,h)
            if captured.get('pending'):
                return {**captured,'lines':[],'ocr_ms':0}
            now=time.monotonic()
            empty={'changed':False,'lines':[],'capture_ms':captured['capture_ms'],'ocr_ms':0,'engine':'vision-waiting'}
            barriers_changed=False
            if captured['changed']:
                image=Image.frombytes('RGB',(w,h),captured['bgra'],'raw','BGRX')
                if hasattr(self.core, 'prepare_capture_image'):
                    original=image
                    image=self.core.prepare_capture_image(original)
                    original.close()
                if hasattr(self.core,'notify_source_frame'):self.core.notify_source_frame(image,x,y)
                # DIB alpha is unused; match the native RGB-only change hash.
                raw=(language,w,h,hashlib.sha256(image.tobytes()).digest())
                raw_cached=self._raw_cache.get(raw)
                key=raw_cached[0] if raw_cached is not None else None
                preserved=raw_cached[1] if raw_cached is not None else []
                cached=self._cached(key,now) if key is not None else None
                local=None
                if cached is None:
                    # The full image changed: inspect local anchors, but only
                    # their geometry and pixels determine whether text changed.
                    # Keep the user's OCR mode. Forcing Windows OCR here used
                    # different anchors from the configured pixel-font path.
                    local=self.core.recognize_image(image,language,mode=getattr(self.core,'mode','auto'))
                    # Supply one anchor per physical narrative row. Otherwise a
                    # model may read a complete row into its left-hand fragment
                    # and then repeat the continuation in the next anchor.
                    retain = getattr(self.core, 'retain_action_labels', None)
                    if retain is not None:
                        local = retain(image, local)
                    local,preserved=_local_anchors(local,language)
                    key=anchor_signature(image,local['lines'],language)
                    cached=self._cached(key,now)
                    trusted,review=self._cuda_review_partition(local)
                    if trusted and not review:
                        # High-confidence local GPU recognition is already a
                        # source transcript. Do not spend a second cloud OCR
                        # round-trip before allowing the actual translation.
                        cached={**local,'lines':trusted,'vision_review':'not_needed'}
                        self._cache[key]=(cached,None)
                        while len(self._cache)>16:self._cache.popitem(last=False)
                self._remember_raw(raw,key,preserved)
                barriers_changed=_barrier_signature(self._preserved)!=_barrier_signature(preserved)
                self._preserved=deepcopy(preserved)
                same=self._frame is not None and self._frame[0]==key
                if not same:
                    self._cancel.set();self._generation+=1;self._cancel=threading.Event()
                    self._delivered=False;self._ready_at=now+self.settle
                self._frame=(key,image,local,language)
                if cached is not None and not self._delivered:
                    self._delivered=True
                    self._remember_published(image,cached,language)
                    return {**self._place(cached,x,y),'changed':True,'capture_ms':captured['capture_ms']}
                if not same:
                    # A changing HUD field must not blank every stable label
                    # during the AI wait. Reuse only exact local anchor/style
                    # and source-pixel matches; changed or missing anchors hide.
                    retained=self._unchanged_published(image,local,language)
                    return {**self._place({**empty,'lines':retained},x,y),'changed':True}
            if self._future is not None and self._future.done():
                generation,key,result=self._future.result();self._future=None
                if generation==self._generation and self._frame and self._frame[0]==key:
                    self._cache[key]=(result,now+30 if result.get('vision_error') else None)
                    while len(self._cache)>16:self._cache.popitem(last=False)
                    self._delivered=True
                    self._remember_published(self._frame[1],result,self._frame[3])
                    return {**self._place(result,x,y),'changed':True,'capture_ms':captured['capture_ms']}
            if self._frame and not self._delivered and self._future is None and now>=max(self._ready_at,self._next_request):
                key,image,local,source=self._frame
                if not local['lines']:
                    self._delivered=True
                    return {**self._place(empty,x,y),'changed':True}
                self._future=self._pool.submit(self._recognize,self._generation,key,image,local,source,self._cancel)
                self._next_request=now+self.interval
            if barriers_changed and self._frame:
                key,image,local,source=self._frame
                # Barrier movement changes grouping but not AI freshness. Keep
                # exact source-evidenced rows while publishing the new barriers.
                local=local or {'lines':self._cached(key,now)['lines']}
                return {**self._place({**empty,'lines':self._unchanged_published(image,local,source)},x,y),'changed':True}
            return empty

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed=True;self.cancel_pending();self._cache.clear();self._raw_cache.clear()
        self._pool.shutdown(wait=False,cancel_futures=True)
        self.core.close()
