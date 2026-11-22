"""SPDX-License-Identifier: MIT
Thin ctypes bridge. Capture/OCR work runs in native code and releases Python's GIL.
"""
from __future__ import annotations

import ctypes
import json
from pathlib import Path
import threading
import sys
import re
import unicodedata
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from .input_paths import local_file_path
from collections.abc import Mapping


# WinRT factory caches outlive a single query. Keep one initialized MTA alive
# until Python process shutdown, instead of repeatedly tearing down the last
# MTA and invalidating cached activation factories. The executor joins at exit.
_language_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ocr-language-mta')
_language_submit_lock = threading.Lock()


def video_memory_mb(root, vendor=0):
    try:
        path=local_file_path(Path(root)/'native/bin/nkc_galgame_translator_core.dll')
        library=ctypes.CDLL(str(path),winmode=0x00000100|0x00000800)
        probe=library.gl_video_memory_mb
        probe.argtypes=[ctypes.c_uint32]
        probe.restype=ctypes.c_uint64
        return int(probe(vendor))
    except (OSError,ValueError,AttributeError):
        return 0


def _integer(value, minimum, maximum, label):
    if isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum:
        raise ValueError(f'Invalid {label}')
    return value


def _capture_bounds(x,y,w,h):
    x=_integer(x,-2147483648,2147483647,'capture x')
    y=_integer(y,-2147483648,2147483647,'capture y')
    w=_integer(w,1,4096,'capture width');h=_integer(h,1,4096,'capture height')
    if x+w>2147483647 or y+h>2147483647:raise ValueError('Capture bounds overflow')
    return x,y,w,h


class _Region(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32),
                ("width", ctypes.c_int32), ("height", ctypes.c_int32),
                ("background", ctypes.c_uint32), ("foreground", ctypes.c_uint32),
                ("font_size", ctypes.c_int32), ("final", ctypes.c_int32), ("text", ctypes.c_wchar_p),
                ("track_id", ctypes.c_uint64), ("revision", ctypes.c_uint64)]


class _SourceRow(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int32) for name in
                ('x', 'y', 'width', 'height', 'ink_x', 'ink_y',
                 'ink_width', 'ink_height', 'font_size')]


def fixed_source_rows(region):
    """Validate local source geometry; never infer character positions from text.

    Coordinates are relative to the containing overlay. Explicit OCR row/ink
    bounds take precedence. A legacy multiline object without physical bounds
    receives equal-height slots, bounded by the supplied original rectangle.
    """
    if not region.get('_fixed_layout'):
        return []
    width, height = region['w'], region['h']
    rows = region.get('_source_rows')
    if rows is None:
        count = _integer(region.get('_source_line_count', 1), 1, 32, 'source line count')
        if count > height:
            raise ValueError('Source rows exceed rectangle height')
        rows = []
        for index in range(count):
            top, bottom = height * index // count, height * (index + 1) // count
            row = dict(x=0, y=top, w=width, h=bottom-top, font_size=0)
            if count == 1 and region.get('_source_ink') is not None:
                ink = region['_source_ink']
                if not isinstance(ink, (list, tuple)) or len(ink) != 4:
                    raise ValueError('Invalid source ink bounds')
                ix, iy, iw, ih = ink
                for value in ink:
                    _integer(value, -2147483648, 2147483647, 'source ink bounds')
                row['ink_bounds'] = [ix-region['x'], iy-region['y'], iw, ih]
            elif count == 1:
                row['font_size'] = region.get('font_size', 0)
            rows.append(row)
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 32:
        raise ValueError('Invalid source rows')
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError('Invalid source row')
        x = _integer(row.get('x'), 0, width-1, 'source row x')
        y = _integer(row.get('y'), 0, height-1, 'source row y')
        w = _integer(row.get('w'), 1, width-x, 'source row width')
        h = _integer(row.get('h'), 1, height-y, 'source row height')
        ink = row.get('ink_bounds', (x, y, w, h))
        if not isinstance(ink, (list, tuple)) or len(ink) != 4:
            raise ValueError('Invalid source row ink')
        ix = _integer(ink[0], x, x+w-1, 'ink x')
        iy = _integer(ink[1], y, y+h-1, 'ink y')
        iw = _integer(ink[2], 1, x+w-ix, 'ink width')
        ih = _integer(ink[3], 1, y+h-iy, 'ink height')
        font = _integer(row.get('font_size', 0), 0, 512, 'source row font')
        result.append(_SourceRow(x, y, w, h, ix, iy, iw, ih, font))
    return result


