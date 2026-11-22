# SPDX-License-Identifier: MIT
"""Track verified source pixels while bounded workers discover new text."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock
from time import monotonic, perf_counter

from PIL import Image, ImageChops
from .flash_hold import FlashHold
from .pointer_attention import attention_crop, nearby

from .selection_regions import overlaps
from .tuning import DEFAULT_SCENE_CHANGE_SENSITIVITY


def major_scene_change(before, after, selections, sensitivity=DEFAULT_SCENE_CHANGE_SENSITIVITY):
    """Estimate the changed area within the active scan regions."""
    strength = sensitivity / 100
    pixel_threshold = round(52 - 32*strength)
    subtle_threshold = round(22 - 12*strength)
    changed_area = subtle_area = strong_area = total_area = 0
    for x,y,w,h in selections or [(0,0,*after.size)]:
        bounds = (x,y,x+w,y+h)
        # The grid ignores individual glyphs, cursor motion and pixel noise.
        with before.resize((32,24), Image.Resampling.BOX, box=bounds) as old, after.resize(
                (32,24), Image.Resampling.BOX, box=bounds) as new:
            with ImageChops.difference(old,new) as delta:
                differences = [max(rgb) for rgb in delta.get_flattened_data()]
        changed_area += w*h*sum(value>=pixel_threshold for value in differences)
        subtle_area += w*h*sum(value>=subtle_threshold for value in differences)
        strong_area += w*h*sum(value>=64 for value in differences)
        total_area += w*h*32*24
    return total_area > 0 and (changed_area >= total_area*(.75-.40*strength) or
                               (subtle_area >= total_area*(.90-.36*strength) and
                                strong_area >= total_area*(.40-.30*strength)))


def box(line):
    return tuple(int(line[key]) for key in ('x', 'y', 'w', 'h'))


def decorative_lettering(image, line):
    """Large, outlined lettering with distinct blocks of saturated fill."""
    x,y,w,h=line.get('_source_ink') or box(line)
    if h<42 or w<3*h or x<0 or y<0 or x+w>image.width or y+h>image.height:
        return False
    if line.get('_cloud_baselines') or line.get('_windose_geometry'):
        return False
    with image.resize((96,24),Image.Resampling.NEAREST,box=(x,y,x+w,y+h)) as tile:
        colors=tile.getcolors(96*24)
    white=sum(n for n,rgb in colors if min(rgb)>=230 and max(rgb)-min(rgb)<=18)
    if white<96:
        return False
    # Group nearby samples so gradients inside outlined letters count as one fill.
    # Require repeated colors in each bin to discard incidental scenery noise.
    bins={}
    for n,rgb in colors:
        if n>=3 and max(rgb)-min(rgb)>=62:
            key=tuple(v//16 for v in rgb)
            bins[key]=bins.get(key,0)+n
    fills=[key for key,total in bins.items() if total>=36]
    return any(max(abs(a-b) for a,b in zip(first,second))>=5
               for i,first in enumerate(fills) for second in fills[i+1:])

def shifted(line, dx, dy):
    result = {**line, 'x': line['x']+dx, 'y': line['y']+dy}
    if '_source_ink' in line:
        x, y, w, h = line['_source_ink']
        result['_source_ink'] = [x+dx, y+dy, w, h]
    if dx or dy:
        result['_pixel_motion'] = (dx, dy)
    else:
        result.pop('_pixel_motion', None)
    return result


def same_stationary_ink(before, after, line, rect):
    """Verify contrasting glyph shapes in small horizontal slices."""
    fg=line.get('fg')
    bg=line.get('bg')
    if (not fg or not bg or max(abs(a-b) for a,b in zip(fg,bg))<56
            or line.get('_center_label')):
        return False
    x,y,w,h=rect
    if h<8 or w<12 or w*h>65536:
        return False
    core=[255 if i<=20 else 0 for i in range(256)]
    fringe=[255 if i<=34 else 0 for i in range(256)]
    with before.crop((x,y,x+w,y+h)) as a, after.crop((x,y,x+w,y+h)) as b, Image.new('RGB',a.size,tuple(fg)) as color:
        def mask(image):
            with ImageChops.difference(image,color) as delta:
                r,g,c=delta.split()
                with r,g,c,ImageChops.lighter(r,g) as rg,ImageChops.lighter(rg,c) as peak:
                    return peak.point(core),peak.point(fringe)
        old,old_fringe=mask(a)
        new,new_fringe=mask(b)
        with old,old_fringe,new,new_fringe,ImageChops.lighter(old,new) as union, ImageChops.subtract(
                old,new_fringe) as vanished,ImageChops.subtract(new,old_fringe) as appeared, ImageChops.lighter(
                vanished,appeared) as changes:
            ink=union.histogram()[255]
            marks=changes.histogram()[255]
            if not max(16,int(w*h*.02))<=ink<=w*h*.62 or marks>max(3,ink*.035):
                return False
            bounds=old.getbbox()
            if not bounds or bounds[2]-bounds[0]<w*.55 or bounds[3]-bounds[1]<h*.48:
                return False
            step=max(12,h)
            for left in range(0,w,step):
                strip=(left,0,min(w,left+step),h)
                with union.crop(strip) as sample,changes.crop(strip) as difference:
                    if difference.histogram()[255]>max(2,sample.histogram()[255]*.10):
                        return False
            return True


def follow_source(before, after, lines, selections=(), radius=112, *, refresh=None):
    """Verify the complete line rectangle at its old or a unique nearby position."""
    if not lines or before.size != after.size:
        return []
    width, height = after.size
    stride = width*3
    kept = []
    remaining = 2_000_000
    deadline = perf_counter()+.030
    # Stationary rows are checked first, even when a list scrolls elsewhere.
    moved = []
    ink_budget = 350_000
    for line in lines[:512]:
        x,y,w,h = box(line)
        remaining -= w*h
        if remaining < 0:
            break
        rx,ry,rw,rh = selections[line.get('_selection_id',0)] if selections else (0,0,width,height)
        if not (rx <= x < x+w <= rx+rw and ry <= y < y+h <= ry+rh):
            continue
        bounds=(x,y,x+w,y+h)
        with before.crop(bounds) as a, after.crop(bounds) as b:
            old=a.tobytes()
            new=b.tobytes()
        step = w*3
        if old==new:
            kept.append(shifted(line,0,0))
        elif w >= 5 and h >= 5:
            if '_aoi_button' in line:
                from .aoi_menu import read_button
                current = read_button(after, (x,y,w,h), line['_aoi_button'])
                if current is not None:
                    kept.append({**shifted(line,0,0), **current})
                    if refresh is not None:
                        refresh.append(True)
                continue
            ink=line.get('_source_ink')
            if ink:
                ix,iy,iw,ih=ink
                if iw>=5 and ih>=5 and x<=ix and y<=iy and ix+iw<=x+w and iy+ih<=y+h:
                    # A caret or adjacent bubble may animate inside the padding.
                    at=((iy-y)*w+ix-x)*3
                    if all(old[i:i+iw*3]==new[i:i+iw*3]
                           for i in range(at,at+ih*step,step)):
                        kept.append(shifted(line,0,0))
                        if refresh is not None:refresh.append(True)
                        continue
            if perf_counter()<deadline and w*h<=ink_budget:
                ink_budget-=w*h
                rect=(ix,iy,iw,ih) if ink and iw>=5 and ih>=5 and x<=ix and y<=iy and ix+iw<=x+w and iy+ih<=y+h else (x,y,w,h)
                if same_stationary_ink(before,after,line,rect):
                    kept.append(shifted(line,0,0))
                    if refresh is not None:refresh.append(True)
                    continue
            moved.append((line, x, y, w, h, rx, ry, rw, rh, old))
    if not radius or not moved or perf_counter()>=deadline:
        return kept
    after_bytes=after.tobytes()
    for line,x,y,w,h,rx,ry,rw,rh,old in moved:
        if perf_counter() >= deadline:
            break
        # Pick a scanline with transitions, avoiding solid margins as a seed.
        step=w*3
        expected=[old[i:i+step] for i in range(0,len(old),step)]
        start_row = max(range(h),key=lambda i:len(set(zip(expected[i][::3],expected[i][1::3],expected[i][2::3]))))
        seed = expected[start_row]
        if seed == seed[:3]*w:
            continue
        left,right = max(rx,x-radius),min(rx+rw-w,x+radius)
        top,bottom = max(ry,y-radius),min(ry+rh-h,y+radius)
        matches = []
        checks = 0
        for py in range(top,bottom+1):
            base = (py+start_row)*stride
            start,end = base+left*3,base+(right+w)*3
            while (hit := after_bytes.find(seed,start,end)) >= 0:
                start = hit+1
                if (hit-base)%3:
                    continue
                checks += 1
                if checks > 32:
                    break
                point = hit-start_row*stride
                if all(after_bytes[point+i*stride:point+i*stride+w*3]==row for i,row in enumerate(expected)):
                    matches.append(((hit-base)//3,py))
                    if len(matches)>1:
                        break
            if checks > 32 or len(matches)>1:
                break
        if checks <= 32 and len(matches)==1:
            px,py = matches[0]
            if not any(overlaps((px,py,w,h),box(other)) for other in kept):
                kept.append(shifted(line,px-x,py-y))
    return kept


def append_new(known, candidates):
    """Adjacent padded boxes can touch even when their glyphs are disjoint."""
    def ink(line):
        return tuple(line.get('_source_ink') or box(line))
    existing=[ink(row) for row in known]
    return [row for row in candidates if not any(overlaps(ink(row),old) for old in existing)]


def cursor_correction(old,new):
    if old.get('_selection_id',0)!=new.get('_selection_id',0):
        return False
    if old.get('_subtitle_read') or old.get('_aoi_button') is not None or old.get('_page_verified'):
        return False
    x,y,w,h=old.get('_source_ink') or box(old)
    a,b,c,d=new.get('_source_ink') or box(new)
    if abs((y+h/2)-(b+d/2))>min(h,d)*.35 or max(h,d)>min(h,d)*1.6:
        return False
    covered=max(0,min(x+w,a+c)-max(x,a))
    previous=''.join(old['text'].split())
    reading=''.join(new['text'].split())
    score=new.get('confidence',0)
    return (covered>=.8*w and score>=75 and previous!=reading and
            ((previous in reading and len(reading)>len(previous)) or
             (score>=old.get('confidence',0)+12 and covered>=.8*c and len(reading)>=len(previous))))


def superseded_fragments(previous, primary):
    from .windose_warning import verified
    complete=[line for line in primary if verified(line)]
    if not complete:
        return previous
    return [old for old in previous if not any(
        old.get('_selection_id',0)==whole.get('_selection_id',0) and overlaps(box(old),box(whole))
        for whole in complete)]


def replaces_reading(old,new):
    """Hand a verified subtitle or cursor reading over to a complete main row."""
    if old.get('_selection_id',0)!=new.get('_selection_id',0):
        return False
    if not (new.get('_subtitle_read') or old.get('_attention_inferred')):
        return False
    x,y,w,h=old.get('_source_ink') or box(old)
    a,b,c,d=new.get('_source_ink') or box(new)
    area=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
    if area < .65*w*h:
        return False
    source=''.join(old['text'].split())
    replacement=''.join(new['text'].split())
    if (new.get('_subtitle_read') and not old.get('_subtitle_read') and new.get('confidence',0)>=88
            and area>=.8*max(w*h,c*d) and abs(y-b)<=max(3,min(h,d)//5)):
        return True
    return source in replacement or (new.get('_subtitle_read') and
                                     len(replacement)>=len(source) and not old.get('_subtitle_read'))


def merge_cloud_rows(known, recognized):
    """Prefer precise one-to-one corrections and keep unrelated local rows."""
    rows = list(known)
    for cloud in recognized:
        x,y,w,h = cloud.get('_source_ink') or box(cloud)
        hits = []
        for index, local in enumerate(rows):
            if cloud.get('_selection_id',0) != local.get('_selection_id',0):
                continue
            lx,ly,lw,lh = local.get('_source_ink') or box(local)
            area = max(0,min(x+w,lx+lw)-max(x,lx))*max(0,min(y+h,ly+lh)-max(y,ly))
            if area:
                hits.append((index, area / max(w*h,lw*lh)))
        if any('_aoi_button' in rows[i] or rows[i].get('_aoi_toolbar') for i,_ in hits):
            continue
        if not hits:
            rows.append(cloud)
        elif cloud.get('_bubble_review'):
            from .windose_warning import verified
            parts=[rows[i] for i,_ in hits]
            def covered(part):
                a,b,c,d=part.get('_source_ink') or box(part)
                area=max(0,min(a+c,x+w)-max(a,x))*max(0,min(b+d,y+h)-max(b,y))
                same_panel=(cloud.get('_cloud_baselines') and part.get('bg')==cloud.get('bg')
                            and x<=a+c/2<x+w and y<=b+d/2<y+h)
                return (area>=.60*c*d or (same_panel and area>=.40*c*d)) and not (part.get('_preserve_source') or verified(part))
            if all(covered(part) for part in parts):
                if cloud.get('_cloud_baselines'):
                    for i,_ in reversed(hits):rows.pop(i)
                    rows.append({**cloud,'fg':cloud['fg'] if cloud.get('_sampled_fg') else min(parts,key=lambda r:r['h']).get('fg',cloud['fg'])})
                    continue
                left=min(cloud['x'],*(r['x'] for r in parts));top=min(cloud['y'],*(r['y'] for r in parts))
                right=max(cloud['x']+cloud['w'],*(r['x']+r['w'] for r in parts))
                bottom=max(cloud['y']+cloud['h'],*(r['y']+r['h'] for r in parts))
                for i,_ in reversed(hits):rows.pop(i)
                rows.append({**cloud,'x':left,'y':top,'w':right-left,'h':bottom-top,
                             'fg':cloud['fg'] if cloud.get('_sampled_fg') else parts[0].get('fg',cloud['fg']),'bg':parts[0].get('bg',cloud['bg'])})
        elif len(hits) == 1 and hits[0][1] >= .55:
            index = hits[0][0]
            local = rows[index]
            from .windose_warning import verified
            if not local.get('_preserve_source') and not verified(local):
                rows[index] = {**local,'text':cloud['text'],'_cloud_ocr':True}
                if cloud.get('_sampled_fg'):rows[index]['fg']=cloud['fg']
    return rows[:512]


class LiveCapture:
    def __init__(self, core):
        self.core = core
        self._ocr_pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='local-ocr')
        self._review_pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='ocr-review')
        self._attention_pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='cursor-ocr')
        self._page_pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='page-ocr')
        self._ocr = self._review = self._attention = self._page = None
        self._preview_at = 0.
        self._preview_revision = -1
        self._page_warmed = False
        self.pointer_provider = None
        self._attention_key = None
        self._attention_signature = None
        self._flash = FlashHold()
        self.scene_change_sensitivity = DEFAULT_SCENE_CHANGE_SENSITIVITY
        self.review_plan = None
        self.frame_review = None
        self.origin = None
        self.frame = None
        self.frame_time = 0.
        self.ready_callback = None
        self.force_recognition = False
        self.lines = []
        self.revision = 0
        self.submitted = -1
        self.epoch = 0
        self.cancel = Event()
        self.next_review = 0.
        self._review_revision = -1
        self._local_result = None
        self._window_pixels = False
        self.next_ocr = 0.
        self._next_background = 0.
        self.ocr_interval = .13
        self.lock = RLock()

    def set_fade_hold(self, seconds):
        self._flash.timeout = min(seconds,.12)

    @property
    def pending(self):
        return self._ocr is not None or self._review is not None

    def reset(self):
        with self.lock:
            self._reset()

    def _reset(self):
        self.cancel.set()
        self.cancel = Event()
        self.epoch += 1
        if self.frame is not None:
            self.frame.close()
        self.frame = None
        self.lines = []
        self._flash.anchors.clear()
        self._preview_at = 0.
        self._preview_revision = -1
        self._attention_key = None
        self._attention_signature = None
        self.submitted = -1
        self.next_ocr = 0.
        self._next_background = 0.
        if not self.frame_review:
            self.next_review = 0.
        self._review_revision = -1
        self._local_result = None
        self._window_pixels = False
        self.origin = None

    def close(self):
        self.reset()
        self._ocr_pool.shutdown(wait=True,cancel_futures=False)
        self._review_pool.shutdown(wait=True,cancel_futures=False)
        self._attention_pool.shutdown(wait=True,cancel_futures=False)
        self._page_pool.shutdown(wait=True,cancel_futures=True)
        for task in (self._ocr,self._review,self._attention,self._page):
            if task is not None:
                task[1].close()

    def _notify_ready(self,_):
        callback=self.ready_callback
        if callback is not None:
            callback()

    def capture(self,x,y,w,h,language):
        with self.lock:
            return self._capture(x,y,w,h,language)

    def _capture(self,x,y,w,h,language):
        if self.origin != (x,y,w,h,language):
            self._reset()
            self.origin = (x,y,w,h,language)
        captured = self.core.native.capture_bgra(x,y,w,h)
        output = {'changed':False,'lines':[],'ocr_ms':0,'capture_ms':captured['capture_ms']}
        if captured.get('pending'):
            return {**output,'pending':True}
        if captured.get('window_pixels') is not True:
            self._window_pixels = False
        motion = False
        pixel_motion = False
        selections = self.core._capture_regions
        now = monotonic()
        discarded = []
        if captured['changed']:
            fresh = Image.frombytes('RGB',(w,h),captured['bgra'],'raw','BGRX')
            if getattr(self.core,'_aoi',False) and language.split('-')[0]=='ja':
                from .aoi_dialogue import erase_advance_markers
                cleaned = erase_advance_markers(fresh)
                if cleaned is not fresh:
                    fresh.close()
                    fresh = cleaned
                if self.frame is not None and (fresh.info.get('_aoi_advance_markers') or
                        self.frame.info.get('_aoi_advance_markers')):
                    with ImageChops.difference(self.frame,fresh) as delta:
                        if not delta.getbbox():
                            captured['changed'] = False
                            fresh.close()
        if captured['changed']:
            self.revision += 1
            if self.frame is not None:
                refresh=[]
                known = self._align(self.frame,fresh,self.lines,selections,refresh,discarded)
                if refresh and now>=self._next_background:
                    self._next_background=now+.10
                    output['background_refresh']=True
                prior_buttons={row['_aoi_button']:row for row in self.lines if '_aoi_button' in row}
                button_style_changed=any(row['bg']!=prior_buttons[row['_aoi_button']]['bg']
                                         or row['fg']!=prior_buttons[row['_aoi_button']]['fg']
                                         or row['_source_ink']!=prior_buttons[row['_aoi_button']]['_source_ink']
                                         for row in known if '_aoi_button' in row)
                pixel_motion = any(row.get('_pixel_motion') for row in known)
                motion = sorted((box(row),row['text'],bool(row.get('_flash_hold'))) for row in known) != sorted(
                    (box(row),row['text'],bool(row.get('_flash_hold'))) for row in self.lines)
                motion = motion or button_style_changed
                verified_scroll = sum(bool(row.get('_pixel_motion')) and not row.get('_flash_hold')
                                      for row in known) > len(self.lines)/2
                verified_text=bool(self.lines) and sum(not row.get('_flash_hold') for row in known)*3>=len(self.lines)*2
                if not (verified_scroll or verified_text) and major_scene_change(
                        self.frame,fresh,selections,self.scene_change_sensitivity):
                    self._reset()
                    self.origin = (x,y,w,h,language)
                    output['scene_cut'] = True
                    discarded.clear()
                    motion = True
                    pixel_motion = False
                else:
                    self.lines = known
                    self.frame.close()
            self.frame = fresh
            self._window_pixels = captured.get('window_pixels') is True
            self.frame_time = now
        if self.frame is None:
            return output
        if not captured['changed'] and self._flash.anchors:
            retained=self._flash.expire(self.lines)
            motion = len(retained)!=len(self.lines)
            if motion:
                keys = {self._flash.key(row) for row in retained}
                discarded.extend(row for row in self.lines if self._flash.key(row) not in keys)
            self.lines=retained

        screen_pointer=self.pointer_provider() if self.pointer_provider else None
        pointer=(screen_pointer[0]-x,screen_pointer[1]-y) if screen_pointer else None
        boxes=selections or ((0,0,w,h),)
        crop=attention_crop(pointer,boxes)
        if crop and getattr(self.core,'_aoi',False):
            index,_,top,_,ch=crop
            left,_,width,_=boxes[index]
            cw=min(1280,width)
            cx=max(left,min(left+width-cw,(pointer[0]//32)*32-cw//2))
            crop=index,cx,top,cw,ch
        focus_cell=(pointer[0]//32,pointer[1]//24) if crop else None
        attention_key=(crop,focus_cell,self.revision)
        recognized = False
        aoi = getattr(self.core,'_aoi',False) and language.split('-')[0]=='ja'
        if captured['changed'] and getattr(self.core,'_aoi',False) and language.split('-')[0] in ('ja','en'):
            from .aoi_menu import with_buttons
            from .aoi_toolbar import toolbar_buttons
            from .selection_regions import scope_lines
            if sum(bool(row.get('_aoi_toolbar')) for row in self.lines)<3:
                toolbar=scope_lines(toolbar_buttons(self.frame),selections)
                if toolbar:
                    self.lines=with_buttons(self.lines,toolbar)
                    recognized=True
        if captured['changed'] and aoi:
            from .aoi_menu import title_buttons, with_buttons
            from .selection_regions import scope_lines
            previous = [row for row in self.lines if '_aoi_button' in row]
            buttons = previous if len(previous)==5 else scope_lines(title_buttons(self.frame), selections)
            if buttons:
                if buttons is not previous:
                    for row in buttons:
                        row['_verified_at'] = now
                    self.lines = with_buttons(self.lines, buttons)
                recognized = recognized or len(previous)!=len(buttons) or motion
                if (not self._page_warmed and self._page is None and self.core.mode!='native'
                        and self.core._page_reader.available()):
                    # Load the Japanese line model while the player reads the title menu.
                    self._page_warmed = True
                    tile = self.frame.crop((buttons[0]['x'],buttons[0]['y'],
                                            buttons[0]['x']+buttons[0]['w'],buttons[0]['y']+buttons[0]['h']))
                    job = self._page_pool.submit(self._warm_page_reader,tile)
                    self._page = (self.epoch,tile,self.revision,now,job)
                    job.add_done_callback(self._notify_ready)
        if (aoi and self._page is None and self.revision!=self._preview_revision
                and now>=self._preview_at and self.core.mode!='native'
                and not any('_aoi_button' in row for row in self.lines)):
            if self.core._page_reader.available():
                from .aoi_dialogue import recover
                source = self.frame.copy()
                visible_ink=[tuple(row['_source_ink']) for row in self.lines
                             if row.get('_subtitle_read') and row.get('_source_ink') and not row.get('_flash_hold')]
                job = self._page_pool.submit(recover,source,[],self.core._page_reader,
                                             max(88,self.core.min_confidence),limit=4,skip_ink=visible_ink)
                self._page = (self.epoch,source,self.revision,self.frame_time,job)
                self._preview_revision = self.revision
                self._preview_at = now+0.45
                job.add_done_callback(self._notify_ready)
        for attr in ('_page','_ocr','_review','_attention'):
            task = getattr(self,attr)
            if task is None or not task[-1].done():
                continue
            setattr(self,attr,None)
            epoch, source, revision, source_time, future = task
            with source:
                if epoch!=self.epoch:
                    continue
                try:
                    result = future.result()
                except Exception:
                    if attr in ('_attention','_page'):
                        continue
                    if attr=='_ocr' and self.frame_review:
                        self._local_result = {'lines':[]}
                        continue
                    raise
                if attr=='_attention' and (crop is None or result['crop'][0]!=crop[0]):
                    continue
                if attr=='_page':
                    from .selection_regions import scope_lines
                    rows=scope_lines(result,selections)
                    for row in rows:
                        row['_page_preview']=True
                    if not rows:
                        continue
                    result={'lines':rows, 'engine':'page-preview'}
                else:
                    rows = result['lines']
                if attr=='_ocr' and self.review_plan is not None and self._review is None and now>=self.next_review:
                    known = self.lines if revision==self.revision else follow_source(self.frame,source,self.lines,selections)
                    immediate, callback = self.review_plan(source,result,language,known,self.cancel)
                    if callback is not None:
                        review_image=source.copy()
                        job=self._review_pool.submit(callback,review_image)
                        self._review=(epoch,review_image,revision,source_time,job)
                        job.add_done_callback(self._notify_ready)
                        self.next_review=now+immediate['review_interval']
                        rows=immediate['lines']
                # Compare only candidate additions; this keeps existing flash
                # anchors and main-frame geometry out of the cursor lane.
                if attr=='_attention':
                    rows=[row for row in rows if nearby(row,pointer)]
                if revision!=self.revision and rows:
                    if attr=='_attention':
                        _,cx,cy,cw,ch=result['crop']
                        with self.frame.crop((cx,cy,cx+cw,cy+ch)) as latest:
                            rows=[shifted(row,cx,cy) for row in follow_source(
                                source,latest,[shifted(row,-cx,-cy) for row in rows],radius=0)]
                    else:
                        # Flash retention is for consecutive live observations.
                        # Late OCR must prove its original pixels still exist.
                        rows=follow_source(source,self.frame,rows,selections)
                if attr == '_review' and self.frame_review and not self._window_pixels:
                    continue
                if attr == '_review' and result.get('engine') in ('llm-screenshot','deepseek-screenshot'):
                    for row in rows:
                        row['_verified_at'] = source_time
                    self.lines = merge_cloud_rows(self.lines, rows)
                    rows = []
                if attr in ('_ocr','_page'):
                    from .aoi_dialogue import superseded_boxes
                    measured=[row for row in (*self.lines,*rows) if row.get('_subtitle_read')]
                    # Cloud/rough OCR can return a single box spanning both lines.
                    if len(measured)>=2:
                        self.lines=superseded_boxes(self.lines,measured)
                        rows=superseded_boxes(rows,measured)
                if attr=='_ocr':
                    self._local_result = result
                    self.lines=superseded_fragments(self.lines,rows)
                if attr in ('_ocr','_page') and rows:
                    self.lines=[row for row in self.lines if not any(replaces_reading(row,main) for main in rows)]
                if attr=='_attention' and rows:
                    self.lines=[old for old in self.lines if not any(cursor_correction(old,new) for new in rows)]
                additions=append_new(self.lines,rows)[:max(0,512-len(self.lines))]
                self.lines.extend(additions)
                for row in additions:
                    row['_verified_at']=source_time
                if attr not in ('_attention','_page'):
                    output.update(result)
                recognized=recognized or attr!='_attention' or bool(additions)
        if (self.frame_review and self._window_pixels and self._review is None
                and self._review_revision!=self.revision and now>=self.next_review):
            plan=self.frame_review(self._local_result,language,self.lines,self.cancel,selections)
            if plan is not None:
                interval, recognize = plan
                review_image = self.frame.copy()
                job = self._review_pool.submit(recognize, review_image)
                self._review = (self.epoch, review_image, self.revision, self.frame_time, job)
                job.add_done_callback(self._notify_ready)
                self._review_revision = self.revision
                self.next_review = now + interval
        if crop and self._attention is None and attention_key!=self._attention_key:
            _,cx,cy,cw,ch=crop
            source=self.frame.crop((cx,cy,cx+cw,cy+ch))
            from hashlib import blake2b
            signature=(crop,focus_cell,blake2b(source.tobytes(),digest_size=16).digest())
            if getattr(self,'_attention_signature',None)!=signature:
                future=self._attention_pool.submit(self._read_attention,source,language,crop)
                self._attention=(self.epoch,source,self.revision,self.frame_time,future)
                future.add_done_callback(self._notify_ready)
                self._attention_signature=signature
            else:
                source.close()
            self._attention_key=attention_key
        for row in self.lines:
            is_near=bool(crop and nearby(row,pointer) and row.get('_selection_id',0)==crop[0])
            if is_near!=bool(row.get('_pointer_priority')):
                row['_pointer_priority']=is_near
                motion=True
        if self._ocr is None and self.submitted!=self.revision and now>=self.next_ocr:
            source,revision,source_time=self.frame.copy(),self.revision,self.frame_time
            recognize=self.core.recognize_fresh if self.force_recognition else self.core.recognize_image
            self.force_recognition=False
            job=self._ocr_pool.submit(recognize,source,language)
            self._ocr=(self.epoch,source,revision,source_time,job)
            job.add_done_callback(self._notify_ready)
            self.submitted=revision
            self.next_ocr=now+self.ocr_interval
        if recognized or motion:
            from .ocr import place_image_result
            if recognized:
                for row in self.lines:
                    row['_decorative_lettering']=decorative_lettering(self.frame,row)
            self.lines.sort(key=lambda row:(row['y'],row['x']))
            output=place_image_result({**output,'changed':True,'lines':self.lines},x,y)
            for row in output['lines']:
                sx,sy,sw,sh = selections[row.get('_selection_id',0)] if selections else (0,0,w,h)
                row['_scroll_clip']=(x+sx,y+sy,x+sx+sw,y+sy+sh)
            output['motion_only']=not recognized
            output['pixel_motion']=pixel_motion
        if discarded:
            output['source_changed_regions'] = [dict(x=x+sx,y=y+sy,w=sw,h=sh)
                                                for sx,sy,sw,sh in map(box,discarded)]
        return output

    def _align(self,before,after,rows,selections,refresh,discarded):
        if not rows:
            return []
        known=follow_source(before,after,[row for row in rows if not row.get('_flash_hold')],selections,refresh=refresh)
        matched={self._flash.key(shifted(row,*(-v for v in row.get('_pixel_motion',(0,0))))) for row in known}
        missing=[row for row in rows if self._flash.key(row) not in matched]
        faded = self._flash.recover(before,after,[row for row in missing if '_aoi_button' not in row])
        retained = {self._flash.key(row) for row in faded}
        candidates = []
        budget = 250_000
        for row in missing:
            if self._flash.key(row) in retained:
                continue
            if row.get('_flash_hold'):
                discarded.append(row)
            elif row['w']*row['h'] <= budget:
                candidates.append(row)
                budget -= row['w']*row['h']
        if candidates:
            from .ocr import changed_source_indices
            indices = changed_source_indices(before,after,candidates,sensitivity=self.scene_change_sensitivity)
            discarded.extend(candidates[index] for index in sorted(indices))
        return known+append_new(known,faded)

    def _warm_page_reader(self,tile):
        self.core._page_reader.recognize(tile,'jpn','line')
        return []

    def _read_attention(self,source,language,crop):
        selection,x,y,w,h=crop
        result=self.core.recognize_attention(source,language)
        margin=3
        lines=[]
        for row in result['lines']:
            left,top,rw,rh=box(row)
            if margin<=left<left+rw<=w-margin and margin<=top<top+rh<=h-margin:
                line=shifted(row,x,y)
                line.pop('_pixel_motion',None)
                line['_attention_inferred']=True
                if self.core._capture_regions:
                    line['_selection_id']=selection
                lines.append(line)
        return {'crop':crop,'lines':lines}
