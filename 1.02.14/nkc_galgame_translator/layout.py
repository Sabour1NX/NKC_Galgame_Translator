# SPDX-License-Identifier: MIT
"""Conservative OCR line grouping for dialogue translation context."""
from __future__ import annotations
import re
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from enum import Enum
from .ocr_regions import has_visual_separator


class _TableEvidence(str, Enum):
    NUMERIC = 'numeric_table_cell'




@dataclass(frozen=True)
class ScreenshotBaselines:
    """Ink rectangles relative to the enclosing overlay, verified on local pixels."""
    rows: tuple


def has_numeric_table_evidence(line):
    # Only a locally created enum survives this identity check. JSON/provider
    # strings cannot assert this provenance; deepcopy retains it internally.
    return line.get('_numeric_column') is _TableEvidence.NUMERIC

class _ColumnEvidence(str, Enum):
    NARRATIVE = 'local_narrative_column'


MAX_PARAGRAPH_LINES = 32
MAX_PARAGRAPH_CHARACTERS = 4000
MAX_PARAGRAPH_SPAN = 4096

_LIST_START = re.compile('^(?:[\u2022\u25cf\u25aa\u25e6\u2023]|[-*+]\\s|\\d{1,3}[.)\u3001]\\s|[([]\\d{1,3}[)\\]]\\s)')
_LIST_PENDING = re.compile('^(?:[-*+]|\\d{1,3}[.)\u3001]?|[([]\\d{0,3}[)\\]]?)$')
_FIELD_START = re.compile('^[^\\W\\d][\\w .\\-\\u3000]{0,24}[:\uff1a]')
_LABEL_WORDS = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’/+_-]*(?: +[A-Za-z0-9][A-Za-z0-9'’/+_-]*){0,2}\Z")
_CONTINUATION_WORDS = frozenset(('a', 'an', 'the', 'and', 'or', 'of', 'to', 'in',
    'on', 'at', 'with', 'for', 'as', 'is', 'was', 'are', 'were', 'your', 'you',
    'we', 'i', 'our', 'their', 'it', 'its', 'he', 'she', 'his', 'her', 'they',
    'this', 'that', 'these', 'those', 'not', 'but', 'if', 'from', 'by', 'into',
    'over', 'under'))
_TABLE_VALUE = re.compile(r'[0-9OoIiLlZzSsBbGgEeAaHh|.,+%\-]{1,6}\Z')


def _structured_line(text):
    """Visible list/field/speaker structure is not an OCR soft wrap."""
    text = text.strip()
    return bool(_LIST_START.match(text) or _FIELD_START.match(text) or '\t' in text)


def _unspaced_character(char):
    # Han/Kana and their punctuation have no inter-word space. Hangul and Latin
    # keep the ordinary space when a physical OCR row wraps between words.
    return ('\u2e80' <= char <= '\u30ff' or '\u31f0' <= char <= '\u31ff'
            or '\u3400' <= char <= '\u9fff' or '\uf900' <= char <= '\ufaff'
            or '\uff01' <= char <= '\uff60' or '\U00020000' <= char <= '\U0003134f')


def reflow_translation(text, final=True):
    """Remove soft row breaks for a locally established narrative paragraph.

    Callers must opt in with locally derived ``_flow_layout``. Blank paragraphs
    and list starts remain breaks; spaces inside an ordinary line are retained.
    A trailing whitespace run or incomplete possible list marker waits for the
    next chunk. Consequently cumulative provider prefixes stay cumulative after
    reflow, instead of resetting native font fitting at each streamed newline.
    Raw translations and dictionary keys are never rewritten by this helper.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    out = []
    cursor = 0
    for whitespace in re.finditer(r'[ \t\n]+', text):
        out.append(text[cursor:whitespace.start()])
        cursor = whitespace.end()
        if cursor == len(text):
            return ''.join(out)  # Wait rather than paint an unstable trailing gap.
        gap = whitespace.group()
        if '\n' not in gap:
            out.append(gap)
            continue
        if not any(out):
            continue
        line_end = text.find('\n', cursor)
        tail = text[cursor:line_end if line_end >= 0 else len(text)]
        if not final and line_end < 0 and _LIST_PENDING.fullmatch(tail):
            return ''.join(out)
        if gap.count('\n') >= 2:
            out.append('\n\n')
        elif _LIST_START.match(tail):
            out.append('\n')
        else:
            previous = next((part[-1] for part in reversed(out) if part), '')
            if not (_unspaced_character(previous) or _unspaced_character(text[cursor])):
                out.append(' ')
    out.append(text[cursor:])
    return ''.join(out)


def _similar_color(first, second, tolerance):
    return len(first) == len(second) == 3 and max(abs(int(a) - int(b)) for a, b in zip(first, second)) <= tolerance


def _compact_label(text):
    """A lexical label candidate, not enough on its own to infer a list."""
    text = text.strip()
    return (len(text) <= 40 and _LABEL_WORDS.fullmatch(text) is not None
            and any(char.isalpha() for char in text)
            and not any(word.lower() in _CONTINUATION_WORDS for word in text.split()))


def _independent_label_rows(ordered):
    """Find bounded vertical label runs, including one missing/selected row.

    At least three compact Latin labels must share a left edge and row height.
    Two single-word labels or an aligned numeric value column establish a list.
    Colors are deliberately ignored here: selection inversion is not a new
    paragraph. This returns identities only and never rewrites caller metadata.
    """
    numeric = [line for line in ordered if any(c.isdigit() for c in line['text'])
               and not any(c.isalpha() for c in line['text'])]
    protected, run = set(), []

    def paired_value(label):
        for value in numeric:
            height = min(float(label['h']), float(value['h']))
            if (height > 0 and max(label['h'], value['h']) <= 1.5 * height
                    and abs(label['y'] + label['h']/2 - value['y'] - value['h']/2) <= .3 * height
                    and value['x'] - label['x'] - label['w'] >= 2 * height
                    and value['w'] <= 4 * height):
                return True
        return False

    def flush():
        if len(run) >= 3 and (sum(len(line['text'].split()) == 1 for line in run) >= 2
                              or any(paired_value(line) for line in run)):
            protected.update(map(id, run))

    for line in ordered[:512]:
        # Numeric values remain in reading order for actual grouping, but do
        # not break evidence for a vertically aligned neighboring label column.
        if any(line is value for value in numeric):
            continue
        candidate = _compact_label(line['text']) and not line.get('_preserve_source')
        if candidate and run:
            first, previous = run[0], run[-1]
            height = min(float(first['h']), float(previous['h']), float(line['h']))
            gap = line['y'] - previous['y'] - previous['h']
            candidate = (height > 0 and max(first['h'], previous['h'], line['h']) <= 1.25 * height
                         and abs(line['x']-first['x']) <= min(12, .35 * height)
                         and -.15 * height <= gap <= 1.6 * height
                         and first.get('source_lang') == line.get('source_lang')
                         and first.get('_capture_origin') == line.get('_capture_origin'))
        if not candidate or len(run) >= MAX_PARAGRAPH_LINES:
            flush()
            run = []
        if _compact_label(line['text']) and not line.get('_preserve_source'):
            run.append(line)
    flush()
    return protected


def _physical_source_row(line, left, top):
    """Relative physical source row; validated ink bounds are optional evidence."""
    result = {key: line[key] for key in ('x', 'y', 'w', 'h')}
    result['x'] -= left
    result['y'] -= top
    # Zero lets the native fixed-row renderer derive the font from actual ink
    # height instead of the legacy paragraph-height cap.
    result['font_size'] = line.get('font_size', 0)
    ink = line.get('_source_ink')
    if (isinstance(ink, (list, tuple)) and len(ink) == 4
            and all(type(value) in (int, float) and math.isfinite(value) for value in ink)):
        x, y, w, h = ink
        if (w > 0 and h > 0 and line['x'] <= x < x+w <= line['x']+line['w']
                and line['y'] <= y < y+h <= line['y']+line['h']):
            result['ink_bounds'] = [x-left, y-top, w, h]
    return result


def mark_table_values(lines):
    """Preserve short numeric-column cells using local row/column geometry.

    Three aligned label/value pairs and two digit-bearing values are required.
    A value is at most six common numeric/OCR-confusion glyphs, four row heights
    wide, with at least three row heights of clear space after its label. This
    excludes ordinary word headers such as Cost. No provider flag or game-name
    vocabulary establishes the table. Source rectangles/text are never changed.
    """
    result = [dict(line) for line in lines]
    bounded = result[:512]
    labels = sorted((line for line in bounded
                     if not line.get('_preserve_source') and _compact_label(line['text'])),
                    key=lambda line: line['y']+line['h']/2)
    centers = [line['y']+line['h']/2 for line in labels]
    pairs = []
    for value in bounded:
        text = value['text'].strip()
        if not _TABLE_VALUE.fullmatch(text) or value['h'] <= 0 or value['w'] > 4*value['h']:
            continue
        # Word-only headers must not become prices merely because their glyphs
        # resemble digits. Two-letter corrupt readings (BE/Hi) remain eligible;
        # longer values need at least one observed digit as local evidence.
        if not any(char.isdigit() for char in text) and sum(char.isalpha() for char in text) > 2:
            continue
        center = value['y']+value['h']/2
        nearby = labels[bisect_left(centers, center-.3*value['h']):
                        bisect_right(centers, center+.3*value['h'])]
        matched = []
        for label in nearby:
            height = min(label['h'], value['h'])
            if (height > 0 and max(label['h'], value['h']) <= 1.5*height
                    and abs(label['y']+label['h']/2-center) <= .3*height
                    and value['x']-label['x']-label['w'] >= 3*height):
                matched.append(label)
        if matched:
            label = max(matched, key=lambda line: line['x']+line['w'])
            pairs.append((label, value))
    groups = []
    for label, value in sorted(pairs, key=lambda pair: (pair[1]['y'], pair[1]['x'])):
        match = None
        for group in reversed(groups):
            first_label, first_value = group[0]
            _, previous_value = group[-1]
            height = min(value['h'], first_value['h'])
            tolerance = min(12, .35*height)
            if (len(group) < MAX_PARAGRAPH_LINES and height > 0
                    and max(value['h'], first_value['h']) <= 1.25*height
                    and 0 < value['y']-previous_value['y'] <= 3.2*height
                    and abs(label['x']-first_label['x']) <= tolerance
                    and abs(value['x']+value['w']-first_value['x']-first_value['w']) <= tolerance):
                match = group
                break
        if match is None:
            groups.append([(label, value)])
        else:
            match.append((label, value))
    for group in groups:
        if len(group) < 3 or sum(any(char.isdigit() for char in value['text'])
                                for _, value in group) < 2:
            continue
        for _, value in group:
            value['_numeric_column'] = _TableEvidence.NUMERIC
            if not value.get('_preserve_source'):
                value.update(_preserve_source=True, _ocr_rejection_reason='numeric_table_cell')
    return result


def _adjacent(first, previous, current):
    """Only neighboring, left-aligned rows with matching visual style join."""
    if any(line.get('_preserve_source') for line in (first,previous,current)) or has_visual_separator(current):
        return False
    if any(line.get('_layout_cell') for line in (first,previous,current)):
        if not (all(line.get('_column_evidence') is _ColumnEvidence.NARRATIVE for line in (first,previous,current))
                and first.get('_column_id')==previous.get('_column_id')==current.get('_column_id')):
            return False
    if any(_structured_line(line['text']) for line in (first, previous, current)):
        return False
    if (first.get('source_lang') != current.get('source_lang')
            or first.get('_capture_origin') != current.get('_capture_origin')):
        return False
    h0, h1, h2 = float(first["h"]), float(previous["h"]), float(current["h"])
    if min(h0, h1, h2) <= 0 or max(h0, h1, h2) > 1.25 * min(h0, h1, h2):
        return False
    if abs(float(current["x"]) - float(first["x"])) > min(12, .35 * min(h0, h2)):
        return False
    gap = float(current["y"]) - (float(previous["y"]) + h1)
    if not -.15 * min(h1, h2) <= gap <= .55 * min(h1, h2):
        return False
    # A short sentence-ending row followed by a fresh full-width sentence
    # is paragraph evidence; punctuation alone never splits normal wrapping.
    closing=previous['text'].rstrip().rstrip('\"”’\u300d\u300f)')
    next_letter=next((char for char in current['text'] if char.isalpha()),'')
    if (closing.endswith(('.', '!', '?', '\u3002', '\uff01', '\uff1f'))
            and previous['w']<.65*max(first['w'],current['w'])
            and current['w']>.8*first['w'] and next_letter.isupper()
            and gap>=.08*min(h1,h2)):
        return False
    if not _similar_color(first.get("bg", [0, 0, 0]), current.get("bg", [0, 0, 0]), 20):
        return False
    if not _similar_color(first.get("fg", [255, 255, 255]), current.get("fg", [255, 255, 255]), 28):
        return False
    return True


def _horizontal_narrative(first, second, neighbor):
    """Repair same-baseline dialogue fragments only with adjacent paragraph evidence.

    A nearby full-width row must support the union. This deliberately excludes
    standalone labels, title-cased button grids and ordinary separate columns.
    """
    if neighbor is None or first.get('source_lang') != second.get('source_lang'):
        return None
    if any(line.get('_preserve_source') or line.get('_layout_cell') for line in (first, second, neighbor)):
        return None
    if any('\n' in line['text'] or '\r' in line['text'] for line in (first, second)):
        return None
    if first.get('_capture_origin') != second.get('_capture_origin'):
        return None
    height = min(float(first['h']), float(second['h']))
    if height <= 0 or max(first['h'], second['h']) > 1.15 * height:
        return None
    if abs(first['y'] - second['y']) > .12 * height:
        return None
    gap = second['x'] - first['x'] - first['w']
    if not 0 <= gap <= 2 * height or min(first['w'], second['w']) < 6 * height:
        return None
    if not _similar_color(first.get('bg', [0, 0, 0]), second.get('bg', [0, 0, 0]), 12):
        return None
    if not _similar_color(first.get('fg', [255, 255, 255]), second.get('fg', [255, 255, 255]), 20):
        return None
    left_text, right_text = first['text'].rstrip(), second['text'].lstrip()
    # Lower-case continuation and several words on each side are conservative
    # narrative evidence; do not infer this from a specific game's vocabulary.
    first_letter = next((char for char in right_text if char.isalpha()), '')
    japanese_continuation=(first.get('source_lang')=='ja' and left_text.endswith('\u3001')
                           and len(left_text)>=5 and len(right_text)>=6
                           and any('\u3041'<=c<='\u30ff' for c in right_text))
    if not japanese_continuation and (len(left_text)<12 or len(right_text)<10 or len(left_text.split())<2
                                     or len(right_text.split())<2 or not first_letter.islower()):
        return None
    text=left_text+('' if japanese_continuation else ' ')+right_text
    top = min(first['y'], second['y'])
    width = second['x'] + second['w'] - first['x']
    if not 16 * height <= width <= MAX_PARAGRAPH_SPAN or len(text) > MAX_PARAGRAPH_CHARACTERS:
        return None
    merged = {**first, 'text': text, 'y': top, 'w': width,
              'h': max(first['y'] + first['h'], second['y'] + second['h']) - top}
    # A row assembled from two OCR fragments cannot inherit only the left
    # fragment's ink extent. Keep ink evidence only when both parts have it.
    merged.pop('_source_ink', None)
    inks = [_physical_source_row(line, 0, 0).get('ink_bounds') for line in (first, second)]
    if all(inks):
        ink_left = min(ink[0] for ink in inks)
        ink_top = min(ink[1] for ink in inks)
        merged['_source_ink'] = [ink_left, ink_top,
            max(ink[0]+ink[2] for ink in inks)-ink_left,
            max(ink[1]+ink[3] for ink in inks)-ink_top]
    if neighbor['w'] < .75 * width:
        return None
    if neighbor['y'] > top:
        supported = _adjacent(merged, merged, neighbor)
    else:
        supported = _adjacent(neighbor, neighbor, merged)
    return merged if supported else None


def _join_horizontal_fragments(ordered):
    result = []
    index = 0
    while index < len(ordered):
        merged = None
        if index + 1 < len(ordered):
            first, second = ordered[index:index+2]
            neighbors = [result[-1] if result else None,
                         ordered[index+2] if index+2 < len(ordered) else None]
            for neighbor in neighbors:
                merged = _horizontal_narrative(first, second, neighbor)
                if merged is not None:
                    break
        result.append(merged if merged is not None else ordered[index])
        index += 2 if merged is not None else 1
    return result


def _column_reading_order(ordered):
    """Keep strong prose chains together despite interleaved neighboring columns.

    Three physical rows, sufficient prose and a clear nonintersecting rectangle
    are required. Short labels retain original order and cell independence.
    This produces local-only evidence, never accepts provider grouping flags.
    """
    for row in ordered:
        row.pop('_column_evidence',None);row.pop('_column_id',None)
    chains=[]
    for row in ordered:
        candidates=[]
        for chain in chains:
            probe=[{k:v for k,v in item.items() if k!='_layout_cell'} for item in (chain[0],chain[-1],row)]
            if not _adjacent(*probe):continue
            left=min(row['x'],*(item['x'] for item in chain));right=max(row['x']+row['w'],*(item['x']+item['w'] for item in chain))
            top=chain[0]['y'];bottom=row['y']+row['h']
            members={id(item) for item in chain}|{id(row)}
            # No chain may span another text object, including a short price,
            # subtitle, rejected row or unknown object in a picture.
            if any(id(other) not in members and max(left,other['x'])<min(right,other['x']+other['w'])
                   and max(top,other['y'])<min(bottom,other['y']+other['h']) for other in ordered):continue
            candidates.append(chain)
        if len(candidates)==1:candidates[0].append(row)
        else:chains.append([row])
    bundles={};claimed=set()
    for number,chain in enumerate(chains):
        if (len(chain)<3 or sum(len(row['text'].split()) for row in chain)<9
                or all(_compact_label(row['text']) for row in chain)
                or not any(row['w']>=8*row['h'] for row in chain)):
            continue
        for row in chain:
            row['_column_evidence']=_ColumnEvidence.NARRATIVE;row['_column_id']=number
        bundles[id(chain[0])]=chain
        claimed.update(id(row) for row in chain[1:])
    output=[]
    for row in ordered:
        if id(row) in claimed:continue
        output.extend(bundles.get(id(row),[row]))
    return output


def merge_dialogue_lines(lines):
    """Return copied regions, joining bounded continuous dialogue paragraphs.

    Reading-order neighbors alone may merge: an intervening second column stops
    a group. Larger menu gaps, different colors/heights and indented rows stay
    separate. A whole run of compact labels stays separate as ambiguous buttons.
    Two long same-baseline fragments can first rejoin with a space when a
    lowercase continuation and an adjacent spanning row establish narrative.
    Existing multiline regions are retained without rewriting their hard
    newlines. Lists and field/speaker rows stay separate. New narrative groups
    retain source newlines for cache compatibility and mark ``_flow_layout``
    as narrative provenance. ``_source_rows`` retains the original physical
    rectangles for fixed-row rendering; it does not add space between rows.
    Locally separated OCR cells and compact label runs remain independent. Groups are
    bounded by 32 rows, 4000 characters and a 4096-pixel union. Font size stays
    based on the original single-row height, not the resulting block height.
    """
    ordered = sorted((dict(line) for line in lines), key=lambda line: (line["y"], line["x"]))
    ordered = _join_horizontal_fragments(ordered)
    ordered = _column_reading_order(ordered)
    independent_rows = _independent_label_rows(ordered)
    result = []
    group = []
    characters = 0

    def flush():
        if not group:
            return
        if len(group) == 1 or all(float(line["w"]) <= 6 * float(line["h"]) for line in group):
            # Tight OCR bounds for a column of short labels do not establish
            # paragraph context. Prefer independent buttons in that ambiguity.
            result.extend(group)
            return
        left = min(line["x"] for line in group)
        top = min(line["y"] for line in group)
        right = max(line["x"] + line["w"] for line in group)
        bottom = max(line["y"] + line["h"] for line in group)
        first = group[0]
        result.append({**first, "text": "\n".join(line["text"] for line in group),
                       "x": left, "y": top, "w": right - left, "h": bottom - top,
                       "_flow_layout": True,
                       **{name:True for name in ('_flash_hold','_pointer_priority') if any(row.get(name) for row in group)},
                       "_source_rows": [_physical_source_row(line, left, top) for line in group],
                       "font_size": first.get("font_size") or min(30, max(12, int(first["h"]) - 3))})

    for current in ordered:
        already_multiline = "\n" in current["text"] or "\r" in current["text"]
        exceeds_budget = False
        if group:
            left = min(current["x"], *(line["x"] for line in group))
            right = max(current["x"] + current["w"], *(line["x"] + line["w"] for line in group))
            exceeds_budget = (len(group) >= MAX_PARAGRAPH_LINES
                              or characters + 1 + len(current["text"]) > MAX_PARAGRAPH_CHARACTERS
                              or right - left > MAX_PARAGRAPH_SPAN
                              or current["y"] + current["h"] - group[0]["y"] > MAX_PARAGRAPH_SPAN)
        if group and (exceeds_budget or id(current) in independent_rows or id(group[-1]) in independent_rows
                      or already_multiline or "\n" in group[-1]["text"]
                      or "\r" in group[-1]["text"] or not _adjacent(group[0], group[-1], current)):
            flush()
            group = []
            characters = 0
        characters += len(current["text"]) + bool(group)
        group.append(current)
    flush()
    for line in result:
        line.pop('_column_evidence',None);line.pop('_column_id',None)
    return sorted(result,key=lambda line:(line['y'],line['x']))
