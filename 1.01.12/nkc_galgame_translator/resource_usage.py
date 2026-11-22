# SPDX-License-Identifier: MIT
"""Sample resources and draw two rolling series on one timeline."""

from bisect import bisect_left
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import colorsys
import ctypes
from ctypes import wintypes
from functools import lru_cache
import math
import os
import random
import time
import tkinter as tk
from PIL import Image, ImageTk

from .chart_backdrop import backdrop, load_picture
from .gpu_usage import NvidiaSampler
from .i18n import ui_source
from .themes import luminance, mix
from .ui_font import UI_SMALL_SIZE


class MemoryCounters(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
            "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile")]


@lru_cache(maxsize=1)
def _memory_api():
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    api = kernel.K32GetProcessMemoryInfo
    api.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    api.restype = wintypes.BOOL
    return api, kernel.GetCurrentProcess()


def working_set_mib():
    try:
        query, process = _memory_api()
    except (AttributeError, OSError):
        return None
    counters = MemoryCounters()
    counters.size = ctypes.sizeof(counters)
    if query(process, ctypes.byref(counters), counters.size):
        return counters.working_set / 1024**2
    return None


@lru_cache(maxsize=1)
def _window_api():
    api = ctypes.windll.user32
    api.GetForegroundWindow.argtypes = []
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.GetWindowThreadProcessId.restype = wintypes.DWORD
    return api


def _in_foreground():
    api = _window_api()
    owner = wintypes.DWORD()
    api.GetWindowThreadProcessId(api.GetForegroundWindow(), ctypes.byref(owner))
    return owner.value == os.getpid()


def version_colors(version, background, accent=None):
    major, minor, patch = map(int, version.split("."))
    hue = ((major * 10000 + minor * 100 + patch) * 137.507764) % 360 / 360
    if accent:
        channels = [int(accent[i:i+2], 16) / 255 for i in (1, 3, 5)]
        primary = colorsys.rgb_to_hsv(*channels)[0]
        primary = primary if primary < .10 or primary > .74 else .88
    else:
        primary = .88
    hues = (primary, .583 + .048 * hue)
    dark = luminance(background) < .22
    saturation, value = (.55, .98) if dark else (.82, .51)
    return tuple("#" + "".join(f"{round(channel * 255):02X}" for channel in colorsys.hsv_to_rgb(h, saturation, value))
                 for h in hues)


@dataclass(frozen=True)
class RidgePeak:
    depth: float
    amplitude: float
    speed: float
    phase: float
    tilt: float
    shape: str

    def at(self, y, bottom, now):
        offset = self.depth + self.amplitude * math.sin(self.speed * now + self.phase)
        return min(bottom, y + offset)


RIDGE_ANCHOR_MARGIN = 6
RIDGE_GAP = 6


def _ridge_strokes(path, index, end, floor, now):
    x, y, motion = path[index]
    height = floor - y
    left = path[index - 1][0]
    right = path[index + 1][0]
    if height >= 27 and motion.shape == "triangle" and end is not None:
        next_x, next_y, _ = path[end]
        fraction = .27 + motion.tilt * .095
        joint_x = x + (next_x - x) * fraction
        edge_y = y + (next_y - y) * fraction
        joint_y = motion.at(edge_y + (floor - edge_y) * .32, floor - 2, now)
        # The link has two straight arms. Clear every skipped sample on each arm.
        for px, py, _ in path[index + 1:end]:
            t = (px - x) / (next_x - x)
            weight = min(t / fraction, (1 - t) / (1 - fraction))
            chord_y = y + (next_y - y) * t
            joint_y = max(joint_y, edge_y + (py - chord_y) / weight)
        if joint_y <= floor:
            return (((x, y, joint_x, joint_y, next_x, next_y), ("usage", "ridge-link")),)
    if height >= 27 and motion.shape == "fork":
        span = min(x - left, right - x, height * .85)
        foot_x = x + span * motion.tilt * .19
        joint_y = motion.at(y + height * .32, floor - 4, now)
        return (
            ((x, y, foot_x, joint_y), ("usage", "ridge")),
            ((foot_x - span * .36, floor, foot_x, joint_y, foot_x + span * .36, floor), ("usage", "ridge-fork")),
        )
    # Stay in the adjacent sample interval so the leg cannot cross a valley.
    foot_x = max(left, min(right, x + height * .75 * motion.tilt))
    return (((x, y, foot_x, floor), ("usage", "ridge", "ground")),)


