# SPDX-License-Identifier: MIT
"""Discard superseded stream fragments before the UI renders them."""
from collections import deque
from queue import Empty
from threading import Lock


class DisplayEvents:
    def __init__(self):
        self._items = deque()
        self._partials = {}
        self._lock = Lock()

    def put(self, event):
        kind, generation, payload = event
        with self._lock:
            if kind == 'translation' and not payload[3]:
                track, line, _, _ = payload
                key = (generation, track, line.get('_revision'))
                slot = self._partials.get(key)
                if slot is not None:
                    slot[0] = event
                    return
                slot = [event, key]
                self._partials[key] = slot
            else:
                # Geometry, final results, focus and control events are barriers.
                self._partials.clear()
                slot = [event, None]
            self._items.append(slot)

    def get_nowait(self):
        with self._lock:
            if not self._items:
                raise Empty
            slot = self._items.popleft()
            event, key = slot
            if key is not None and self._partials.get(key) is slot:
                del self._partials[key]
            return event

    def qsize(self):
        with self._lock:
            return len(self._items)
