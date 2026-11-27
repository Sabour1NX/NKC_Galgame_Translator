# SPDX-License-Identifier: MIT
"""Bounded game-client selections, one capture, explicit grouping boundaries."""
from dataclasses import dataclass

MAX_REGIONS = 8


def overlaps(a, b):
    return max(a[0], b[0]) < min(a[0]+a[2], b[0]+b[2]) and max(a[1], b[1]) < min(a[1]+a[3], b[1]+b[3])


def _ink_regions(line):
    x, y, w, h = (line[name] for name in ('x', 'y', 'w', 'h'))
    rows = line.get('_source_rows')
    if rows:
        for row in rows:
            rx, ry, rw, rh = row.get('ink_bounds') or tuple(row[name] for name in ('x', 'y', 'w', 'h'))
            yield x + rx, y + ry, rw, rh
    else:
        yield line.get('_source_ink') or (x, y, w, h)


def _layer_conflict(region, text, occupied):
    x, y, w, h = region
    intersections = []
    for (px, py, pw, ph), previous in occupied:
        left, top = max(x, px), max(y, py)
        width, height = min(x+w, px+pw)-left, min(y+h, py+ph)-top
        if width <= 0 or height <= 0:
            continue
        common = (left, top, width, height)
        if previous == text and width*height >= .7*max(w*h, pw*ph):
            return True
        if any(overlaps(common, part) for part in intersections):
            return True
        intersections.append(common)
    return False


def limit_two_layers(lines):
    """Count distinct text layers on physical rows, allowing their OCR margins to touch."""
    result = []
    occupied = []
    for line in lines:
        if not line.get('_preserve_source'):
            regions = list(_ink_regions(line))
            if any(_layer_conflict(region, line['text'], occupied) for region in regions):
                continue
            occupied.extend((region, line['text']) for region in regions)
        result.append(line)
    return result


@dataclass(frozen=True)
class CapturePlan:
    bounds: tuple
    regions: tuple


def capture_plan(value):
    """Accept a legacy rectangle or 1..8 nonoverlapping absolute rectangles."""
    if value is None:
        return None
    if not isinstance(value, (tuple, list)):
        raise ValueError('Invalid capture regions')
    boxes = (value,) if len(value) == 4 and all(type(v) is int for v in value) else value
    if not 1 <= len(boxes) <= MAX_REGIONS:
        raise ValueError('Select between 1 and 8 regions')
    checked = []
    for box in boxes:
        if (not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(v) is not int for v in box)
                or not 0 < box[2] <= 4096 or not 0 < box[3] <= 4096
                or any(abs(v) > 1000000 for v in box[:2])):
            raise ValueError('Invalid capture rectangle')
        if any(overlaps(box, other) for other in checked):
            raise ValueError('Capture regions must not overlap')
        checked.append(tuple(box))
    left, top = min(b[0] for b in checked), min(b[1] for b in checked)
    right, bottom = max(b[0]+b[2] for b in checked), max(b[1]+b[3] for b in checked)
    if right-left > 4096 or bottom-top > 4096:
        raise ValueError('Combined capture bounds exceed 4096 pixels')
    return CapturePlan((left, top, right-left, bottom-top),
                       tuple((x-left, y-top, w, h) for x, y, w, h in checked))


def client_selections(relative, client):
    """Clip to the current client area; never capture neighbouring applications."""
    if not relative:
        return client
    boxes = (relative,) if len(relative) == 4 and all(type(v) is int for v in relative) else relative
    result = []
    for x, y, w, h in boxes:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(client[2], x+w), min(client[3], y+h)
        if x1 > x0 and y1 > y0:
            result.append((client[0]+x0, client[1]+y0, x1-x0, y1-y0))
    return tuple(result) or None


def selection_groups(lines):
    groups = {}
    for line in lines:
        groups.setdefault(line.get('_selection_id', 0), []).append(line)
    return groups.values()


def mask_regions(image, regions):
    """Return an owned RGB image; gaps are opaque black, including AI input."""
    from PIL import Image
    if not regions or regions == ((0, 0, image.width, image.height),):
        return image.convert('RGB')
    result = Image.new('RGB', image.size, (0, 0, 0))
    for x, y, w, h in regions:
        if not 0 <= x < x+w <= image.width or not 0 <= y < y+h <= image.height:
            result.close()
            raise ValueError('Selection lies outside capture')
        with image.crop((x, y, x+w, y+h)) as patch:
            result.paste(patch, (x, y))
    return result


def scope_lines(lines, regions):
    if not regions:
        return lines
    result = []
    for line in lines:
        x, y, w, h = (line[k] for k in ('x', 'y', 'w', 'h'))
        for index, (rx, ry, rw, rh) in enumerate(regions):
            if rx <= x < x+w <= rx+rw and ry <= y < y+h <= ry+rh:
                result.append({**line, '_selection_id': index})
                break
    return result