class SessionSamples:
    def __init__(self, capacity=72):
        self.history = [deque(maxlen=capacity), deque(maxlen=capacity)]
        self.peaks = [None, None]
        self.visible_ridges = set()
        self.random = random.Random()

    def record(self, index, value, timestamp):
        if value is not None:
            peak = self.peaks[index]
            self.peaks[index] = value if peak is None else max(peak, value)
        rng = self.random
        ridge = RidgePeak(rng.uniform(4.5, 10), rng.uniform(1, 3.5),
                          rng.uniform(1.15, 3.5), rng.uniform(0, math.tau),
                          rng.uniform(-1., 1.),
                          rng.choices(("ground", "fork", "triangle"), weights=(5, 3, 2))[0])
        self.history[index].append((timestamp, value, ridge))

    def visible(self, index, latest):
        history = self.history[index]
        samples = []
        for timestamp, value, ridge in reversed(history):
            if value is None or latest - timestamp > history.maxlen - 1:
                break
            samples.append((timestamp, value, ridge))
        return samples

    def plot(self, index, samples, latest, limits, left, right, top, bottom):
        low, high = limits
        step = (right - left) / (self.history[index].maxlen - 1)
        return [(left + (latest - timestamp) * step,
                 (top + bottom) / 2 if low == high else bottom - (bottom - top) * (value - low) / (high - low),
                 ridge) for timestamp, value, ridge in samples]


