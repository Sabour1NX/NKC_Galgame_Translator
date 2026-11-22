# SPDX-License-Identifier: MIT
"""Bounded multi-object capture, tracking and translation pipeline.

One capture worker produces the newest OCR observation. A separate coordinator
associates stable objects and dispatches a bounded pool of translation workers.
Only session changes invalidate all objects; text edits invalidate one revision.
All notifications are plain data. No worker touches a Tk widget.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from dataclasses import dataclass
from itertools import count
import queue
import threading
import time
from .pointer_attention import CursorLens, cursor_position, nearby
from .layout import ScreenshotBaselines, merge_dialogue_lines, reflow_translation, mark_table_values, has_numeric_table_evidence
from .tracking import ObjectTracker
from .windose_warning import verified
from .languages import detect_source_language, label_translation, foreign_language_groups, coherent_language_groups
from .translation import TranslationError, RetryableTranslationError
from .ocr_quality import rejection_reason
from .translatability import preservation_reason, unchanged_translation
from .selection_regions import capture_plan, selection_groups, limit_two_layers
from .literal_rules import separate_literal_values

_GENERATIONS = count(1)
_GENERATION_LOCK = threading.Lock()


def _overlaps(first, second):
    return (max(first['x'], second['x']) < min(first['x'] + first['w'], second['x'] + second['w'])
            and max(first['y'], second['y']) < min(first['y'] + first['h'], second['y'] + second['h']))


def _quality_lines(lines, selected_source, origin, merge_lines, game_executable=''):
    """Keep rejected geometry as a barrier; never redraw its uncertain text."""
    if game_executable.casefold()=='aoichan.exe' and selected_source=='ja':
        from .aoi_dialogue import OPENING_CHOICES, OPENING_PROMPT, opening_fragment, repair_caption, rental_ad_caption, single_subtitle_rows
        lines = [{**line, 'text':repair_caption(line['text'])} for line in lines if not opening_fragment(line['text'])]
        lines = single_subtitle_rows(lines)
        for line in lines:
            if line['text'] in OPENING_CHOICES:
                line.update(_center_label=True, _layout_cell=True)
            elif line['text']==OPENING_PROMPT:
                line.update(_standalone_subtitle=True, _layout_cell=True)
            elif len(line['text'])<=240 and rental_ad_caption(line['text'],False):
                line['_layout_cell']=True
    prepared = []
    rejected = []
    literal_values=separate_literal_values(lines)
    for index,line in enumerate(lines):
        source = detect_source_language(line['text'], selected_source)
        reason = (('protected_literal' if index in literal_values else None)
                  or ('decorative_lettering' if line.get('_decorative_lettering') else None)
                  or rejection_reason(line['text'], source) or preservation_reason(line['text'], source)
                  or ('numeric_table_cell' if has_numeric_table_evidence(line) else None))
        item = {**line, '_capture_origin': origin, 'source_lang': source}
        # These fields are local decisions, not trusted OCR/provider metadata.
        item.pop('_preserve_source', None)
        item.pop('_ocr_rejection_reason', None)
        item.pop('_flow_layout', None)
        item.pop('_translation_unchanged', None)
        item.pop('_source_rows', None)
        item['_fixed_layout'] = True
        item['_source_line_count'] = min(32, max(1, len(line['text'].splitlines())))
        if verified(line) or isinstance(line.get('_cloud_baselines'),ScreenshotBaselines):
            geometry=line.get('_cloud_baselines') or line['_windose_geometry']
            item['_source_rows']=[dict(x=x,y=y,w=w,h=h) for x,y,w,h in geometry.rows]
            item['_source_line_count']=len(item['_source_rows'])
        if reason:
            item.update(_preserve_source=True, _ocr_rejection_reason=reason)
            rejected.append(item)
        prepared.append(item)
    prepared = [line for group in selection_groups(prepared) for line in mark_table_values(group)]
    rejected = [item for item in prepared if item.get('_preserve_source')]
    if merge_lines:
        prepared = [line for group in selection_groups(prepared) for line in merge_dialogue_lines(group)]
    # A spanning or overlapping OCR object must not cover a rejected row,
    # including rows outside the bounded set eventually admitted by tracking.
    for item in prepared:
        if not item.get('_preserve_source') and any(_overlaps(item, bad) for bad in rejected):
            item.update(_preserve_source=True, _ocr_rejection_reason='overlapping_rejected_region')
    return prepared


def _next_generation():
    with _GENERATION_LOCK:
        return next(_GENERATIONS)


@dataclass
class _ObjectState:
    revision: int
    line: dict
    stable_at: float
    captured_at: float = 0.
    confirmed: bool = False
    visible: bool = True
    attempted: bool = False
    provisional: bool = False
    separate: bool = False
    # Last cumulative text/finality supports movement and brief OCR misses.
    output: tuple[str, bool] | None = None
    error: str | None = None


class Pipeline:
    def __init__(self, core, engine, emit, *, interval=.25, settle=.45,
                 merge_lines=True, tracking_workers=2, translation_workers=4,
                 max_objects=32, max_missing=2, show_source_label=True, label_language='zh-CN',
                 show_translation_brackets=True, source_label_mixed_only=False, warmup_scope=None,
                 cursor_attention=False, sampling_mode='off', fast_capture_ms=50, persist_results=False,
                 game_executable=''):
        if any(type(value) is not bool for value in (show_source_label, show_translation_brackets, source_label_mixed_only)):
            raise ValueError('Display switches must be boolean')
        self.label_language = label_language
        self.show_source_label = show_source_label
        self.show_translation_brackets = show_translation_brackets
        self.source_label_mixed_only = source_label_mixed_only
        self.warmup_scope = warmup_scope
        self.game_executable = game_executable
        self._visible_foreign_languages = frozenset()
        self.lightweight=False
        self._lens=CursorLens()
        self.core, self.engine, self.emit = core, engine, emit
        self.interval = max(.005, float(interval))
        self.settle = max(0., float(settle))
        if sampling_mode not in ('off','auto','supersample'):
            raise ValueError('Invalid sampling mode')
        self.sampling_mode=sampling_mode
        self.fast_interval=min(self.interval,max(.02,fast_capture_ms/1000))
        self.persist_results=persist_results
        self.merge_lines = bool(merge_lines)
        self.tracking_workers = min(4, max(1, int(tracking_workers)))
        self.translation_workers = min(16, max(1, int(translation_workers)))
        self.max_objects = min(128, max(1, int(max_objects)))
        self.tracker = ObjectTracker(workers=self.tracking_workers,
                                     max_tracks=self.max_objects,
                                     max_missing=max(0, int(max_missing)))
        self.stop_event = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=self.translation_workers,
                                       thread_name_prefix='translate')
        self.pointer_pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='cursor-translate') if cursor_attention else None
        self._pointer_job = None
        self.generation = _next_generation()
        self.thread = None  # Compatibility: capture/OCR thread.
        self.coordinator_thread = None
        self._state_lock = threading.RLock()
        self._observations = queue.Queue(maxsize=1)
        self._states: dict[int, _ObjectState] = {}
        self._inflight = {}
        self._recent_outputs = OrderedDict()
        self._result_epoch = 0
        self._quality_pending = False
        self._queue_drops = 0
        self._observation_serial = 0
        self._capture_active = False
        self._scope = None
        self._capture_wake = threading.Event()
        self._refresh_pending = False
        self._refresh_active = False
        self._refresh_ready_serial = None
        self._refresh_observed = False
        self._translation_epoch = None
        self._source_change_serial = 0

    @property
    def alive(self):
        """Capture and coordinator must both finish before reusing the core."""
        return any(worker is not None and worker.is_alive()
                   for worker in (self.thread, self.coordinator_thread))

    def start(self, region_provider, game, source, target, context=''):
        with self._state_lock:
            if self.thread is not None or self.stop_event.is_set():
                raise RuntimeError('Pipeline \u5b9e\u4f8b\u4e0d\u80fd\u91cd\u590d\u542f\u52a8\uff0c\u8bf7\u7b49\u5f85\u65e7\u5b9e\u4f8b\u7ed3\u675f\u540e\u521b\u5efa\u65b0\u5b9e\u4f8b\u3002')
            advance = getattr(self.engine, 'advance_request_epoch', None)
            self._translation_epoch = advance() if advance is not None else None
            self._scope = (game, source, target, context)
            if hasattr(self.core,'set_source_change_callback'):
                self.core.set_source_change_callback(self._source_regions_changed)
            if hasattr(self.core,'set_ready_callback'):
                self.core.set_ready_callback(self._capture_wake.set)
            self.coordinator_thread = threading.Thread(target=self._coordinate,
                daemon=True, name='object-coordinator')
            self.thread = threading.Thread(target=self._capture,
                args=(region_provider, source), daemon=True, name='capture-ocr')
            self.coordinator_thread.start()
            self.thread.start()

    def request_retranslation(self):
        """Accept one refresh of the selected target; repeated presses coalesce.

        This UI-facing method never captures pixels or waits on an OCR/model
        lock. Old display callbacks become stale immediately. The capture
        worker performs invalidation and a new recognition pass on the same
        target/ROIs, retaining bounded worker slots and the saved AI history.
        """
        with self._state_lock:
            if self.thread is None or self.stop_event.is_set():
                return False
            if self._refresh_active:
                return True
            self._refresh_pending = self._refresh_active = True
            self._refresh_observed = False
            self._refresh_ready_serial = None
            self._result_epoch += 1
            self._recent_outputs.clear()
            self._invalidate_locked(keep_view=self.persist_results)
            self._capture_wake.set()
            return True

    def _wait_capture(self, seconds):
        self._capture_wake.wait(seconds)
        self._capture_wake.clear()

    def _source_regions_changed(self, regions):
        """Hide only source-evidenced stale objects before expensive OCR finishes."""
        with self._state_lock:
            if self.stop_event.is_set():return
            self._source_change_serial+=1
            self._observation_serial+=1
            self.emit(('source_changed', self.generation, regions))
            affected=False
            for state in self._states.values():
                if state.visible and any(_overlaps(state.line,region) for region in regions):
                    state.visible=False;affected=True
            if affected:
                # Discard pre-change coordinator work while keeping tracker IDs
                # and in-flight results available for the next valid geometry.
                self.emit(('objects',self.generation,[{'track_id':identity,'revision':state.revision,'line':dict(state.line)}
                          for identity,state in self._states.items() if state.visible]))

    def _offer_locked(self, observation, *, confirmation=False, captured_at=None, motion_only=False):
        """Replace the waiting observation; never enqueue a history of frames."""
        self._observation_serial += 1
        observation = (*observation, self._observation_serial, confirmation, captured_at, motion_only)
        try:
            self._observations.put_nowait(observation)
        except queue.Full:
            try:
                self._observations.get_nowait()
                self._queue_drops += 1
            except queue.Empty:
                pass  # Coordinator consumed it concurrently.
            self._observations.put_nowait(observation)

    def _invalidate_locked(self, *, keep_view=False):
        self.generation = _next_generation()
        self._states.clear()
        self._visible_foreign_languages = frozenset()
        self.emit(('hold' if keep_view else 'clear', self.generation, None))
        # Do not cancel old submitted jobs and then replace their WorkItems:
        # those jobs continue occupying the bounded number of worker slots.
        self._offer_locked((self.generation, None, None))

    def set_lightweight(self,enabled):
        with self._state_lock:
            if self.lightweight!=enabled:
                self.lightweight=enabled
                self._result_epoch+=1
                self._lens=CursorLens()
                self._invalidate_locked()
                self.core.hide_overlay()
                self._capture_wake.set()

    def _active_region(self,bounds):
        if not self.lightweight:return bounds
        anchor=self._lens.anchor
        region=self._lens.region(cursor_position(),bounds)
        if anchor!=self._lens.anchor:
            with self._state_lock:
                self._result_epoch+=1
                self._invalidate_locked()
                self.core.hide_overlay()
        return region

    def _lose_target(self):
        with self._state_lock:
            if self.stop_event.is_set() or not self._capture_active:
                return
            self._capture_active = False
            self._invalidate_locked()
        if hasattr(self.core,'cancel_pending'):self.core.cancel_pending()
        self.core.hide_overlay()

    def _fail(self, error):
        with self._state_lock:
            if self.stop_event.is_set():
                return
            self.stop_event.set()
            self._capture_wake.set()
            self.generation = _next_generation()
            self._states.clear()
            self.emit(('clear', self.generation, None))
            self.emit(('error', self.generation, '\u6355\u83b7\u6216\u8bc6\u522b\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u6e38\u620f\u7a97\u53e3\u548c\u533a\u57df\u3002'))
            self.pool.shutdown(wait=False, cancel_futures=True)
        self.core.hide_overlay()

    def _capture(self, provider, source):
        last_region = None
        confirmed_lines, confirm_remaining = None, 0
        confirmed_source_serial = None
        burst_until = 0.
        last_lens=None
        while not self.stop_event.is_set():
            began = time.monotonic()
            period=self.fast_interval if self.sampling_mode=='supersample' or began<burst_until else self.interval
            region = None
            try:
                region = capture_plan(self._active_region(provider()))
                if self.stop_event.is_set():
                    break
                if region is None:
                    self._lose_target()
                    burst_until=0.
                    last_region = None
                    confirmed_lines, confirm_remaining = None, 0
                    self._wait_capture(self.interval)
                    continue
                with self._state_lock:
                    self._capture_active = True
                    session = self.generation
                    refresh = self._refresh_pending
                    self._refresh_pending = False
                    quality = self._quality_pending
                    self._quality_pending = False
                if quality and not refresh:
                    getattr(self.core,'request_quality_review',getattr(self.core,'request_refresh',self.core.reset))()
                    confirmed_lines,confirm_remaining=None,0
                if refresh:
                    advance = getattr(self.engine, 'advance_request_epoch', None)
                    epoch = advance() if advance is not None else None
                    getattr(self.core, 'request_refresh', self.core.reset)()
                    if not self.persist_results:
                        self.core.hide_overlay()
                    with self._state_lock:
                        self._translation_epoch = epoch
                    confirmed_lines, confirm_remaining = None, 0
                lens=self._lens.anchor if self.lightweight else None
                if region != last_region or lens!=last_lens:
                    last_lens=lens
                    burst_until=0.
                    self.core.reset()
                    if hasattr(self.core, 'set_capture_regions'):
                        self.core.set_capture_regions(region.regions)
                    elif len(region.regions) > 1:
                        raise RuntimeError('This OCR core does not support multiple regions')
                    last_region = region
                    confirmed_lines, confirm_remaining = None, 0
                result = self.core.capture_ocr(*region.bounds, language=source)
                if self.sampling_mode=='auto' and result.get('pixel_motion'):
                    burst_until=time.monotonic()+.65
                    period=self.fast_interval
                if self.stop_event.is_set():
                    break
                if result.get('pending'):
                    confirmed_lines,confirm_remaining=None,0
                    self._wait_capture(max(.005,period-(time.monotonic()-began)))
                    continue
                # A slow OCR must not publish a frame taken before focus/move.
                current_region = capture_plan(self._active_region(provider()))
                if current_region != region:
                    if current_region is None:
                        self._lose_target()
                    last_region = None
                    continue
                with self._state_lock:
                    if self.stop_event.is_set() or session != self.generation:
                        continue
                    if result.get('scene_cut'):
                        self._recent_outputs.clear()
                        advance=getattr(self.engine,'advance_request_epoch',None)
                        if advance:self._translation_epoch=advance()
                        self._result_epoch += 1
                        self._invalidate_locked()
                        session = self.generation
                        confirmed_lines, confirm_remaining = None, 0
                        self.core.hide_overlay()
                    elif result.get('source_changed_regions'):
                        self._source_regions_changed(result['source_changed_regions'])
                    if result.get('background_refresh') and not result.get('scene_cut'):
                        self.emit(('background',session,None))
                    if result['changed']:
                        lines = [dict(r) for r in result['lines']
                                 if str(r.get('text', '')).strip()
                                 ][:512]
                        motion_only = bool(result.get('motion_only'))
                        self._offer_locked((session, region.bounds[:2], lines),captured_at=began,
                                           motion_only=motion_only)
                        if motion_only:
                            confirmed_lines, confirm_remaining = None, 0
                        else:
                            if self._refresh_active and not getattr(self.core, 'recognition_pending', False):
                                self._refresh_ready_serial = self._observation_serial
                            confirmed_lines, confirm_remaining = lines, 2
                            confirmed_source_serial = self._source_change_serial
                            self.emit(('timing', session, result))
                    elif confirmed_source_serial != self._source_change_serial:
                        confirmed_lines, confirm_remaining = None, 0
                    elif confirm_remaining and confirmed_lines is not None:
                        # An unchanged captured image confirms the last OCR
                        # result without rerunning OCR or calling the API.
                        # At most two confirmations, no perpetual idle work.
                        self._offer_locked((session, region.bounds[:2], confirmed_lines), confirmation=True)
                        confirm_remaining -= 1
            except Exception as exc:
                try:
                    moved=region is not None and capture_plan(self._active_region(provider()))!=region
                except Exception:
                    moved=False
                if moved:
                    last_region=None
                    confirmed_lines,confirm_remaining=None,0
                else:
                    self._fail(exc)
            self._wait_capture(max(.005, period - (time.monotonic() - began)))

    def _coordinate(self):
        tracker_session = None
        try:
            while not self.stop_event.is_set():
                try:
                    observation = self._observations.get(timeout=.005)
                except queue.Empty:
                    observation = None
                if self.stop_event.is_set():
                    break
                if observation is not None:
                    session, origin, lines, serial, confirmation, captured_at, motion_only = observation
                    with self._state_lock:
                        current = session == self.generation
                    if not current:
                        continue
                    if tracker_session != session:
                        self.tracker.reset()
                        tracker_session = session
                    if lines is not None:
                        # Route each detected box before grouping. Adjacent rows
                        # of different source languages must not become one box.
                        selected_source = self._scope[1]
                        lines = _quality_lines(lines, selected_source, origin, self.merge_lines,self.game_executable)
                        if self.lightweight:
                            point=cursor_position()
                            lines=[r for r in lines if nearby(r,point)]
                        for row in lines:
                            row['_cover_source']=(row['source_lang']=='ja' and not self._scope[2].startswith('ja')
                                                  and not row.get('_preserve_source') and
                                                  any('\u3041'<=c<='\u30ff' for c in row['text']))
                        if len(lines)>self.max_objects:
                            lines.sort(key=lambda row:(not row.get('_pointer_priority'),not row['_cover_source']))
                        lines = limit_two_layers(lines[:self.max_objects])
                        update = self.tracker.update(lines, origin=origin, advance_missing=not (confirmation or motion_only))
                        with self._state_lock:
                            if (self.stop_event.is_set() or session != self.generation
                                    or serial != self._observation_serial):
                                continue
                            self._apply_objects_locked(update.tracks, session,confirmation=confirmation,
                                                       captured_at=captured_at,motion_only=motion_only)
                            if (self._refresh_ready_serial is not None
                                    and serial >= self._refresh_ready_serial):
                                self._refresh_observed = True
                self._schedule()
        except Exception as exc:
            self._fail(exc)
        finally:
            self.tracker.close()

    def _apply_objects_locked(self, tracks, session,*,confirmation=False,captured_at=None,motion_only=False):
        now = time.monotonic()
        old_visible = {track_id for track_id, state in self._states.items() if state.visible}
        old_layouts = {track_id: bool(state.line.get('_flow_layout')) for track_id, state in self._states.items()}
        old_labels = {track_id: bool(state.line.get('_label_mixed')) for track_id,state in self._states.items()}
        reused=set()
        for state in self._states.values():
            state.visible = False
        for track in tracks:
            state = self._states.get(track.track_id)
            if state is None or state.revision != track.revision:
                state = _ObjectState(track.revision, dict(track.line), now,
                                     captured_at=min(now,captured_at) if captured_at is not None else now)
                state.provisional=motion_only
                self._states[track.track_id] = state
            else:
                # One accepted source revision owns its style, just as it owns
                # fitted size; uncertain OCR refreshes must not flip fonts.
                source_style=state.line.get('_source_font_style')
                state.line = dict(track.line)
                if source_style is not None:state.line['_source_font_style']=source_style
                state.visible = True
                if confirmation:state.confirmed=True
            state.line['_source_stamp']=state.stable_at
            confidence=state.line.get('confidence')
            verified_at=state.line.get('_verified_at')
            if (self.persist_results and not motion_only and type(confidence) in (int,float)
                    and confidence>=96 and type(verified_at) in (int,float) and not state.line.get('_flash_hold')):
                state.confirmed=True
                state.captured_at=min(now,verified_at)
            if state.line.get('_preserve_source'):
                state.output = None
                state.error = None
                state.attempted = True
            elif self.persist_results and not state.attempted:
                source_key=(state.line['source_lang'],state.line['text'])
                if source_key in self._recent_outputs:
                    self._recent_outputs.move_to_end(source_key)
                    state.output=(self._recent_outputs[source_key],True)
                    state.attempted=True
                    reused.add(track.track_id)
            if not motion_only and not confirmation:
                state.provisional=False
        # Only retained missing tracks keep results. Expired IDs never grow RAM.
        for track_id in list(self._states):
            if self.tracker.get(track_id) is None:
                del self._states[track_id]
        self._visible_foreign_languages = foreign_language_groups(
            (track.line.get('source_lang', '') for track in tracks), self._scope[2])
        groups=coherent_language_groups([self._states[track.track_id].line for track in tracks],self._scope[2])
        for track,group in zip(tracks,groups):
            self._states[track.track_id].line['_label_mixed']=len(group)>=2
        objects = [{'track_id': track.track_id, 'revision': track.revision,
                    'line': dict(self._states[track.track_id].line)} for track in tracks]
        self.emit(('objects', session, objects))
        for track in tracks:
            state = self._states[track.track_id]
            reformat = self.source_label_mixed_only and old_labels.get(track.track_id)!=state.line['_label_mixed']
            layout_changed = old_layouts.get(track.track_id) != bool(state.line.get('_flow_layout'))
            if state.output is not None and (track.track_id not in old_visible or reformat or layout_changed
                                             or track.track_id in reused):
                # Visibility changes only reformat the last raw cumulative output.
                # No task, revision, translation-memory key or API call changes.
                self._emit_translation_locked(session, track.track_id, state, *state.output)
            elif track.track_id not in old_visible and state.error:
                self.emit(('line_error', session, (track.track_id, state.revision, state.error)))

    def _schedule(self):
        with self._state_lock:
            if self.stop_event.is_set():
                return
            self._inflight = {future: key for future, key in self._inflight.items()
                              if not future.done()}
            now = time.monotonic()
            pending = sorted(((track_id, state) for track_id, state in self._states.items()
                              if state.visible and not state.attempted and not state.line.get('_preserve_source')
                              and not state.provisional
                              and (('_aoi_button' in state.line or state.line.get('_aoi_choice') or state.line.get('_page_preview'))
                                   or (self.pointer_pool and state.line.get('_pointer_priority'))
                                   or now - (state.captured_at if state.confirmed else state.stable_at) >= self.settle)),
                             key=lambda pair: (not bool(self.pointer_pool and pair[1].line.get('_pointer_priority')),
                                               pair[1].stable_at, pair[0]))
            # Verified game captions are already final. They can paint while
            # the network workers are still busy on the preceding page.
            from .aoi_menu import TRANSLATIONS
            from .aoi_toolbar import LABELS
            target=self._scope[2]
            if self.game_executable.casefold()=='aoichan.exe' and target in ('zh','zh-Hans','zh-CN','zh-Hant','zh-TW'):
                from .aoi_dialogue import OPENING_CHOICES, OPENING_PROMPT, OPENING_TRANSLATIONS, name_caption, rental_ad_caption
                traditional=target in ('zh-Hant','zh-TW')
                remaining=[]
                for track_id,state in pending:
                    caption=TRANSLATIONS.get(state.line['text']) if '_aoi_button' in state.line else None
                    if state.line.get('_aoi_toolbar') and state.line['source_lang']=='en':
                        caption=LABELS.get(state.line['text'])
                    translated=caption[traditional] if caption else None
                    if translated is None and state.line['source_lang']=='ja' and len(state.line['text'])<=240:
                        text=state.line['text']
                        if text==OPENING_PROMPT:
                            translated=OPENING_TRANSLATIONS[traditional]
                        elif text in OPENING_CHOICES:
                            translated=OPENING_CHOICES[text][traditional]
                        else:
                            translated=name_caption(text,traditional) or rental_ad_caption(text,traditional)
                    if translated is None:
                        remaining.append((track_id,state))
                        continue
                    state.attempted=True
                    self._translate((self.generation,track_id,state.revision),dict(state.line),
                                    self._translation_epoch,self._result_epoch,
                                    completed=translated)
                pending=remaining
            # Dispatch the focused row before a page batch can claim it.
            if (self.pointer_pool and pending and pending[0][1].line.get('_pointer_priority')
                    and self._pointer_job not in self._inflight and len(self._inflight)<self.translation_workers):
                track_id,state=pending[0]
                source_key=(state.line['source_lang'],state.line['text'],self._result_epoch)
                if not self.persist_results or source_key not in self._inflight.values():
                    state.attempted=True
                    key=(self.generation,track_id,state.revision)
                    self._pointer_job=self.pointer_pool.submit(self._translate,key,dict(state.line),
                                                               self._translation_epoch,self._result_epoch)
                    self._inflight[self._pointer_job]=source_key
                    pending=pending[1:]
            if self.persist_results:
                pending=[pair for pair in pending if (pair[1].line['source_lang'],pair[1].line['text'],
                                                      self._result_epoch) not in self._inflight.values()]
            screen=getattr(self.engine,'translate_screen',None)
            if (self.persist_results and screen and not getattr(self.engine,'offline_only',False)
                    and len(pending)>1 and not any(state.separate for _,state in pending)
                    and len(self._inflight)<self.translation_workers):
                visible=[state.line for state in self._states.values() if state.visible and not state.line.get('_preserve_source')]
                budget=self.engine.screen_budget()
                if sum(2*len(row['text'])+40 for row in visible)+768<=budget:
                    pending.sort(key=lambda pair:(pair[1].line['y'],pair[1].line['x']))
                    jobs=[((self.generation,track_id,state.revision),dict(state.line)) for track_id,state in pending]
                    waiting={track_id for track_id,state in pending}
                    other='\n'.join(s.line['text'] for i,s in self._states.items() if s.visible and i not in waiting and not s.line.get('_preserve_source'))
                    for _,state in pending:state.attempted=True
                    future=self.pool.submit(self._translate_screen,jobs,other,self._translation_epoch,self._result_epoch)
                    self._inflight[future]=('screen',self.generation,self._result_epoch)
                    return
            for track_id, state in pending:
                if len(self._inflight) >= self.translation_workers:
                    break
                source_key=state.line['source_lang'],state.line['text'],self._result_epoch
                if self.persist_results and source_key in self._inflight.values():
                    continue
                priority = (self.pointer_pool and state.line.get('_pointer_priority')
                            and self._pointer_job not in self._inflight)
                if (self.pointer_pool and not priority and self.translation_workers>1
                        and self._pointer_job not in self._inflight
                        and len(self._inflight)>=self.translation_workers-1):
                    continue  # Reserve at most one slot for the next pointed row.
                key = (self.generation, track_id, state.revision)
                state.attempted = True
                worker = self.pointer_pool if priority else self.pool
                future = worker.submit(self._translate, key, dict(state.line),self._translation_epoch,self._result_epoch)
                if priority:
                    self._pointer_job = future
                self._inflight[future] = source_key
            if (self._refresh_active and self._refresh_observed and not self._refresh_pending
                    and not self._inflight and all(state.attempted or not state.visible
                                                  for state in self._states.values())):
                self._refresh_active = False

    def _translate_screen(self,jobs,neighbors,epoch,result_epoch):
        game,source,target,context=self._scope
        def progress(i,text):
            key=jobs[i][0]
            with self._state_lock:
                state=self._state_for_locked(key)
                if state and state.visible and self._result_epoch==result_epoch:
                    self._emit_translation_locked(key[0],key[1],state,text,False)
        try:
            values=self.engine.translate_screen(game,source,target,[row for _,row in jobs],context,
                                                self.warmup_scope,self.game_executable,neighbors=neighbors,on_block=progress)
        except RetryableTranslationError:
            values=None
        except Exception as error:
            with self._state_lock:
                for key,_ in jobs:
                    state=self._state_for_locked(key)
                    if state and state.visible:
                        state.error=str(error) if isinstance(error,TranslationError) else '\u8be5\u6587\u5b57\u6846\u7ffb\u8bd1\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u914d\u7f6e\u6216\u7a0d\u540e\u91cd\u8bd5\u3002'
                        self.emit(('line_error',key[0],(key[1],key[2],state.error)))
            return
        if values is None:
            with self._state_lock:
                for key,_ in jobs:
                    state=self._state_for_locked(key)
                    if state:state.separate=True;state.attempted=False
            return
        for (key,row),value in zip(jobs,values):
            with self._state_lock:
                if result_epoch!=self._result_epoch or self.stop_event.is_set():return
            self._translate(key,row,epoch,result_epoch,completed=value)

    def _state_for_locked(self, key):
        session, track_id, revision = key
        if self.stop_event.is_set() or session != self.generation:
            return None
        state = self._states.get(track_id)
        return state if state and state.revision == revision and not state.line.get('_preserve_source') else None

    def _translation_line(self, source, revision, text, final):
        raw = text
        same_text = unchanged_translation(source['text'], text)
        unchanged = bool(final and same_text)
        if same_text:
            text = ''
        if source.get('_flow_layout') and not source.get('_fixed_layout'):
            text = reflow_translation(text, final)
        line = {**source, 'text': label_translation(text, source['source_lang'], final, label_language=self.label_language,
                show_source_label=self.show_source_label and (
                    not self.source_label_mixed_only or bool(source.get('_label_mixed'))),
                show_translation_brackets=self.show_translation_brackets), 'final': final,
                '_revision': revision}
        if final and not same_text:
            line['_raw_translation'] = raw
        if unchanged:
            line['_translation_unchanged'] = True
        return line

    def _emit_translation_locked(self, session, track_id, state, text, final):
        if state.line.get('_center_label') and not final:
            return
        line=self._translation_line(state.line,state.revision,text,final)
        self.emit(('translation', session,
                   (track_id, line, state.line['text'], final)))

    def _translate(self, key, snapshot, epoch, result_epoch,completed=None):
        original,source=snapshot['text'],snapshot['source_lang']
        with self._state_lock:
            state = self._state_for_locked(key)
            if self.stop_event.is_set():
                return
            if not self.persist_results and (state is None or not state.visible):
                # It may reappear before an expired ID is discarded.
                if state is not None:
                    state.attempted = False
                return
        game, _, target, context = self._scope
        def chunk(text):
            # Local dictionary/cache results are already complete. Emitting an
            # artificial partial then appending ']' on final can momentarily
            # cross a wrap threshold and make the native fitted font flicker.
            if getattr(self.engine, 'offline_only', False):
                return
            with self._state_lock:
                state = self._state_for_locked(key)
                if state is not None:
                    state.output = (text, False)
                    if state.visible:
                        self._emit_translation_locked(key[0], key[1], state, text, False)
        try:
            options = {'warmup_scope':self.warmup_scope} if self.warmup_scope is not None else {}
            if self.game_executable:
                options['game_executable'] = self.game_executable
            if epoch is not None:
                options['request_epoch'] = epoch
            try:
                translated = completed if completed is not None else self.engine.translate(game, source, target, original, chunk, context, **options)
            except RetryableTranslationError:
                with self._state_lock:
                    if not self.persist_results or self.stop_event.is_set() or result_epoch!=self._result_epoch:
                        raise
                    self._quality_pending=True
                    self._capture_wake.set()
                translated = self.engine.translate(game, source, target, original, chunk, context, **options)
            with self._state_lock:
                if self.stop_event.is_set():
                    return
                state = self._state_for_locked(key)
                if state is not None:
                    state.output = (translated, True)
                    if state.visible:
                        self._emit_translation_locked(key[0], key[1], state, translated, True)
                if self.persist_results:
                    current_epoch=result_epoch==self._result_epoch
                    if current_epoch and max(len(original),len(translated))<=8192:
                        source_key=(source,original)
                        self._recent_outputs[source_key]=translated
                        self._recent_outputs.move_to_end(source_key)
                        if len(self._recent_outputs)>96:
                            self._recent_outputs.popitem(last=False)
                    shown=bool(state and state.visible)
                    if current_epoch:
                        for identity,other in self._states.items():
                            if (other is not state and other.visible and not other.attempted
                                    and not other.line.get('_preserve_source')
                                    and (other.line['source_lang'],other.line['text'])==(source,original)):
                                other.attempted=True
                                other.output=(translated,True)
                                self._emit_translation_locked(self.generation,identity,other,translated,True)
                                shown=True
                    if not shown and not self.lightweight and not unchanged_translation(original,translated):
                        line=self._translation_line(snapshot,key[2],translated,True)
                        self.emit(('late_translation',self.generation,
                                   (self,key[1],line,original,current_epoch and key[0]==self.generation)))
        except Exception as exc:
            # Provider/OS exceptions may contain private text, headers or paths.
            # Only the translator's explicitly controlled diagnostics cross UI.
            message = (str(exc)[:500] if isinstance(exc, TranslationError) else
                       '\u8be5\u6587\u5b57\u6846\u7ffb\u8bd1\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u914d\u7f6e\u6216\u7a0d\u540e\u91cd\u8bd5\u3002')
            with self._state_lock:
                state = self._state_for_locked(key)
                if state is not None:
                    state.output = None
                    state.error = message
                    if state.visible:
                        self.emit(('line_error', key[0], (key[1], key[2], message)))

    def get_stats(self):
        with self._state_lock:
            visible = [state for state in self._states.values() if state.visible]
            return {'objects': len(visible),
                    'preserved_source': sum(bool(state.line.get('_preserve_source')) for state in visible),
                    'pending': sum(not state.attempted for state in visible),
                    'inflight': sum(not future.done() for future in self._inflight),
                    'queue_drops': self._queue_drops,
                    'refresh_pending': self._refresh_active,
                    'observation_queue': self._observations.qsize(),
                    'tracking_workers': self.tracking_workers,
                    'translation_workers': self.translation_workers}

    def stop(self):
        if hasattr(self.core,'set_source_change_callback'):self.core.set_source_change_callback(None)
        if hasattr(self.core,'set_ready_callback'):self.core.set_ready_callback(None)
        with self._state_lock:
            if not self.stop_event.is_set():
                self.stop_event.set()
                self._capture_wake.set()
                self._refresh_pending = self._refresh_active = False
                self.generation = _next_generation()
                self._states.clear()
                self.emit(('clear', self.generation, None))
            self.pool.shutdown(wait=False, cancel_futures=True)
            if self.pointer_pool is not None:
                self.pointer_pool.shutdown(wait=False,cancel_futures=True)
        if hasattr(self.core,'cancel_pending'):self.core.cancel_pending()
        self.core.hide_overlay()
        if self.coordinator_thread is None:
            self.tracker.close()

    def join(self, timeout=2):
        deadline = time.monotonic() + max(0., timeout)
        for worker in (self.thread, self.coordinator_thread):
            if worker is not None:
                worker.join(max(0., deadline - time.monotonic()))
        return not self.alive