def _color(value):
    r, g, b = (max(0, min(255, int(v))) for v in value)
    return r | (g << 8) | (b << 16)


class NativeCore:
    def __init__(self, dll_path=None):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise RuntimeError("NKC_Galgame_Translator requires 64-bit Python on Windows x64")
        root = Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]
        try:
            path = local_file_path(Path(dll_path) if dll_path else root / "native" / "bin" / "nkc_galgame_translator_core.dll")
        except (OSError,ValueError,TypeError):
            raise RuntimeError('Native core missing or invalid. Use the local release folder or run native/build.ps1.') from None
        # Absolute DLL; dependencies may only come from its directory/System32.
        self._dll = ctypes.CDLL(str(path),winmode=0x00000100|0x00000800)
        try:
            self._dll.gl_abi_version.argtypes=[]
            self._dll.gl_abi_version.restype=ctypes.c_uint32
            compatible=(self._dll.gl_abi_version()==2 and hasattr(self._dll,'gl_set_font')
                        and hasattr(self._dll,'gl_ocr_bgra') and hasattr(self._dll,'gl_overlay_options')
                        and hasattr(self._dll,'gl_overlay_anchored'))
        except AttributeError:
            compatible=False
        if not compatible:
            raise RuntimeError('\u539f\u751f\u6838\u5fc3\u7248\u672c\u4e0d\u5339\u914d\uff0c\u8bf7\u4f7f\u7528\u672c\u7248\u672c\u9644\u5e26\u7684 DLL \u6216\u91cd\u65b0\u8fd0\u884c native/build.ps1\u3002')
        self._lifecycle = threading.Condition(threading.RLock())
        self._capture_lock = threading.RLock()
        self._active_operations = 0
        self._closing = False
        self._dll.gl_create.argtypes = []
        self._dll.gl_create.restype = ctypes.c_void_p
        self._dll.gl_destroy.argtypes = [ctypes.c_void_p]
        self._dll.gl_destroy.restype = None
        self._dll.gl_languages.argtypes = []
        self._dll.gl_languages.restype = ctypes.c_char_p
        self._dll.gl_capture_ocr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        self._dll.gl_capture_ocr.restype = ctypes.c_char_p
        self._dll.gl_capture_frame.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self._dll.gl_capture_frame.restype = ctypes.c_char_p
        self._dll.gl_copy_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
        self._dll.gl_copy_frame.restype = ctypes.c_int
        self._dll.gl_ocr_bgra.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_wchar_p]
        self._dll.gl_ocr_bgra.restype = ctypes.c_char_p
        self._dll.gl_reset.argtypes = [ctypes.c_void_p]
        self._dll.gl_reset.restype = None
        self._dll.gl_overlay.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Region), ctypes.c_int]
        self._dll.gl_overlay.restype = ctypes.c_int
        if hasattr(self._dll, 'gl_overlay_fixed'):
            self._dll.gl_overlay_fixed.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Region), ctypes.c_int,
                ctypes.POINTER(_SourceRow), ctypes.c_int, ctypes.POINTER(ctypes.c_int32)]
            self._dll.gl_overlay_fixed.restype = ctypes.c_int
        self._dll.gl_overlay_anchored.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Region), ctypes.c_int,
            ctypes.POINTER(_SourceRow), ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]
        self._dll.gl_overlay_anchored.restype = ctypes.c_int
        self._font_selector = None
        if hasattr(self._dll, 'gl_overlay_styled'):
            self._dll.gl_overlay_styled.argtypes = self._dll.gl_overlay_anchored.argtypes + [ctypes.POINTER(ctypes.c_wchar_p),ctypes.POINTER(ctypes.c_int32)]
            self._dll.gl_overlay_styled.restype = ctypes.c_int
        if hasattr(self._dll, 'gl_overlay_labels'):
            self._dll.gl_overlay_labels.argtypes = self._dll.gl_overlay_styled.argtypes + [ctypes.POINTER(ctypes.c_int32)]
            self._dll.gl_overlay_labels.restype = ctypes.c_int
            self._dll.gl_font_supports.argtypes = [ctypes.c_wchar_p,ctypes.c_wchar_p]
            self._dll.gl_font_supports.restype = ctypes.c_int
        self._dll.gl_set_font.argtypes = [ctypes.c_void_p,ctypes.c_wchar_p]
        self._dll.gl_set_font.restype = ctypes.c_int
        self._dll.gl_overlay_options.argtypes = [ctypes.c_void_p] + [ctypes.c_int]*5
        self._dll.gl_overlay_options.restype = ctypes.c_int
        self._dll.gl_overlay_snapshot.argtypes = [ctypes.c_void_p]
        self._dll.gl_overlay_snapshot.restype = ctypes.c_char_p
        self._dll.gl_hide.argtypes = [ctypes.c_void_p]
        self._dll.gl_hide.restype = None
        self._dll.gl_set_target.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]
        self._dll.gl_set_target.restype = None
        if hasattr(self._dll, 'gl_prefer_game_capture'):
            self._dll.gl_prefer_game_capture.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self._dll.gl_prefer_game_capture.restype = None
        self._dll.gl_error.argtypes = []
        self._dll.gl_error.restype = ctypes.c_char_p
        self._context = self._dll.gl_create()
        if not self._context:
            raise RuntimeError(self._dll.gl_error().decode("utf-8", "replace"))

    @contextmanager
    def _operation(self, allow_closed=False):
        # Hold the lifecycle condition only while pinning/unpinning the context.
        # Long OCR calls must not serialize the UI's overlay updates.
        with self._lifecycle:
            context = self._context if not self._closing else None
            if context:
                self._active_operations += 1
            elif not allow_closed:
                raise RuntimeError("NativeCore is closed")
        try:
            yield context
        finally:
            if context:
                with self._lifecycle:
                    self._active_operations -= 1
                    self._lifecycle.notify_all()

    @staticmethod
    def _decode(raw):
        if not raw:
            raise RuntimeError("Native core returned an empty response")
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(data["error"])
        return data

    def languages(self) -> list[str]:
        # Tk may initialize the caller as STA. Enumerate on the process-owned
        # MTA worker, and decode its thread-local JSON buffer before returning.
        def enumerate_languages():
            with self._operation():
                return self._decode(self._dll.gl_languages())
        # Synchronous callers wait here rather than filling an executor queue.
        with _language_submit_lock:
            return _language_executor.submit(enumerate_languages).result()

    def capture_ocr(self, x: int, y: int, w: int, h: int, language: str = "en") -> dict:
        x,y,w,h=_capture_bounds(x,y,w,h)
        if not isinstance(language,str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language) or len(language)>64:
            raise ValueError('Invalid OCR language')
        with self._capture_lock, self._operation() as context:
            return self._decode(self._dll.gl_capture_ocr(context, int(x), int(y), int(w), int(h), language))

    def reset(self):
        with self._capture_lock, self._operation() as context:
            self._dll.gl_reset(context)

    def capture_bgra(self, x, y, w, h):
        """Capture once in C++; return BGRA bytes only when the complete RGB frame changes."""
        x,y,w,h=_capture_bounds(x,y,w,h)
        with self._capture_lock, self._operation() as context:
            result = self._decode(self._dll.gl_capture_frame(context, int(x), int(y), int(w), int(h)))
            result["bgra"] = None
            if result["changed"]:
                count = int(w) * int(h) * 4
                data = (ctypes.c_ubyte * count)()
                if self._dll.gl_copy_frame(context, data, count) != count:
                    raise RuntimeError("Native frame copy failed")
                result["bgra"] = bytes(data)
            return result

    def recognize_bgra(self, bgra: bytes, width: int, height: int, language: str = 'en'):
        """Recognize a fixed frame on this MTA worker; preserve capture change state."""
        width=_integer(width,1,4096,'image width');height=_integer(height,1,4096,'image height')
        if not isinstance(bgra,bytes) or len(bgra)!=width*height*4:
            raise ValueError('Invalid BGRA image buffer')
        if not isinstance(language,str) or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*',language) or len(language)>64:
            raise ValueError('Invalid OCR language')
        with self._operation():
            return self._decode(self._dll.gl_ocr_bgra(bgra,len(bgra),width,height,language))

    def set_overlay_font(self, family: str):
        """Set a context-local GDI family; new names reset fit asynchronously."""
        if (not isinstance(family,str) or not family.strip()
                or any(unicodedata.category(ch) in ('Cc','Cf','Cs') for ch in family)):
            raise ValueError('Invalid overlay font family')
        if len(family.encode('utf-16-le'))//2>31:
            raise ValueError('Overlay font family exceeds 31 UTF-16 units')
        with self._operation() as context:
            if not self._dll.gl_set_font(context,family):
                raise RuntimeError('Native overlay font could not be applied')

    def set_overlay_options(self, *, auto_font_size=True, overlay_font_size=24,
                            overlay_font_min=8, overlay_font_max=72, capture_translations=True):
        if type(auto_font_size) is not bool or type(capture_translations) is not bool:
            raise ValueError('Invalid overlay option flags')
        for value in (overlay_font_size, overlay_font_min, overlay_font_max):
            _integer(value, 8, 512, 'overlay font size')
        if overlay_font_min > overlay_font_max:
            raise ValueError('Invalid overlay font range')
        with self._operation() as context:
            if not self._dll.gl_overlay_options(context, auto_font_size, overlay_font_size,
                    overlay_font_min, overlay_font_max, capture_translations):
                raise RuntimeError('Native overlay options could not be applied')

    def font_supports(self, family, text):
        from .tuning import validate_font_family
        family=validate_font_family(family)
        if not isinstance(text,str) or len(text)>4096 or '\x00' in text:return False
        if any(ord(c)>0xffff or 0xd800<=ord(c)<=0xdfff for c in text):return False
        with self._operation():
            return bool(self._dll.gl_font_supports(family,text))

    def set_auto_font_style(self, enabled, target='zh-Hans'):
        if type(enabled) is not bool:raise ValueError('Invalid font style option')
        if enabled and not hasattr(self._dll,'gl_overlay_styled'):
            raise RuntimeError('Automatic font styles require this version native DLL')
        from .font_style import TargetFontSelector
        self._font_selector=TargetFontSelector(self.font_supports,target) if enabled else None

    def show_overlay(self, regions: list[dict]):
        if not isinstance(regions,(list,tuple)) or len(regions)>512:raise ValueError('Too many overlay regions')
        selector=getattr(self,'_font_selector',None)
        if selector is not None:
            styled=[]
            for region in regions:
                if not isinstance(region,dict):raise ValueError('Invalid overlay region')
                text=region.get('text','')
                if not isinstance(text,str) or len(text)>64000 or '\x00' in text:raise ValueError('Invalid overlay text')
                choice=selector.choose(region.get('_source_font_style','sans'),text)
                if choice is None and region.get('_cover_source'):
                    region={**region,'text':''}
                    choice=selector.choose('sans','') or ('Microsoft YaHei UI',False)
                if choice is not None:
                    styled.append({**region,'_font_family':choice[0],'_font_pixel':choice[1]})
            regions=styled
        total=0
        row_data, offsets, origins = [], [0], []
        anchored = bool(regions) and all(isinstance(r,dict) and '_capture_origin' in r for r in regions)
        for region in regions:
            if not isinstance(region,dict):raise ValueError('Invalid overlay region')
            for field in ('x','y'):_integer(region.get(field),-2147483648,2147483647,field)
            for field in ('w','h'):_integer(region.get(field),1,8192,field)
            if region['x']+region['w']>2147483647 or region['y']+region['h']>2147483647:raise ValueError('Overlay bounds overflow')
            for field in ('_track_id','_revision'):_integer(region.get(field,0),0,18446744073709551615,field)
            _integer(region.get('font_size',0),0,512,'font size')
            text=region.get('text','')
            if not isinstance(text,str) or '\x00' in text:raise ValueError('Invalid overlay text')
            try:units=len(text.encode('utf-16-le'))//2
            except UnicodeError:raise ValueError('Invalid overlay Unicode') from None
            total+=units
            if units>64000 or total>1048576:raise ValueError('Overlay text exceeds limit')
            row_data.extend(fixed_source_rows(region))
            offsets.append(len(row_data))
            if anchored:
                origin=region['_capture_origin']
                if not isinstance(origin,(list,tuple)) or len(origin)!=2:raise ValueError('Invalid capture origin')
                origins.extend(_integer(v,-2147483648,2147483647,'capture origin') for v in origin)
        with self._operation() as context:
            array = (_Region * len(regions))(*[
                _Region(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"]),
                        _color(r.get("bg", [25, 25, 25])), _color(r.get("fg", [245, 245, 245])),
                        int(r.get("font_size", 0)), int(bool(r.get("final",True))), str(r.get("text", "")),
                        int(r.get("_track_id",0)), int(r.get("_revision",0)))
                for r in regions])
            centered = [int(bool(r.get('_center_label'))) | (2 if r.get('_flash_hold') else 0)
                        | (4 if r.get('_hold_previous') else 0) | (8 if r.get('_cover_source') else 0)
                        | (16 if r.get('_subtitle_read') and r.get('_fixed_layout') else 0)
                        | (32 if '_aoi_button' in r and r.get('_center_label') else 0)
                        | (64 if r.get('_aoi_toolbar') and r.get('_center_label') else 0)
                        | (128 if r.get('_standalone_subtitle') and r.get('_fixed_layout') else 0)
                        for r in regions]
            if any(centered) and hasattr(self._dll, 'gl_overlay_labels'):
                rows = (_SourceRow*len(row_data))(*row_data)
                starts = (ctypes.c_int32*len(offsets))(*offsets)
                anchor_data = (ctypes.c_int32*len(origins))(*origins) if anchored else None
                families = (ctypes.c_wchar_p*len(regions))(*(r['_font_family'] for r in regions)) if selector is not None else None
                pixels = (ctypes.c_int32*len(regions))(*(int(r['_font_pixel']) for r in regions)) if selector is not None else None
                flags = (ctypes.c_int32*len(regions))(*centered)
                accepted = self._dll.gl_overlay_labels(context,array,len(regions),rows,len(rows),starts,anchor_data,families,pixels,flags)
            elif selector is not None:
                rows=(_SourceRow*len(row_data))(*row_data)
                starts=(ctypes.c_int32*len(offsets))(*offsets)
                anchor_data=(ctypes.c_int32*len(origins))(*origins) if anchored else None
                families=(ctypes.c_wchar_p*len(regions))(*(r['_font_family'] for r in regions))
                pixels=(ctypes.c_int32*len(regions))(*(int(r['_font_pixel']) for r in regions))
                accepted=self._dll.gl_overlay_styled(context,array,len(regions),rows,len(rows),starts,anchor_data,families,pixels)
            elif row_data or anchored:
                if not hasattr(self._dll, 'gl_overlay_fixed'):
                    raise RuntimeError('Source-row layout requires this version’s native DLL.')
                rows = (_SourceRow * len(row_data))(*row_data)
                starts = (ctypes.c_int32 * len(offsets))(*offsets)
                if anchored:
                    anchor_data=(ctypes.c_int32*len(origins))(*origins)
                    accepted=self._dll.gl_overlay_anchored(context,array,len(regions),rows,len(rows),starts,anchor_data)
                else:
                    accepted = self._dll.gl_overlay_fixed(context, array, len(regions), rows, len(rows), starts)
            else:
                accepted = self._dll.gl_overlay(context, array, len(regions))
            if not accepted:
                raise RuntimeError(self._dll.gl_error().decode("utf-8", "replace"))

    def overlay_snapshot(self) -> dict:
        """Read the last completed GDI render for diagnostics; performs no capture."""
        with self._operation() as context:
            return self._decode(self._dll.gl_overlay_snapshot(context))

    def hide_overlay(self):
        with self._operation(allow_closed=True) as context:
            if context:
                self._dll.gl_hide(context)

    def prefer_game_capture(self, enabled):
        with self._operation() as context:
            if hasattr(self._dll, 'gl_prefer_game_capture'):
                self._dll.gl_prefer_game_capture(context, bool(enabled))

    def set_target(self, hwnd, pid):
        """Bind overlays to one foreground game window/PID; zero is diagnostic mode."""
        _integer(hwnd,0,18446744073709551615,'window handle')
        _integer(pid,0,4294967295,'process id')
        with self._operation() as context:
            self._dll.gl_set_target(context,int(hwnd),int(pid))

    def close(self):
        with self._lifecycle:
            if self._closing:
                while self._context:
                    self._lifecycle.wait()
                return
            if not self._context:
                return
            self._closing = True
            while self._active_operations:
                self._lifecycle.wait()
            context = self._context
        try:
            self._dll.gl_destroy(context)
        finally:
            with self._lifecycle:
                self._context = None
                self._lifecycle.notify_all()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
