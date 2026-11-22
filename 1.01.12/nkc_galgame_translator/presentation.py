# SPDX-License-Identifier: MIT
"""UI-owned overlay state, keyed by tracked object identity and content revision."""
from collections import OrderedDict
from time import monotonic

from .tuning import DEFAULT_TRANSLATION_HOLD_MS

SCROLL_GRACE_SECONDS = .08


def _overlaps(first, second):
    return (max(first['x'], second['x']) < min(first['x'] + first['w'], second['x'] + second['w'])
            and max(first['y'], second['y']) < min(first['y'] + first['h'], second['y'] + second['h']))


def _same_region(first, second):
    return first.get('_selection_id',0) == second.get('_selection_id',0) and _overlaps(first,second)


class OverlayState:
    def __init__(self, *, hold_until_next=False, hold_seconds=DEFAULT_TRANSLATION_HOLD_MS/1000):
        self.hold_until_next = hold_until_next
        self.hold_seconds = hold_seconds
        self.objects = {}
        self.rendered = {}
        self._unchanged = {}
        self._geometry_candidates = {}
        self._history = OrderedDict()
        self._scroll_seen = {}

    def clear(self):
        self.objects.clear()
        self.rendered.clear()
        self._unchanged.clear()
        self._geometry_candidates.clear()
        self._history.clear()
        self._scroll_seen.clear()

    def expire_held(self):
        now = monotonic()
        expired = [key for key, row in self.rendered.items()
                   if any(now >= row[field] for field in ('_scroll_deadline', '_hold_deadline') if field in row)]
        for key in expired:
            del self.rendered[key]
        return bool(expired)

    def discard_changed_sources(self, regions):
        """Clear overlays whose original pixels are gone, including retained rows."""
        affected = {identity for identity, row in self.rendered.items()
                    if any(_overlaps(row, region) for region in regions)}
        affected.update(identity for identity, item in self.objects.items()
                        if any(_overlaps(item['line'], region) for region in regions))
        for identity in affected:
            self.rendered.pop(identity, None)
            self.objects.pop(identity, None)
            self._scroll_seen.pop(identity, None)
        return bool(affected)

    def completed_page(self):
        eligible=[]
        for identity,item in self.objects.items():
            if item['line'].get('_preserve_source') or self._unchanged.get(identity)==item['revision']:
                continue
            line=self.rendered.get(identity,{})
            if (not line.get('final') or line.get('_revision')!=item['revision']
                    or line.get('_hold_previous') or not line.get('_raw_translation')):
                return None
            eligible.append((identity,item,line))
        return sorted(eligible,key=lambda entry:(entry[1]['line']['y'],entry[1]['line']['x'])) or None

    def display_regions(self):
        regions=list(self.rendered.values())
        held = [row for row in regions if row.get('_hold_previous')]
        for key,item in self.objects.items():
            line=item['line']
            if (line.get('_cover_source') and not line.get('_preserve_source') and key not in self.rendered
                    and not any(_same_region(row, line) for row in held)):
                regions.append({**line,'_track_id':key,'_revision':item['revision'],'text':'','final':False})
        return regions

    def _scroll_placeholder(self, identity, row, movers, current, now):
        # Only borrow an observed displacement from a nearby row in the same
        # column and selection. Never integrate a guessed velocity between frames.
        nearby = set()
        for anchor,delta in movers:
            if (anchor.get('_capture_origin') == row.get('_capture_origin')
                    and anchor.get('_selection_id',0) == row.get('_selection_id',0)
                    and abs(anchor['y']-row['y']) <= 4*max(anchor['h'],row['h'])
                    and min(anchor['x']+anchor['w'],row['x']+row['w']) > max(anchor['x'],row['x'])):
                nearby.add(delta)
        if len(nearby)>1:
            return None
        deadline = row.get('_scroll_deadline')
        if deadline is None:
            last = now if nearby else self._scroll_seen.get(identity)
            if last is None:
                return None
            deadline = last + min(SCROLL_GRACE_SECONDS,self.hold_seconds)
        if now >= deadline:
            return None
        dx,dy = next(iter(nearby),(0,0))
        x,y = row['x']+dx,row['y']+dy
        clip = row.get('_scroll_clip')
        if clip and not (clip[0]<=x and clip[1]<=y and x+row['w']<=clip[2] and y+row['h']<=clip[3]):
            return None
        moved = {**row,'x':x,'y':y,'_hold_previous':True,'_scroll_deadline':deadline}
        if '_source_ink' in moved:
            ix,iy,iw,ih=moved['_source_ink']
            moved['_source_ink']=[ix+dx,iy+dy,iw,ih]
        if any(_overlaps(moved,item['line']) for item in current.values()):
            return None
        return moved

    @staticmethod
    def _keep_layout(line, previous, bounds, dx, dy):
        line.update(zip(('x','y','w','h'),bounds))
        for name in ('_source_rows','_source_line_count','font_size'):
            if name in previous:
                line[name] = previous[name]
            else:
                line.pop(name, None)
        if '_source_ink' in previous:
            x,y,w,h = previous['_source_ink']
            line['_source_ink'] = [x+dx,y+dy,w,h]
        else:
            line.pop('_source_ink',None)

    def _stable_geometry(self, identity, line, previous):
        """Reject isolated OCR boxes; follow confirmed changes and window moves.

        A rectangle is accepted as a unit, never a new position with an old
        unconfirmed size. Tiny noise needs three exactly repeated observations;
        larger dimension changes and small moves need three similar boxes.
        Large translations with stable dimensions follow immediately.
        Capture-origin movement is applied before filtering, including on
        negative-coordinate monitors. Colors always follow the observation.
        """
        previous = dict(previous)
        old_origin = previous.get('_capture_origin', (0, 0))
        origin = line.get('_capture_origin', old_origin)
        dx,dy = origin[0]-old_origin[0], origin[1]-old_origin[1]
        previous['x'] += dx
        previous['y'] += dy
        candidates = self._geometry_candidates.setdefault(identity, {})
        fields = ('x', 'y', 'w', 'h')
        old_box = tuple(previous[name] for name in fields)
        current_box = tuple(line[name] for name in fields)
        deltas = tuple(abs(a-b) for a, b in zip(old_box, current_box))
        stable_caption = (line.get('_standalone_subtitle') and previous.get('_standalone_subtitle') or
                          identity in self.rendered and line.get('_subtitle_read') and previous.get('_subtitle_read'))
        if stable_caption:
            old_clip, clip = previous.get('_scroll_clip'),line.get('_scroll_clip')
            if old_clip and clip and (old_clip[2]-old_clip[0],old_clip[3]-old_clip[1]) != (
                    clip[2]-clip[0],clip[3]-clip[1]):
                candidates.clear()
                return line
            if (not line.get('_content_motion') and deltas[0]<=max(6,old_box[2]*.08)
                    and deltas[1]<=max(4,old_box[3]*.27)
                    and deltas[2]<=old_box[2]*.30 and deltas[3]<=old_box[3]*.40):
                self._keep_layout(line,previous,old_box,dx,dy)
                candidates.clear()
                return line
        size_noise = max(deltas[2:]) > 2
        immediate = bool(line.get('_content_motion')) or not size_noise and max(deltas[:2]) > 6
        if not any(deltas) or immediate:
            candidates.pop('box', None)
        else:
            tiny = max(deltas) <= 2
            # Store coordinates relative to the capture origin so moving the
            # game window does not either confirm or discard a size candidate.
            local_box = (current_box[0]-origin[0], current_box[1]-origin[1], *current_box[2:])
            candidate, count, was_tiny = candidates.get('box', (local_box, 0, tiny))
            tolerance = 0 if tiny else 2
            if was_tiny != tiny or any(abs(a-b) > tolerance for a, b in zip(candidate, local_box)):
                candidate, count = local_box, 0
            count += 1
            if count >= 3:
                candidates.pop('box', None)
            else:
                candidates['box'] = (candidate, count, tiny)
                line.update(zip(fields, old_box))
                # Source-row/ink coordinates belong to the accepted rectangle.
                # Do not combine held dimensions with the next OCR frame's rows.
                for name in ('_source_rows', '_source_line_count'):
                    if name in previous:
                        line[name] = previous[name]
                    else:
                        line.pop(name, None)
                if '_source_ink' in previous:
                    ix, iy, iw, ih = previous['_source_ink']
                    line['_source_ink'] = [ix+origin[0]-old_origin[0],
                                           iy+origin[1]-old_origin[1], iw, ih]
                else:
                    line.pop('_source_ink', None)
        # Font size is independent of the coverage rectangle and preserves its
        # established noise filter. Native fitting never enlarges a stream.
        before, current = previous.get('font_size'), line.get('font_size')
        if (isinstance(before, (int, float)) and isinstance(current, (int, float))
                and before > 0 and current > 0):
            if abs(current-before) <= 2:
                line['font_size'] = before
                candidates.pop('font_size', None)
            else:
                candidate, count = candidates.get('font_size', (current, 0))
                if abs(candidate-current) > 2:
                    candidate, count = current, 0
                count += 1
                if count >= 3:
                    candidates.pop('font_size', None)
                else:
                    candidates['font_size'] = (candidate, count)
                    line['font_size'] = before
        return line

    def apply_objects(self, objects, *, manual_refresh=False):
        current = {item['track_id']: {'track_id': item['track_id'],
                    'revision': item['revision'], 'line': dict(item['line'])} for item in objects}
        for identity, revision in list(self._unchanged.items()):
            item = current.get(identity)
            if item is None or item['revision'] != revision or item['line'].get('_preserve_source'):
                del self._unchanged[identity]
        preserved = [item['line'] for item in current.values() if item['line'].get('_preserve_source')]
        for identity, item in current.items():
            previous = self.objects.get(identity) or self._history.get(identity)
            raw = dict(item['line'])
            if not raw.get('_preserve_source') and any(_overlaps(raw, bad) for bad in preserved):
                raw.update(_preserve_source=True, _ocr_rejection_reason='overlapping_rejected_region')
                item['line'] = raw
            if (previous is not None and previous['revision'] == item['revision']
                    and not item['line'].get('_preserve_source') and not previous['line'].get('_preserve_source')):
                self._stable_geometry(identity, item['line'], previous['line'])
                # A previously larger accepted rectangle cannot extend into a
                # newly rejected row just because geometry is being debounced.
                if any(_overlaps(item['line'], bad) for bad in preserved):
                    item['line'] = raw
                    self._geometry_candidates.pop(identity, None)
                # Debouncing must not keep an old rectangle over a neighboring
                # text object that the current raw rectangle already avoids.
                neighbors = (other['line'] for key, other in current.items() if key != identity)
                if any(_overlaps(item['line'], other) and not _overlaps(raw, other) for other in neighbors):
                    item['line'] = raw
                    self._geometry_candidates.pop(identity, None)
            else:
                self._geometry_candidates.pop(identity, None)
            if not item['line'].get('_preserve_source') and any(_overlaps(item['line'], bad) for bad in preserved):
                item['line'].update(_preserve_source=True, _ocr_rejection_reason='overlapping_rejected_region')
            self._history[identity] = item
            self._history.move_to_end(identity)
        # Keep accepted geometry across short OCR dropouts. This history is
        # discarded on scene/session clear and never reused across games.
        while len(self._history) > 64:
            self._history.popitem(last=False)
        for identity in list(self._geometry_candidates):
            if identity not in current:
                del self._geometry_candidates[identity]
        changed = self.expire_held() or current != self.objects
        now = monotonic()
        movers = []
        for key,item in current.items():
            previous = self.objects.get(key)
            row = item['line']
            if previous and row.get('_content_motion') and not row.get('_preserve_source'):
                old = previous['line']
                delta = (row['x']-old['x'],row['y']-old['y'])
                if any(delta) and delta == tuple(row['_content_motion']) and row.get('_capture_origin')==old.get('_capture_origin'):
                    movers.append((row,delta))
                    self._scroll_seen[key]=now
        self._scroll_seen={k:v for k,v in self._scroll_seen.items() if now-v<SCROLL_GRACE_SECONDS}
        content_moved = any(item['line'].get('_content_motion') for item in current.values())
        for identity in list(self.rendered):
            rendered = self.rendered[identity]
            item = current.get(identity)
            if item is None and self.hold_until_next and self.hold_seconds > 0 and not manual_refresh:
                placeholder=self._scroll_placeholder(identity,rendered,movers,current,now)
                if placeholder is not None:
                    self.rendered[identity]=placeholder
                    changed = changed or placeholder!=rendered
                    continue
            if item is None or item['line'].get('_preserve_source') or rendered['_revision'] != item['revision']:
                replacement_here = (item is not None and not item['line'].get('_preserve_source')
                                    and _overlaps(rendered,item['line']))
                can_hold = (item is None or replacement_here) and '_scroll_deadline' not in rendered
                if (self.hold_until_next and self.hold_seconds > 0 and can_hold
                        and not content_moved and rendered['final'] and str(rendered.get('text','')).strip()
                        and not any(_overlaps(rendered,bad) for bad in preserved)):
                    if '_hold_deadline' not in rendered:
                        self.rendered[identity] = {**rendered,'_hold_previous':True,
                                                   '_hold_deadline':now+self.hold_seconds}
                        changed = True
                    continue
                del self.rendered[identity]
                changed = True
            else:
                # Translate once, following the latest accepted geometry and
                # current background without exposing raw OCR pixel jitter.
                updated = {**item['line'], 'text': rendered['text'],
                           'final': rendered['final'], '_revision': item['revision'], '_track_id': identity}
                if '_raw_translation' in rendered:
                    updated['_raw_translation']=rendered['_raw_translation']
                changed = changed or updated != rendered
                self.rendered[identity] = updated
        self.objects.clear()
        self.objects.update(current)
        return changed

    def apply_translation(self, identity, line):
        item = self.objects.get(identity)
        if item is None or item['line'].get('_preserve_source') or item['revision'] != line.get('_revision'):
            return False
        previous = self.rendered.get(identity)
        final = bool(line.get('final', False))
        if not final and (self._unchanged.get(identity) == item['revision']
                          or previous and previous['final'] and not previous.get('_hold_previous')):
            return False
        if line.get('_translation_unchanged'):
            if not final:
                return False
            self._unchanged[identity] = item['revision']
            replaced = self._replace_held(identity, item['line'])
            removed = self.rendered.pop(identity, None) is not None
            return replaced or removed
        if final:
            self._unchanged.pop(identity, None)
        region = {**item['line'], 'text': str(line['text']),
                  'final': final, '_revision': item['revision'], '_track_id': identity}
        if final and '_raw_translation' in line:
            region['_raw_translation']=line['_raw_translation']
        has_text = bool(region['text'].strip())
        if not has_text and any(row.get('_hold_previous') and (key==identity or _same_region(row,region))
                                for key,row in self.rendered.items()):
            return False
        replaced = self._replace_held(identity, region) if has_text else False
        self.rendered[identity] = region
        return replaced or region != previous

    def _replace_held(self, identity, region):
        replaced = False
        for key, held in list(self.rendered.items()):
            if (held.get('_hold_previous') and (key == identity or (
                    held.get('_source_stamp',0.) <= region.get('_source_stamp',0.)
                    and _same_region(held,region)))):
                del self.rendered[key]
                replaced = True
        return replaced

    def apply_late(self,identity,line):
        """Only a currently visible, matching source revision can accept output."""
        if not self.hold_until_next:
            return False
        return self.apply_translation(identity,line)

    def remove_error(self, identity, revision):
        item = self.objects.get(identity)
        if item is None or item['revision'] != revision:
            return False
        if self.hold_until_next:
            return False
        return self.rendered.pop(identity, None) is not None
