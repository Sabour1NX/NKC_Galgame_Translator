# SPDX-License-Identifier: MIT
"""Real GDI/DWM refresh sampling of owned, non-activating synthetic fixtures.

These are compositor regressions, not game/OCR/translation quality evidence.
No input, game process, credentials or API requests are used.
"""
import ctypes
from ctypes import wintypes
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import threading
import time

from PIL import Image, ImageChops, ImageDraw, ImageFont
import pytest

from test_native_overlay import core, region, render
from test_native_aero import InfoHeader, fixed_item, scene_with_ink, source_window
from overlay_smoke import USER32, print_window, window_mask


EVIDENCE = []


def pixels(image):
    return image.get_flattened_data() if hasattr(image, 'get_flattened_data') else image.getdata()


@pytest.fixture(scope='module', autouse=True)
def write_evidence():
    yield
    destination = Path(__file__).resolve().parents[1] / 'reports/native-refresh29.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({
        'version': '0.01.29', 'kind': 'owned synthetic GDI/DWM compositor replay',
        'live_game_verified': False, 'api_requests': 0,
        'sampling_limitations': 'Discrete screen samples and committed-frame assertions; '
                                'not an exhaustive physical display scanout recording.',
        'cases': EVIDENCE,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


class ScreenReader:
    """Reusable desktop BitBlt surface; includes layered windows, no cursor."""
    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height
        self.user = ctypes.WinDLL('user32')
        self.gdi = ctypes.WinDLL('gdi32')
        self.user.GetDC.argtypes = [wintypes.HWND]
        self.user.GetDC.restype = wintypes.HDC
        self.user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(InfoHeader),
            wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        self.gdi.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        self.screen = self.user.GetDC(None)
        self.dc = self.gdi.CreateCompatibleDC(self.screen)
        info = InfoHeader(); info.size = ctypes.sizeof(info)
        info.width, info.height, info.planes, info.bits = width, -height, 1, 32
        self.bits = ctypes.c_void_p()
        self.bitmap = self.gdi.CreateDIBSection(self.screen, ctypes.byref(info), 0,
                                               ctypes.byref(self.bits), None, 0)
        assert self.screen and self.dc and self.bitmap
        self.old = self.gdi.SelectObject(self.dc, self.bitmap)

    def read(self):
        assert self.gdi.BitBlt(self.dc, 0, 0, self.width, self.height,
                              self.screen, self.x, self.y, 0x40cc0020)
        self.gdi.GdiFlush()
        return Image.frombytes('RGB', (self.width, self.height),
            ctypes.string_at(self.bits, self.width * self.height * 4), 'raw', 'BGRX')

    def close(self):
        self.gdi.SelectObject(self.dc, self.old)
        self.gdi.DeleteObject(self.bitmap)
        self.gdi.DeleteDC(self.dc)
        self.user.ReleaseDC(None, self.screen)


class RefreshRecorder:
    def __init__(self, bounds):
        self.bounds = bounds
        self.stop = threading.Event()
        self.phase = 'initial'
        self.samples = []
        self.errors = []
        self.thread = threading.Thread(target=self.run, name='native-refresh-screen-sampler')

    def run(self):
        reader = None
        started = time.perf_counter()
        try:
            reader = ScreenReader(*self.bounds)
            while not self.stop.is_set() and len(self.samples) < 4096:
                phase = self.phase
                frame = reader.read()
                extrema = frame.getextrema()
                self.samples.append(dict(phase=phase, elapsed_ms=round(1000*(time.perf_counter()-started), 3),
                    min_rgb=[pair[0] for pair in extrema], max_rgb=[pair[1] for pair in extrema],
                    sha256=hashlib.sha256(frame.tobytes()).hexdigest()))
                self.stop.wait(.001)
        except BaseException as exc:
            self.errors.append(repr(exc))
        finally:
            if reader: reader.close()

    def finish(self):
        self.stop.set(); self.thread.join(3)
        assert not self.thread.is_alive() and not self.errors, self.errors
        assert len(self.samples) >= 8
        assert all(min(item['min_rgb']) > 0 for item in self.samples), [
            item for item in self.samples if min(item['min_rgb']) == 0]
        assert len({item['sha256'] for item in self.samples}) >= 3


