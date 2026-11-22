# SPDX-License-Identifier: MIT
"""Stable identities for OCR rectangles, not objects inside a game process.

One coordinator serializes snapshots. A fixed, bounded worker pool scores
existing tracks against each snapshot; only the coordinator assigns identities
and publishes state. These are small Python association tasks, not parallel OCR
or a claim of CPU speedup under the GIL.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import math
import threading
from types import MappingProxyType
from typing import Mapping
import unicodedata
from .literal_rules import literal_ranges


def _text_key(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).replace('\r\n', '\n').replace('\r', '\n')
    # OCR spacing changes do not revise content, but explicit line breaks matter.
    return '\n'.join(' '.join(row.split()) for row in text.split('\n')).strip()


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class TextTrack:
    track_id: int
    revision: int
    line: Mapping
    visible: bool


@dataclass(frozen=True)
class TrackingUpdate:
    tracks: list[TextTrack]
    removed_ids: list[int]
    changed_ids: list[int]


@dataclass(frozen=True)
class _Observation:
    line: Mapping
    key: str
    box: tuple[float, float, float, float]
    literals: tuple[str, ...] = ()


@dataclass(frozen=True)
class _State:
    public: TextTrack
    observation: _Observation
    missing: int = 0
    pending_key: str = ''
    motion: tuple[float, float] | None = None


def _minor_ocr_edit(before, after):
    """Debounce a 1-2 character interior OCR error, never typed suffixes/numbers."""
    if not (10 <= min(len(before), len(after)) <= max(len(before), len(after)) <= 512):
        return False
    if before.startswith(after) or after.startswith(before):
        return False
    if before.count('\n') != after.count('\n'):
        return False
    if [c for c in before if c.isdigit()] != [c for c in after if c.isdigit()]:
        return False
    left = 0
    while left < min(len(before), len(after)) and before[left] == after[left]:
        left += 1
    right = 0
    while right < min(len(before)-left, len(after)-left) and before[-right-1] == after[-right-1]:
        right += 1
    return max(len(before)-left-right, len(after)-left-right) <= 2


def _similarity(first: str, second: str) -> float:
    if first == second:
        return 1.0
    # Keep small edits to long/repetitive dialogue out of SequenceMatcher. Trim
    # known common edges BEFORE sampling; sampling first moves its suffix window
    # after an appended character and needlessly makes the entire sample differ.
    bounded = lambda s: s if len(s) <= 4096 else s[:2048] + s[-2048:]
    first, second = bounded(first), bounded(second)
    first_length, second_length = len(first), len(second)
    total = first_length + second_length
    if not total:
        return 1.0
    prefix = 0
    while prefix < min(first_length, second_length) and first[prefix] == second[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < min(first_length - prefix, second_length - prefix)
           and first[first_length - suffix - 1] == second[second_length - suffix - 1]):
        suffix += 1
    left = first[prefix:first_length - suffix]
    right = second[prefix:second_length - suffix]
    edge_matches = prefix + suffix
    if not left or not right:
        return 2.0 * edge_matches / total
    # Association is heuristic. Very large unmatched middles are sampled to
    # bound repetitive-text worst cases; content revisions still compare the
    # complete normalized strings, so sampling cannot hide a content change.
    sample = lambda s: s if len(s) <= 256 else s[:128] + s[-128:]
    middle_ratio = SequenceMatcher(None, sample(left), sample(right), autojunk=False).ratio()
    middle_total = len(left) + len(right)
    middle_ratio = min(middle_ratio, 2.0 * min(len(left), len(right)) / middle_total)
    return (2.0 * edge_matches + middle_ratio * middle_total) / total


def _identity(observation):
    return (observation.line.get('_selection_id',0),observation.line.get('source_lang',''),observation.key)


def _scroll_evidence(previous, observations):
    """Use unique source text anchors to disambiguate scrolling repeated rows.

    Evidence is local to an aligned column/selection and needs two agreeing
    anchors. No inferred motion is used to draw pixels without a fresh box.
    """
    old_count=Counter(_identity(state.observation) for state in previous)
    new_count=Counter(_identity(item) for item in observations)
    unique={key for key,count in old_count.items() if count==1 and new_count[key]==1}
    new={_identity(item):item for item in observations if _identity(item) in unique}
    anchors=[]
    for state in previous:
        old=state.observation;key=_identity(old)
        if key not in unique or state.missing:continue
        current=new[key];a,b=old.box,current.box
        if min(a[2],b[2])/max(a[2],b[2])<.55 or min(a[3],b[3])/max(a[3],b[3])<.55:continue
        anchors.append((old,(b[0]-a[0],b[1]-a[1])))
    hints={}
    for state in previous:
        box=state.observation.box;selection=state.observation.line.get('_selection_id',0)
        eligible=[]
        for anchor,delta in anchors:
            a=anchor.box
            overlap=max(0.,min(box[0]+box[2],a[0]+a[2])-max(box[0],a[0]))
            if (anchor.line.get('_selection_id',0)==selection and
                    (overlap>=.55*min(box[2],a[2]) or abs(box[0]-a[0])<=max(8.,.6*min(box[3],a[3])))):
                eligible.append(delta)
        clusters=[]
        for delta in eligible:
            supporters=[d for d in eligible if max(abs(d[i]-delta[i]) for i in (0,1))<=2.]
            clusters.append((len(supporters),delta,supporters))
        if clusters:
            count,_,supporters=max(clusters,key=lambda item:(item[0],-math.hypot(*item[1])))
            if count>=1 and count>len(eligible)/2:
                delta=tuple(sum(d[i] for d in supporters)/count for i in (0,1))
                # A scroll can crop all but one unique anchor. A duplicate row
                # at its precisely predicted position is independent spatial
                # corroboration; nearest-old-slot matching is not evidence.
                corroborating=0
                for old in previous:
                    a=old.observation
                    if old.missing or a.line.get('_selection_id',0)!=selection:continue
                    if abs(a.box[0]-box[0])>max(8.,.6*min(a.box[3],box[3])):continue
                    if any(_identity(a)==_identity(b) and
                           max(abs((b.box[i]-a.box[i])-delta[i]) for i in (0,1))<=2 for b in observations):
                        corroborating+=1
                if max(map(abs,delta))>=2 and (count>=2 or corroborating>=2):
                    hints[state.public.track_id]=delta
    return unique,hints


def _score_candidates(state: _State, observations: tuple[_Observation, ...], unique=frozenset(), motion=None) -> list[float]:
    ax, ay, aw, ah = state.observation.box
    if motion is not None:ax+=motion[0];ay+=motion[1]
    result = []
    for observation in observations:
        if state.observation.line.get('_selection_id',0) != observation.line.get('_selection_id',0):
            result.append(-1.)
            continue
        bx, by, bw, bh = observation.box
        left, top = max(ax, bx), max(ay, by)
        right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        intersection = max(0., right - left) * max(0., bottom - top)
        union = aw * ah + bw * bh - intersection
        overlap = intersection / union if union else 0.
        dx, dy = abs(ax + aw / 2 - bx - bw / 2), abs(ay + ah / 2 - by - bh / 2)
        relative_distance = math.hypot(dx / max(aw, bw), dy / max(ah, bh))
        exact = state.observation.key == observation.key
        unique_exact=exact and _identity(state.observation)==_identity(observation) and _identity(observation) in unique
        same_place = overlap >= .20 or relative_distance <= .80
        same_text_nearby = exact and dx <= max(180., 4 * max(aw, bw)) and dy <= max(160., 4 * max(ah, bh))
        # Fuzzy similarity cannot make a distant pair eligible. Reject it before
        # SequenceMatcher, whose cost can grow sharply on repetitive paragraphs.
        if not same_place and not same_text_nearby and not unique_exact and relative_distance > 1.8:
            result.append(-1.)
            continue
        similarity = _similarity(state.observation.key, observation.key)
        similar_nearby = similarity >= .55 and relative_distance <= 1.8
        if not (same_place or same_text_nearby or similar_nearby or unique_exact):
            result.append(-1.)
            continue
        geometry = .65 * overlap + .35 / (1 + relative_distance * 2)
        # Exact source identity wins over a different row occupying its old
        # screen position. Geometry still separates duplicate strings.
        score = (2.30 if unique_exact else 2.) + .35*geometry if exact else .67*geometry+.30*similarity
        if state.public.visible:
            score += .03
        result.append(score)
    return result


def _assign(scores: list[list[float]], observations: int) -> dict[int, int]:
    """Maximum total score assignment with one private unmatched slot per row.

    Rectangular Hungarian algorithm; at most 32 x 64, independent of worker
    completion order. Stable row/column order resolves equally good matches.
    """
    rows = len(scores)
    if not rows or not observations:
        return {}
    columns = observations + rows
    cost = [[-value for value in row] + [0.] * rows for row in scores]
    u, v = [0.] * (rows + 1), [0.] * (columns + 1)
    assigned, way = [0] * (columns + 1), [0] * (columns + 1)
    for row in range(1, rows + 1):
        assigned[0] = row
        column = 0
        minimum, used = [math.inf] * (columns + 1), [False] * (columns + 1)
        while True:
            used[column] = True
            current_row = assigned[column]
            delta, next_column = math.inf, 0
            for candidate in range(1, columns + 1):
                if used[candidate]:
                    continue
                value = cost[current_row - 1][candidate - 1] - u[current_row] - v[candidate]
                if value < minimum[candidate]:
                    minimum[candidate], way[candidate] = value, column
                if minimum[candidate] < delta:
                    delta, next_column = minimum[candidate], candidate
            for candidate in range(columns + 1):
                if used[candidate]:
                    u[assigned[candidate]] += delta
                    v[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if assigned[column] == 0:
                break
        while True:
            previous = way[column]
            assigned[column] = assigned[previous]
            column = previous
            if column == 0:
                break
    return {assigned[column] - 1: column - 1 for column in range(1, observations + 1)
            if assigned[column] and scores[assigned[column] - 1][column - 1] > 0.}


class ObjectTracker:
    """Bounded frame association with stable IDs and per-object text revisions.

    ``origin`` is the selected capture area's screen position. Subtracting it
    from matching coordinates allows moving the whole game window without
    assigning new identities. ``line`` in returned tracks stays screen-relative.
    """
    def __init__(self, workers=2, max_tracks=32, max_missing=2):
        self.workers = min(4, max(1, int(workers)))
        self.max_tracks = min(128, max(1, int(max_tracks)))
        self.max_missing = min(30, max(0, int(max_missing)))
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='text-track')
        self._update_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._states: dict[int, _State] = {}
        self._next_id = 1
        self._closed = False

    def _observations(self, lines, origin):
        ox, oy = map(float, origin)
        if not math.isfinite(ox) or not math.isfinite(oy):
            raise ValueError('Tracking origin must contain finite coordinates')
        observations = []
        for source in lines:
            line = dict(source)
            line.pop('_content_motion',None)
            text = str(line.get('text', ''))
            key = _text_key(text)
            if not key:
                continue
            try:
                x, y, w, h = (float(line[name]) for name in ('x', 'y', 'w', 'h'))
            except (KeyError, ValueError, TypeError):
                continue
            if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
                continue
            line['text'] = text
            originals=tuple(text[item.start:item.end] for item in literal_ranges(text))
            observations.append(_Observation(_freeze(line), key, (x - ox, y - oy, w, h),originals))
        observations.sort(key=lambda item: (item.box[1], item.box[0], item.key, item.box[2], item.box[3]))
        return tuple(observations[:self.max_tracks])

    def update(self, lines: list[dict], origin=(0, 0), *, advance_missing=True) -> TrackingUpdate:
        with self._update_lock:
            with self._state_lock:
                if self._closed:
                    raise RuntimeError('ObjectTracker is closed')
                previous = sorted(self._states.values(), key=lambda state: state.public.track_id)
                previous_visible = {state.public.track_id for state in previous if state.public.visible}
            observations = self._observations(lines, origin)
            unique,motions=_scroll_evidence(previous,observations)
            # There are at most max_tracks jobs per update. update() is serialized
            # and waits for them, so work never accumulates across video frames.
            futures = [self._pool.submit(_score_candidates, state, observations, unique,
                                         motions.get(state.public.track_id)) for state in previous] if observations else []
            scores = [future.result() for future in futures]
            assignment = _assign(scores, len(observations))
            reverse = {column: row for row, column in assignment.items()}
            current, changed, visible = {}, [], []
            for column, observation in enumerate(observations):
                pending_key = ''
                motion=None
                if column in reverse:
                    old = previous[reverse[column]]
                    track_id = old.public.track_id
                    literals_changed = old.observation.literals != observation.literals
                    text_changed = old.observation.key != observation.key or literals_changed
                    motion=tuple(observation.box[i]-old.observation.box[i] for i in (0,1))
                    quality_changed = (bool(old.public.line.get('_preserve_source')) != bool(observation.line.get('_preserve_source'))
                                       or old.public.line.get('source_lang')!=observation.line.get('source_lang'))
                    if (text_changed and not literals_changed and not old.missing and old.pending_key != observation.key
                            and not old.public.line.get('_preserve_source') and not observation.line.get('_preserve_source')
                            and old.public.line.get('source_lang') == observation.line.get('source_lang')
                            and old.public.line.get('_selection_id',0) == observation.line.get('_selection_id',0)
                            and max(map(abs,motion))<=2
                            and _minor_ocr_edit(old.observation.key, observation.key)):
                        pending_key = observation.key
                        # Keep the accepted text/revision during one uncertain
                        # observation, while still following geometry/colors.
                        held = {**observation.line, 'text': old.public.line['text']}
                        observation = _Observation(_freeze(held), old.observation.key, observation.box,observation.literals)
                        text_changed = False
                    text_changed = text_changed or quality_changed
                    revision = old.public.revision + int(text_changed)
                    hint=motions.get(track_id)
                    consistent=(old.motion is not None and max(map(abs,motion))>=2
                                and max(abs(motion[i]-old.motion[i]) for i in (0,1))<=1)
                    follows_hint=(hint is not None and max(abs(motion[i]-hint[i]) for i in (0,1))<=2)
                    verified = observation.line.get('_pixel_motion') == motion and any(motion)
                    if not text_changed and (verified or consistent or follows_hint or
                            (_identity(observation) in unique and max(map(abs,motion))>6)):
                        observation=_Observation(_freeze({**observation.line,'_content_motion':motion}),observation.key,
                                                 observation.box,observation.literals)
                else:
                    track_id = self._next_id
                    self._next_id += 1
                    text_changed, revision = True, 1
                public = TextTrack(track_id, revision, observation.line, True)
                current[track_id] = _State(public, observation, pending_key=pending_key,motion=motion)
                visible.append(public)
                if text_changed:
                    changed.append(track_id)
            # Visible observations have priority over old invisible states when
            # capacity is reached. Hidden retained entries never block new text.
            missing = [state for state in previous if state.public.track_id not in current]
            missing.sort(key=lambda state: (state.missing, state.public.track_id))
            for old in missing:
                misses = old.missing + int(advance_missing)
                if misses <= self.max_missing and len(current) < self.max_tracks:
                    public = TextTrack(old.public.track_id, old.public.revision, old.public.line, False)
                    current[public.track_id] = _State(public, old.observation, misses)
            now_visible = {track.track_id for track in visible}
            with self._state_lock:
                self._states = current
            return TrackingUpdate(visible, sorted(previous_visible - now_visible), sorted(changed))

    def get(self, track_id: int) -> TextTrack | None:
        with self._state_lock:
            state = self._states.get(track_id)
            return state.public if state else None

    def reset(self):
        with self._update_lock, self._state_lock:
            if self._closed:
                raise RuntimeError('ObjectTracker is closed')
            self._states.clear()

    def close(self):
        with self._update_lock:
            with self._state_lock:
                if self._closed:
                    return
                self._closed = True
                self._states.clear()
            self._pool.shutdown(wait=True, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
