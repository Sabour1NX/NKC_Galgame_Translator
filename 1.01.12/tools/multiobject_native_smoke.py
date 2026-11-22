# SPDX-License-Identifier: MIT
"""Synthetic Pipeline + OverlayState + native-window integration smoke test.

No API, game access, desktop capture, simulated input, or foreground activation.
OCR observations and accumulated translation chunks are deliberately simulated.
Only this process's fixture/overlay windows are inspected with PrintWindow.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import queue
import sys
import threading
import time

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nkc_galgame_translator.native import NativeCore
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.languages import label_translation
from overlay_smoke import NOACTIVATE, USER32, overlays, print_window, window_mask

WIDTH, HEIGHT = 960, 420
BACKGROUND = (18, 24, 36)
COLORS = [(28, 43, 63), (39, 36, 63), (25, 52, 48),
          (58, 39, 45), (53, 47, 29), (31, 44, 60)]
SOURCES = ["Journal: Explore the eastern forest.",
           "Quest: Find the lost silver key.",
           "Party: Remilia / Level 20",
           "\u4f9d\u983c: \u661f\u306e\u6b20\u7247\u3092\u96c6\u3081\u308b\u3002",
           "\u6240\u6301\u54c1: \u56de\u5fa9\u85ac x 3",
           "\u8a2d\u5b9a: \u5b57\u5e55\u3068\u97f3\u91cf\u3092\u5909\u66f4\u3059\u308b\u3002"]
TRANSLATIONS = ["\u65e5\u5fd7\uff1a\u63a2\u7d22\u4e1c\u90e8\u68ee\u6797\u3002\n\u5c0f\u5fc3\u5c94\u8def\u4e0e\u9690\u85cf\u5b9d\u7bb1\u3002",
                "\u4efb\u52a1\uff1a\u5bfb\u627e\u9057\u5931\u7684\u94f6\u94a5\u5319\u3002",
                "\u961f\u4f0d\uff1a\u857e\u7c73\u8389\u4e9a / \u7b49\u7ea7 20",
                "\u59d4\u6258\uff1a\u6536\u96c6\u661f\u4e4b\u788e\u7247\u3002",
                "\u7269\u54c1\uff1a\u6062\u590d\u836f × 3",
                "\u8bbe\u7f6e\uff1a\u8c03\u6574\u5b57\u5e55\u4e0e\u97f3\u91cf\u3002"]
PAINT_LINES = []
FIXTURE_ORIGIN = (0, 0)


def fixture_paint(hwnd, dc):
    brush = win32gui.CreateSolidBrush(win32api.RGB(*BACKGROUND))
    win32gui.FillRect(dc, win32gui.GetClientRect(hwnd), brush)
    win32gui.DeleteObject(brush)
    font = win32ui.CreateFont({"name": "Microsoft YaHei UI", "height": -19})
    previous = win32gui.SelectObject(dc, font.GetSafeHandle())
    try:
        win32gui.SetBkMode(dc, win32con.TRANSPARENT)
        win32gui.SetTextColor(dc, win32api.RGB(215, 226, 243))
        win32gui.DrawText(dc, "\u5408\u6210\u6a21\u62df · \u591a\u6587\u5b57\u6846\u5b9e\u65f6\u7ffb\u8bd1 / \u65e0\u6e38\u620f · \u65e0 API", -1,
                         (24, 15, WIDTH - 20, 45), win32con.DT_SINGLELINE)
        ox, oy = FIXTURE_ORIGIN
        for index, line in enumerate(PAINT_LINES):
            x, y = line['x'] - ox, line['y'] - oy
            box = (x, y, x + line['w'], y + line['h'])
            brush = win32gui.CreateSolidBrush(win32api.RGB(*line['bg']))
            win32gui.FillRect(dc, box, brush)
            win32gui.DeleteObject(brush)
            win32gui.SetTextColor(dc, win32api.RGB(149, 174, 208))
            win32gui.DrawText(dc, f"\u5bf9\u8c61 {index + 1:02d}", -1,
                             (x, y - 26, x + 150, y - 3), win32con.DT_SINGLELINE)
            win32gui.SetTextColor(dc, win32api.RGB(*line['fg']))
            win32gui.DrawText(dc, line['text'], -1, box,
                             win32con.DT_LEFT | win32con.DT_WORDBREAK | win32con.DT_NOPREFIX)
    finally:
        win32gui.SelectObject(dc, previous)


def fixture_proc(hwnd, message, wp, lp):
    if message == win32con.WM_PAINT:
        dc, paint = win32gui.BeginPaint(hwnd)
        try:
            fixture_paint(hwnd, dc)
        finally:
            win32gui.EndPaint(hwnd, paint)
        return 0
    if message == win32con.WM_PRINTCLIENT:
        fixture_paint(hwnd, wp)
        return 0
    if message == win32con.WM_MOUSEACTIVATE:
        return 3
    if message == win32con.WM_NCHITTEST:
        return -1
    return win32gui.DefWindowProc(hwnd, message, wp, lp)


class SyntheticCapture:
    """Feeds deterministic OCR observations; delegates overlay calls to C++."""
    def __init__(self, native, lines):
        self.native = native
        self.lock = threading.Lock()
        self.lines = lines
        self.changed = True

    def set_scene(self, lines):
        with self.lock:
            self.lines = [dict(line) for line in lines]
            self.changed = True

    def reset(self):
        with self.lock:
            self.changed = True

    def capture_ocr(self, *region, language):
        with self.lock:
            changed, self.changed = self.changed, False
            return {'changed': changed, 'lines': [dict(line) for line in self.lines],
                    'capture_ms': 0., 'ocr_ms': 0., 'synthetic_ocr': True}

    def hide_overlay(self):
        self.native.hide_overlay()


class SyntheticTranslator:
    """Gated cumulative chunks expose four simultaneous native partial masks."""
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []
        self.active = self.peak = 0
        self.finished = []
        self.plans = {}
        self.advance = threading.Event()
        self.finish = threading.Event()
        for source, text in zip(SOURCES, TRANSLATIONS):
            self.plans[source] = (text, self.advance, self.finish)

    def add(self, source, translated):
        advance, finish = threading.Event(), threading.Event()
        self.plans[source] = (translated, advance, finish)
        return advance, finish

    def release_all(self):
        for _, advance, finish in self.plans.values():
            advance.set()
            finish.set()

    def translate(self, game, source, target, text, chunk, context):
        translated, advance, finish = self.plans[text]
        with self.lock:
            self.calls.append(text)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            chunk(translated[:2])
            assert advance.wait(30), 'synthetic intermediate gate timed out'
            chunk(translated[:7])
            assert finish.wait(30), 'synthetic completion gate timed out'
            chunk(translated)
            return translated
        finally:
            with self.lock:
                self.active -= 1
                self.finished.append(text)


def rectangle(line):
    return (line['x'], line['y'], line['x'] + line['w'], line['y'] + line['h'])


def main():
    global PAINT_LINES, FIXTURE_ORIGIN
    destination = ROOT / 'reports'
    destination.mkdir(exist_ok=True)
    report = {'kind': 'synthetic Pipeline + OverlayState + actual C++ native overlays',
              'api_used': False, 'game_accessed': False, 'input_sent': False,
              'ocr_source': 'six deterministic simulated OCR boxes',
              'translation_source': 'fixed simulated cumulative chunks',
              'screenshot_source': 'PrintWindow of this process fixture and overlay windows only',
              'native_mode': 'unbound own-fixture diagnostic mode; does not validate game focus binding',
              'stages': []}
    began = time.perf_counter()
    before_foreground = win32gui.GetForegroundWindow()
    instance = win32api.GetModuleHandle(None)
    cls = win32gui.WNDCLASS()
    cls.hInstance = instance
    cls.lpszClassName = 'NKC_Galgame_TranslatorMultiobjectSyntheticFixture'
    cls.lpfnWndProc = fixture_proc
    atom = win32gui.RegisterClass(cls)
    vx, vy = win32api.GetSystemMetrics(76), win32api.GetSystemMetrics(77)
    vw, vh = win32api.GetSystemMetrics(78), win32api.GetSystemMetrics(79)
    x, y = vx + max(0, (vw - WIDTH) // 2), vy + max(0, (vh - HEIGHT) // 2)
    FIXTURE_ORIGIN = (x, y)
    lines = [{'text': source, 'x': x + 24 + (index % 2) * 472,
              'y': y + 86 + (index // 2) * 110, 'w': 436, 'h': 78,
              'bg': COLORS[index], 'fg': [242, 246, 251], 'font_size': 23}
             for index, source in enumerate(SOURCES)]
    PAINT_LINES = lines
    hwnd = win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST | NOACTIVATE | win32con.WS_EX_TOOLWINDOW,
        atom, 'Synthetic multiobject pipeline test (no API)', win32con.WS_POPUP,
        x, y, WIDTH, HEIGHT, 0, 0, instance, None)
    native = pipeline = engine = None
    state, event_queue = OverlayState(), queue.SimpleQueue()
    event_history, pictures = [], []
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
        win32gui.UpdateWindow(hwnd)
        win32gui.PumpWaitingMessages()
        assert win32gui.GetForegroundWindow() == before_foreground, 'Fixture activated'
        native = NativeCore()
        capture = SyntheticCapture(native, lines)
        engine = SyntheticTranslator()
        pipeline = Pipeline(capture, engine, event_queue.put, interval=.01, settle=.025,
                            merge_lines=False, tracking_workers=2, translation_workers=4)

        def drain():
            win32gui.PumpWaitingMessages()
            assert win32gui.GetForegroundWindow() == before_foreground, 'Foreground changed during test'
            changed = False
            while True:
                try:
                    event = event_queue.get_nowait()
                except queue.Empty:
                    break
                event_history.append(event)
                kind, session, payload = event
                if session != pipeline.generation:
                    continue
                if kind == 'objects':
                    changed = state.apply_objects(payload) or changed
                elif kind == 'translation':
                    identity, line, original, complete = payload
                    changed = state.apply_translation(identity, line) or changed
                elif kind == 'clear':
                    state.clear()
                    changed = True
                elif kind in ('error', 'line_error'):
                    raise AssertionError(f'Pipeline error: {payload}')
            if changed:
                native.show_overlay(list(state.rendered.values()))

        def until(predicate, description, timeout=5):
            deadline = time.perf_counter() + timeout
            while time.perf_counter() < deadline:
                drain()
                if predicate():
                    return
                time.sleep(.008)
            raise AssertionError('Timed out: ' + description)

        def native_stage(name, growing_from=None):
            expected = {rectangle(line): (identity, dict(line))
                        for identity, line in state.rendered.items()}
            found = {}
            def native_matches():
                found.clear()
                for window in overlays():
                    if not win32gui.IsWindowVisible(window):
                        continue
                    rect = win32gui.GetWindowRect(window)
                    if rect not in expected or rect in found:
                        return False
                    identity, line = expected[rect]
                    mask, mask_rectangles = window_mask(window)
                    area, full = mask.histogram()[255], line['w'] * line['h']
                    if (line['final'] and area != full) or (not line['final'] and not 0 < area < full):
                        return False
                    if growing_from and area <= growing_from[identity]['masked_area']:
                        return False  # Wait until the native thread paints the newer chunk.
                    found[rect] = (window, identity, line, mask, mask_rectangles)
                return len(found) == len(expected)
            until(native_matches, name + ': expected native rectangles and masks')
            frame = print_window(hwnd)
            records = []
            for rect, (window, identity, line, mask, mask_rectangles) in found.items():
                shot = print_window(window, diagnostic_overlay=True)
                style = win32gui.GetWindowLong(window, win32con.GWL_EXSTYLE)
                assert style & NOACTIVATE and style & win32con.WS_EX_TRANSPARENT
                assert win32gui.SendMessage(window, win32con.WM_NCHITTEST, 0, 0) == -1
                affinity = ctypes.c_uint()
                assert USER32.GetWindowDisplayAffinity(window, ctypes.byref(affinity)) and affinity.value == 0x11
                # Full regions must paint the requested approximate local background.
                if line['final']:
                    assert shot.getpixel((line['w'] - 1, line['h'] - 1)) == tuple(line['bg'])
                frame.paste(shot, (rect[0] - x, rect[1] - y), mask)
                records.append({'track_id': identity, 'revision': line['_revision'],
                    'text': line['text'], 'final': line['final'], 'rectangle': list(rect),
                    'masked_area': mask.histogram()[255], 'full_area': line['w'] * line['h'],
                    'mask_rectangles': mask_rectangles,
                    'pixels_sha256': hashlib.sha256(shot.tobytes()).hexdigest()})
            stage = {'name': name, 'native_window_count': len(records),
                     'partial_count': sum(not item['final'] for item in records),
                     'final_count': sum(item['final'] for item in records), 'objects': records}
            report['stages'].append(stage)
            pictures.append((name, frame))
            return {item['track_id']: item for item in records}

        def set_scene(new_lines):
            global PAINT_LINES
            PAINT_LINES = new_lines
            win32gui.InvalidateRect(hwnd, None, False)
            win32gui.UpdateWindow(hwnd)
            capture.set_scene(new_lines)

        pipeline.start(lambda: (x, y, WIDTH, HEIGHT), 'synthetic-fixture', 'ja', 'zh-Hans')
        until(lambda: engine.active == 4 and len(state.rendered) == 4,
              'four simultaneously active partial translations')
        partial = native_stage('01 \u56db\u5bf9\u8c61\u540c\u65f6\u6d41\u5f0f\uff1a\u53ea\u8986\u76d6\u5df2\u751f\u6210\u6587\u5b57')
        assert len(partial) == 4 and all(not record['final'] for record in partial.values())
        engine.advance.set()
        until(lambda: len(state.rendered) == 4 and all(
            line['text'] == label_translation(TRANSLATIONS[SOURCES.index(state.objects[i]['line']['text'])][:7],
                                               line['source_lang'], False)
            for i,line in state.rendered.items()),
              'four accumulated intermediate chunks')
        intermediate = native_stage('02 \u56db\u5bf9\u8c61\u7ee7\u7eed\u6d41\u5f0f\uff1a\u906e\u76d6\u533a\u57df\u968f\u6587\u5b57\u589e\u957f', growing_from=partial)
        assert all(intermediate[i]['masked_area'] > partial[i]['masked_area'] for i in partial)
        engine.finish.set()
        until(lambda: len(state.rendered) == 6 and all(line['final'] for line in state.rendered.values()),
              'six completed objects')
        completed = native_stage('03 \u516d\u5bf9\u8c61\u5168\u90e8\u5b8c\u6210\uff1a\u8986\u76d6\u5b8c\u6574\u539f\u6587\u77e9\u5f62')
        assert len(completed) == 6 and len(engine.calls) == 6 and engine.peak == 4
        first_ids = {item['line']['text']: identity for identity, item in state.objects.items()}
        moved_id = first_ids[SOURCES[0]]
        changed_id = first_ids[SOURCES[1]]
        original_generation = pipeline.generation

        lines = [dict(line) for line in lines]
        lines[0]['x'] += 9
        lines[0]['y'] += 8
        set_scene(lines)
        until(lambda: state.rendered[moved_id]['x'] == lines[0]['x'], 'geometry-only movement')
        moved = native_stage('04 \u79fb\u52a8\u4e00\u4e2a\u6587\u5b57\u6846\uff1a\u516d\u4efd\u8bd1\u6587\u4fdd\u6301\u539f\u6837')
        assert len(engine.calls) == 6
        assert all(moved[i]['pixels_sha256'] == completed[i]['pixels_sha256'] for i in completed)

        superseded = 'Quest: Search the old tower.'
        replacement = 'Quest: Open the eastern gate.'
        old_advance, old_finish = engine.add(superseded, '\u65e7\u4efb\u52a1\uff1a\u641c\u7d22\u5e9f\u5f03\u9ad8\u5854\u3002')
        new_advance, new_finish = engine.add(replacement, '\u65b0\u4efb\u52a1\uff1a\u6253\u5f00\u4e1c\u4fa7\u5927\u95e8\u3002\n\u5176\u4ed6\u4e94\u6846\u8bd1\u6587\u6301\u7eed\u4fdd\u7559\u3002')
        lines[1] = {**lines[1], 'text': superseded}
        set_scene(lines)
        until(lambda: len(engine.calls) == 7 and changed_id in state.rendered
              and not state.rendered[changed_id]['final'], 'only the edited object starts a new request')
        changing = native_stage('05 \u5355\u6846\u6539\u5b57\uff1a\u5176\u4f59\u4e94\u6846\u4fdd\u7559\u5b8c\u6574\u8bd1\u6587')
        assert all(changing[i]['pixels_sha256'] == moved[i]['pixels_sha256']
                   for i in moved if i != changed_id)
        obsolete_revision = state.objects[changed_id]['revision']

        lines[1] = {**lines[1], 'text': replacement}
        set_scene(lines)
        until(lambda: len(engine.calls) == 8 and state.objects[changed_id]['revision'] > obsolete_revision
              and changed_id in state.rendered and not state.rendered[changed_id]['final'],
              'a newer object revision supersedes the slow stream')
        new_advance.set()
        new_finish.set()
        until(lambda: state.rendered[changed_id]['final'], 'new revision completes first')
        checkpoint = len(event_history)
        old_advance.set()
        old_finish.set()
        until(lambda: superseded in engine.finished and pipeline.get_stats()['inflight'] == 0,
              'obsolete request finishes without reappearing')
        final = native_stage('06 \u6700\u65b0\u4fee\u8ba2\u5b8c\u6210\uff1a\u8fc7\u671f\u6d41\u54cd\u5e94\u4e0d\u518d\u56de\u6d41')
        assert not any(e[0] == 'translation' and e[2][0] == changed_id
                       and e[2][1]['_revision'] == obsolete_revision for e in event_history[checkpoint:])
        assert state.rendered[changed_id]['text'].startswith('[\u82f1\u8bed\uff1a\u65b0\u4efb\u52a1\uff1a')
        assert all(final[i]['pixels_sha256'] == moved[i]['pixels_sha256']
                   for i in moved if i != changed_id)
        assert pipeline.generation == original_generation
        assert not any(e[0] == 'clear' for e in event_history)
        assert engine.calls.count(SOURCES[0]) == 1

        # Use four representative stages; all content pixels originate from our
        # own PrintWindow calls, with explanatory labels drawn around them.
        selected = [pictures[0], pictures[2], pictures[4], pictures[5]]
        row_height, header = HEIGHT + 46, 74
        proof = Image.new('RGB', (WIDTH * 2, header + row_height * 2), (238, 242, 248))
        draw = ImageDraw.Draw(proof)
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 21)
        draw.text((20, 10), '\u5408\u6210\u6a21\u62df\u9a8c\u8bc1 / \u5b9e\u9645 C++ \u8986\u76d6\u7a97 + \u591a\u5bf9\u8c61 Pipeline / \u975e\u6e38\u620f\u622a\u56fe',
                  font=font, fill=(20, 35, 58))
        draw.text((20, 40), 'OCR \u4e0e\u7d2f\u8ba1\u8bd1\u6587\u5747\u4e3a\u56fa\u5b9a\u6a21\u62df\u6570\u636e\uff1b\u65e0 API\u3001\u65e0\u8f93\u5165\u3001\u65e0\u524d\u53f0\u6fc0\u6d3b\u3002',
                  font=font, fill=(61, 80, 103))
        for index, (title, frame) in enumerate(selected):
            px, py = (index % 2) * WIDTH, header + (index // 2) * row_height
            draw.text((px + 14, py + 8), title, font=font, fill=(20, 35, 58))
            proof.paste(frame, (px, py + 46))
        proof.save(destination / 'multiobject-native-proof.png')
        report.update({'status': 'passed', 'max_parallel_translations': engine.peak,
            'initial_object_count': 6, 'initial_request_count': 6,
            'geometry_move_extra_requests': 0, 'single_revision_extra_requests': 1,
            'total_requests_including_superseded_revision': len(engine.calls),
            'simultaneous_partial_masks_pass': True, 'progressive_masks_pass': True,
            'six_final_rectangles_and_full_masks_pass': True,
            'five_unchanged_native_pixels_preserved_pass': True,
            'old_stream_suppressed_pass': True, 'no_global_clear_pass': True,
            'clickthrough_pass': True, 'capture_exclusion_restored_pass': True,
            'foreground_unchanged_pass': win32gui.GetForegroundWindow() == before_foreground,
            'pipeline_stats': pipeline.get_stats(), 'screenshot': 'multiobject-native-proof.png'})
    except Exception as error:
        report.update({'status': 'failed', 'error': repr(error)})
        raise
    finally:
        if engine:
            engine.release_all()
        if pipeline:
            pipeline.stop()
            report['pipeline_workers_joined'] = pipeline.join(5)
            pipeline.pool.shutdown(wait=True, cancel_futures=True)
        if native:
            native.close()
        if win32gui.IsWindow(hwnd):
            win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(atom, instance)
        report['owned_overlays_remaining'] = len(overlays())
        report['foreground_unchanged_after_cleanup'] = win32gui.GetForegroundWindow() == before_foreground
        report['elapsed_seconds'] = round(time.perf_counter() - began, 3)
        (destination / 'multiobject-native-test.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['pipeline_workers_joined'] and report['owned_overlays_remaining'] == 0
    assert report['foreground_unchanged_after_cleanup']
    print(json.dumps({key: value for key, value in report.items() if key != 'stages'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