class ResourceUsage(tk.Canvas):
    """CPU and RAM for the app, or utilization and VRAM for the CUDA device."""

    def __init__(self, parent, version, font, translate, gpu_active, gpu_enabled):
        super().__init__(parent, height=83, highlightthickness=0)
        self.version, self.ui_font, self.translate = version, font, translate
        self.gpu_active = gpu_active
        self.gpu_enabled = gpu_enabled
        self.monitoring_gpu = False
        self.cpu = SessionSamples()
        self.gpu = SessionSamples()
        self.show_gpu = False
        self.sampler = NvidiaSampler()
        self.executor = None
        self.pending = None
        self.cores = max(1, os.cpu_count() or 1)
        self.previous = None
        self.next_sample = 0.0
        self.next_metric = 0
        self.grip = tk.Canvas(self, height=9, highlightthickness=0, cursor="sb_v_double_arrow")
        self.grip.place(relx=0, rely=1, relwidth=1, height=9, anchor="sw")
        self.grip.bind("<Configure>", self._draw_grip)
        self.grip.bind("<ButtonPress-1>", self._begin_resize)
        self.grip.bind("<B1-Motion>", self._resize)
        parent.bind("<Configure>", self._fit_height, add="+")
        self.timer = self.after_idle(self._tick)
        self.bind("<Destroy>", self._close)
        self.bind("<Configure>", lambda _: self.draw())

    def configure_colors(self, paper, surface, ink, accent, theme, picture, icon, chart_style, overrides=()):
        self.panel = mix(paper, surface, .09)
        self.text_color = ink if luminance(self.panel) > .22 else "#F5F2FF"
        defaults = version_colors(self.version, self.panel, accent)
        if theme == 'modern_windows':
            defaults = ('#0078D4', '#163B78')
        elif theme in ('system', 'custom'):
            defaults = (accent, defaults[1])
        self.lines = tuple((overrides[i] if overrides else '') or color for i, color in enumerate(defaults))
        self.theme, self.icon = theme, icon
        self.chart_style = chart_style
        self.background_size = None
        try:
            self.picture = load_picture(picture) if picture else None
        except (OSError, ValueError, Image.DecompressionBombError):
            self.picture = None
        self.configure(bg=self.panel)
        self.grip.configure(bg=self.panel)
        self._draw_grip()
        self.draw()

    def _draw_grip(self, event=None):
        if hasattr(self, "panel"):
            center = self.grip.winfo_width() / 2
            self.grip.delete("all")
            self.grip.create_line(center - 16, 4, center + 16, 4, width=2,
                                  fill=mix(self.panel, self.text_color, .46))

    def _begin_resize(self, event):
        self.drag_start = event.y_root, self.winfo_height()

    def _resize(self, event):
        start, height = self.drag_start
        self.configure(height=max(83, min(height + event.y_root - start, self.master.winfo_height() // 3)))

    def _fit_height(self, event):
        limit = max(83, event.height // 3)
        if int(self.cget("height")) > limit:
            self.configure(height=limit)

    def _close(self, event):
        if event.widget is not self:
            return
        if self.timer is not None:
            self.after_cancel(self.timer)
            self.timer = None
        if self.executor is not None:
            if self.pending is not None:
                self.pending.cancel()
            self.executor.submit(self.sampler.close)
            self.executor.shutdown(wait=False)
            self.executor = None

    def _sample_cpu(self, now):
        used = time.process_time()
        load = None
        if self.previous:
            elapsed = now - self.previous[0]
            if elapsed > 0:
                load = max(0., min(100., 100 * (used - self.previous[1]) / (elapsed * self.cores)))
        self.previous = now, used
        return load

    def _tick(self):
        self.timer = None
        now = time.perf_counter()
        enabled = bool(self.gpu_enabled())
        if self.monitoring_gpu and not enabled:
            if self.pending is not None:
                self.pending.cancel()
                self.pending = None
            for index in range(2):
                self.gpu.record(index, None, now)
        self.monitoring_gpu = enabled
        if self.pending is not None and self.pending.done():
            try:
                timestamp, value = self.pending.result()
                self.gpu.record(self.pending_metric, value, timestamp)
            except (OSError, ValueError):
                self.gpu.record(self.pending_metric, None, now)
            self.pending = None
        if now >= self.next_sample:
            self.next_sample = now + .5
            metric = self.next_metric
            self.next_metric = 1 - metric
            value = self._sample_cpu(now) if metric == 0 else working_set_mib()
            self.cpu.record(metric, value, now)
            if enabled and self.pending is None:
                if self.executor is None:
                    self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gpu-usage")
                self.pending_metric = metric
                self.pending = self.executor.submit(self.sampler.sample, metric)
        active = enabled and self.gpu_active()
        ready = all(len(h) >= 2 and all(point[1] is not None for point in (h[-2], h[-1]))
                    for h in self.gpu.history)
        self.show_gpu = bool(active and (self.show_gpu or ready))
        foreground = self.winfo_ismapped() and _in_foreground()
        if foreground:
            self.draw(now)
        self.timer = self.after(100 if foreground else 500, self._tick)

    def draw(self, now=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 100 or height < 44 or not hasattr(self, "lines"):
            return
        now = time.perf_counter() if now is None else now
        self.delete("usage")
        if self.background_size != (width, height):
            artwork = backdrop((width, height), self.theme, self.panel, self.picture, self.icon)
            self.delete("backdrop")
            self.background = ImageTk.PhotoImage(artwork, master=self) if artwork is not None else None
            if self.background is not None:
                self.create_image(0, 0, image=self.background, anchor="nw", tags="backdrop")
                self.tag_lower("backdrop")
            self.background_size = width, height
        series = self.gpu if self.show_gpu else self.cpu
        recent = [history[-1][1] if history else None for history in series.history]
        latest = max((history[-1][0] for history in series.history if history), default=0)
        samples = [series.visible(index, latest) for index in range(2)]
        labels = (("GPU utilization", "VRAM usage") if self.show_gpu else ("App CPU", "App memory"))
        units = ("{:.1f}%", "{:.0f} MiB")
        limits = []
        margins = []
        top, bottom = 33, height - 20
        for index, label in enumerate(labels):
            current = units[index].format(recent[index]) if recent[index] is not None else "—"
            maximum = series.peaks[index]
            peak = units[index].format(maximum) if maximum is not None else "—"
            text = (f"{self.translate(ui_source(label))}  {current}   "
                    + self.translate(ui_source("Peak {value}")).format(value=peak))
            self.create_text(17 if index == 0 else width - 17, 9, text=text,
                             anchor="nw" if index == 0 else "ne", fill=self.lines[index],
                             font=(self.ui_font, UI_SMALL_SIZE, "bold"), tags="usage")
            values = [v for _, v, _ in samples[index]]
            low, high = (min(values), max(values)) if values else (0, 0)
            limits.append((low, high))
            precision = 1 if index == 0 else 0
            while high > low and round(high, precision) == round(low, precision) and precision < 6:
                precision += 1
            margin = 17
            for symbol, value, y in (("▲", high, top), ("▼", low, bottom)):
                unit = "%" if index == 0 else " MiB"
                label = f"{symbol} {value:.{precision}f}{unit}" if values else f"{symbol} —"
                item = self.create_text(17 if index == 0 else width - 17, y, text=label,
                                        anchor="w" if index == 0 else "e", fill=self.lines[index],
                                        font=(self.ui_font, UI_SMALL_SIZE), tags=("usage", "axis"))
                box = self.bbox(item)
                margin = max(margin, box[2] + 8 if index == 0 else width - box[0] + 8)
            margins.append(margin)
        left, right = margins[0], width - margins[1]
        if right <= left:
            return
        paths = [series.plot(i, samples[i], latest, limits[i], left, right, top, bottom) for i in range(2)]
        if self.chart_style == "mountains":
            series.visible_ridges = self._draw_ridge(paths[0], self.lines[0], height - 10, now, series.visible_ridges)
        else:
            self.create_line(left, bottom, right, bottom, fill=mix(self.panel, self.text_color, .23), tags="usage")
        coincident = all(len(path) >= 2 for path in paths) and all(lo == hi for lo, hi in limits)
        for index, (path, color) in enumerate(zip(paths, self.lines)):
            if len(path) >= 2:
                self.create_line(*(v for x, y, _ in path for v in (x, y)),
                                 fill=color, width=2, dash=(5, 4) if coincident and index else (),
                                 tags=("usage", "data-line"))

    def _draw_ridge(self, path, color, floor, now, previous=()):
        stroke = mix(self.panel, color, .76)
        turns = [i for i in range(1, len(path) - 1)
                 if abs(path[i - 1][1] + path[i + 1][1] - 2 * path[i][1]) >= 1]
        occupied = []
        visible = set()
        # Admit existing ridges first when a new sample scrolls into view.
        order = sorted(enumerate(turns), key=lambda turn: path[turn[1]][2] not in previous)
        for ordinal, index in order:
            x, _, peak = path[index]
            position = bisect_left(occupied, (x,))
            left = occupied[position - 1][1] + RIDGE_GAP if position else -math.inf
            right = occupied[position][0] - RIDGE_GAP if position < len(occupied) else math.inf
            low, high = x - RIDGE_ANCHOR_MARGIN, x + RIDGE_ANCHOR_MARGIN
            if low < left or high > right:
                continue
            end = turns[ordinal + 1] if ordinal + 1 < len(turns) else None
            strokes = _ridge_strokes(path, index, end, floor, now)
            # Reserve the whole horizontal footprint, including both feet of a fork.
            for coords, _ in strokes:
                low = min(low, *coords[::2])
                high = max(high, *coords[::2])
            if low < left or high > right:
                continue
            occupied.insert(position, (low, high))
            visible.add(peak)
            for coords, tags in strokes:
                self.create_line(*coords, fill=stroke, tags=tags)
        return visible