def assert_atomic(snapshot):
    paint = snapshot['paint']
    assert paint['atomic_layered'] and paint['buffered'] and not paint['failures']
    assert paint['first_show_commits'] >= 1, 'An HWND became visible before receiving its first frame'


@pytest.mark.parametrize('background,foreground', [
    ((42, 63, 87), (232, 237, 245)),
    ((226, 211, 184), (35, 52, 61)),
    ((95, 44, 68), (240, 221, 152)),
])
def test_nonblack_stream_final_resize_erase_never_exposes_black(core, background, foreground):
    x, y = region()['x'] + 25, region()['y'] + 25
    source = Image.new('RGB', (320, 145), background)
    item = region(2901, x=x+12, y=y+12, w=250, h=78, text='\u521d', final=False,
                  bg=list(background), fg=list(foreground), font_size=26)
    phases = []
    with source_window(source, x, y):
        first = render(core, [item])[0]; assert_atomic(first)
        assert USER32.SetWindowDisplayAffinity(first['hwnd'], 0)
        ctypes.windll.dwmapi.DwmFlush()
        reader = ScreenReader(x, y, 320, 145)
        recorder = RefreshRecorder((x, y, 320, 145)); recorder.thread.start()
        try:
            for index, text in enumerate(('\u521d', '\u521d\u59cb', '\u521d\u59cb\u6587\u5b57', '\u521d\u59cb\u6587\u5b57\u6b63\u5728', '\u521d\u59cb\u6587\u5b57\u6b63\u5728\u8f93\u51fa\u3002')):
                recorder.phase = 'partial-' + str(index)
                state = render(core, [{**item, 'text': text}])[0]
                assert_atomic(state)
                assert state['hwnd'] == first['hwnd']
                ctypes.windll.dwmapi.DwmFlush()
                actual = reader.read()
                assert ImageChops.difference(actual, source).getbbox(), 'Overlay was excluded from the sampled screen'
                assert foreground in set(pixels(actual)), 'Foreground color was replaced'
                assert actual.getpixel((15, 15)) == background
                phases.append(recorder.phase)
            for phase, changes in (
                ('final', {'final': True, 'text': '\u5b8c\u6574\u6587\u5b57\u3002'}),
                ('updated', {'final': True, 'text': '\u66f4\u65b0\u540e\u7684\u6587\u5b57\u3002', '_revision': 2}),
                ('resized', {'final': True, 'text': '\u6539\u53d8\u5927\u5c0f\u540e\u7684\u6587\u5b57\u3002', 'w': 280, 'h': 100, '_revision': 3}),
            ):
                recorder.phase = phase
                current = {**item, **changes}
                state = render(core, [current])[0]; assert_atomic(state)
                ctypes.windll.dwmapi.DwmFlush()
                actual = reader.read()
                assert actual.getpixel((12+current['w']-2, 12+current['h']-2)) == background
                assert foreground in set(pixels(actual))
                phases.append(phase)
            recorder.phase = 'erase-invalidation'
            before = reader.read()
            user = ctypes.WinDLL('user32')
            user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT]
            assert user.SendMessageW(state['hwnd'], 0x14, 0, 0) == 1
            assert user.RedrawWindow(state['hwnd'], None, None, 0x105)
            ctypes.windll.dwmapi.DwmFlush()
            assert reader.read().tobytes() == before.tobytes()
            phases.append(recorder.phase)
            recorder.phase = 'removed'
            assert render(core, []) == []
            ctypes.windll.dwmapi.DwmFlush()
            assert reader.read().tobytes() == source.tobytes()
            phases.append(recorder.phase)
        finally:
            try: recorder.finish()
            finally: reader.close()
        EVIDENCE.append(dict(kind='nonblack-color-refresh', background=background,
            foreground=foreground, phases=phases, first_show_commits=first['paint']['first_show_commits'],
            sample_count=len(recorder.samples), all_samples_nonblack=True, samples=recorder.samples))


def test_complex_source_repair_streams_opaquely_and_failure_keeps_source(core):
    x, y = region()['x'] + 25, region()['y'] + 25
    foreground = (240, 230, 160)
    clean, source = scene_with_ink(color=foreground)
    # A deliberately black scalar fallback traps accidental use of default fill
    # instead of the captured, nonblack source texture during reconstruction.
    item = {**fixed_item(x, y, '\u4e2d'), 'bg': [0, 0, 0], 'fg': list(foreground),
            '_track_id': 2902, 'final': False}
    stages = []
    with source_window(source, x, y):
        core.capture_bgra(x, y, *source.size)
        for text, final in [('\u4e2d', False), ('\u4e2d\u6587', False), ('\u4e2d\u6587\u7ffb\u8bd1', False), ('\u8bd1\u6587\u5b8c\u6210', True), (' ', True)]:
            state = render(core, [{**item, 'text': text, 'final': final}])[0]
            assert_atomic(state)
            assert state['aero'] and not state['background_suppressed'], state
            assert state['background_mask_pixels'] == state['background_repaired_pixels'] > 0
            image = print_window(state['hwnd'], diagnostic_overlay=True)
            mask, _ = window_mask(state['hwnd'])
            assert mask.getbbox()
            for yy in range(image.height):
                for xx in range(image.width):
                    if mask.getpixel((xx, yy)):
                        assert min(image.getpixel((xx, yy))) > 0, (text, xx, yy)
            if text == ' ':
                original = source.crop((30, 30, 230, 72)); base = clean.crop((30, 30, 230, 72))
                untouched = 0; removed = 0
                for old, expected, actual in zip(pixels(original), pixels(base), pixels(image)):
                    if old == expected:
                        assert actual == old
                        untouched += 1
                    elif old == foreground:
                        assert actual != old
                        removed += 1
                assert untouched > 4000 and removed > 200
            stages.append(dict(text_units=len(text), final=final, mask_pixels=state['background_mask_pixels'],
                repaired_pixels=state['background_repaired_pixels'], sha256=hashlib.sha256(image.tobytes()).hexdigest()))
        rejected = render(core, [{**item, 'final': True, 'fg': [255, 0, 255], 'text': '\u539f\u6587\u4fdd\u7559'}])[0]

        assert rejected['background_suppressed'] and rejected['background_reason'] == 'foreground_missing'
        assert not ctypes.windll.user32.IsWindowVisible(ctypes.c_void_p(rejected['hwnd']))
        render(core, [])
    EVIDENCE.append(dict(kind='complex-source-opaque-repair', stages=stages,
        unrelated_pixels_unchanged=True, source_ink_removed=True, uncertain_foreground_preserves_source=True))


def test_changed_source_background_replaces_previous_patch_without_default_black(core):
    x, y = region()['x']+25, region()['y']+25
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 23)
    colors = [(44, 62, 93), (211, 192, 160), (85, 45, 67)]
    samples = []
    with ExitStack() as sources:
        for index, background in enumerate(colors):
            source = Image.new('RGB', (280, 110), background)
            foreground = (245, 245, 245) if index != 1 else (35, 45, 55)
            ImageDraw.Draw(source).text((33, 29), 'Welcome, player', font=font, fill=foreground)
            sources.enter_context(source_window(source, x, y))
            capture = core.capture_bgra(x, y, 280, 110)
            assert capture['changed']
            assert Image.frombytes('RGB', source.size, capture['bgra'], 'raw', 'BGRX').tobytes() == source.tobytes()
            state = render(core, [{**fixed_item(x, y, ' '), '_track_id': 2903,
                                  'bg': [0, 0, 0], 'fg': foreground}])[0]
            assert_atomic(state)
            assert state['aero'] and not state['background_suppressed'], (index, state)
            actual = print_window(state['hwnd'], diagnostic_overlay=True)
            assert actual.getpixel((0, 0)) == background
            assert actual.getpixel((199, 41)) == background
            assert min(pair[0] for pair in actual.getextrema()) > 0
            if samples:
                assert state['background_frame'] > samples[-1]['background_frame']
                assert state['background_builds'] > samples[-1]['background_builds']
            samples.append(dict(background=background, foreground=foreground,
                background_frame=state['background_frame'], background_builds=state['background_builds'],
                sha256=hashlib.sha256(actual.tobytes()).hexdigest()))
        render(core, [])
    EVIDENCE.append(dict(kind='changed-source-background', samples=samples,
                         stale_patch_or_black_fallback=False))
