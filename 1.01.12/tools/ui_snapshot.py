# SPDX-License-Identifier: MIT
"""Capture this application's actual idle Tk UI without activation/input calls.

Uses only this process's HWND. No game is launched, no input is injected, and no
API request is made. The five actual idle pages are captured for visual review.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nkc_galgame_translator.app import App, BRAND
from nkc_galgame_translator import app as app_module
from nkc_galgame_translator import __version__

user32 = C.WinDLL("user32", use_last_error=True)
gdi32 = C.WinDLL("gdi32", use_last_error=True)
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND,C.POINTER(W.DWORD)]
user32.GetAncestor.argtypes = [W.HWND, W.UINT]
user32.GetAncestor.restype = W.HWND
user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.GetWindowDC.argtypes = [W.HWND]
user32.GetWindowDC.restype = W.HDC
user32.ReleaseDC.argtypes = [W.HWND, W.HDC]
user32.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
user32.ShowWindow.argtypes = [W.HWND, C.c_int]
user32.UpdateWindow.argtypes = [W.HWND]
user32.GetWindowLongPtrW.argtypes = [W.HWND, C.c_int]
user32.GetWindowLongPtrW.restype = C.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [W.HWND, C.c_int, C.c_ssize_t]
user32.SetWindowLongPtrW.restype = C.c_ssize_t
gdi32.CreateCompatibleDC.argtypes = [W.HDC]
gdi32.CreateCompatibleDC.restype = W.HDC
gdi32.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
gdi32.CreateCompatibleBitmap.restype = W.HBITMAP
gdi32.SelectObject.argtypes = [W.HDC, W.HANDLE]
gdi32.SelectObject.restype = W.HANDLE
gdi32.DeleteObject.argtypes = [W.HANDLE]
gdi32.DeleteDC.argtypes = [W.HDC]


class BitmapInfoHeader(C.Structure):
    _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                ("planes", W.WORD), ("bit_count", W.WORD), ("compression", W.DWORD),
                ("image_size", W.DWORD), ("xppm", W.LONG), ("yppm", W.LONG),
                ("used", W.DWORD), ("important", W.DWORD)]


gdi32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.POINTER(BitmapInfoHeader), W.UINT]


def print_own_window(hwnd):
    rect = W.RECT()
    if not user32.GetWindowRect(hwnd, C.byref(rect)):
        raise C.WinError(C.get_last_error())
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetWindowDC(hwnd)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    previous = gdi32.SelectObject(memory, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory, 2):
            raise RuntimeError("PrintWindow could not render this application's window")
        gdi32.SelectObject(memory, previous)
        previous = None
        info = BitmapInfoHeader(C.sizeof(BitmapInfoHeader), width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        pixels = C.create_string_buffer(width * height * 4)
        if gdi32.GetDIBits(memory, bitmap, 0, height, pixels, C.byref(info), 0) != height:
            raise RuntimeError("Could not read rendered window pixels")
        return Image.frombytes("RGB", (width, height), pixels.raw, "raw", "BGRX")
    finally:
        if previous:
            gdi32.SelectObject(memory, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, screen)


def main():
    foreground_before = user32.GetForegroundWindow()
    focus_observations=[]
    def observe_focus(stage):
        current=user32.GetForegroundWindow()
        if current!=foreground_before:
            pid=W.DWORD()
            user32.GetWindowThreadProcessId(current,C.byref(pid))
            assert pid.value==os.getpid(),'External foreground changed; preview stopped'
            focus_observations.append({'stage':stage,'own_window_received_focus':True})
    original_tk = tk.Tk
    def hidden_tk(*args, **kwargs):
        root = original_tk(*args, **kwargs)
        root.withdraw()
        handle = user32.GetAncestor(root.winfo_id(), 2)
        style = user32.GetWindowLongPtrW(handle, -20)
        user32.SetWindowLongPtrW(handle, -20, style | 0x08000000)
        return root
    tk.Tk = hidden_tk
    fixture = tempfile.TemporaryDirectory(prefix='nishokuchou-preview-')
    preview_root = Path(fixture.name)
    shutil.copytree(ROOT/'assets', preview_root/'assets')
    (preview_root/'config').mkdir()
    (preview_root/'config/example.json').write_text('{"api_key":"","offline_only":true}',encoding='utf-8')
    app_module.ROOT = preview_root
    try:
        app = App(show_setup=False)
    finally:
        tk.Tk = original_tk
    reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    try:
        # Hide unrelated user window titles. Never bind/capture a game.
        app.windows_box['values']=['\u672a\u8fde\u63a5\u6e38\u620f · \u754c\u9762\u9884\u89c8']
        app.windows_box.current(0)
        app.region_label.configure(text='\u5c1a\u672a\u9009\u62e9\u533a\u57df')
        app.offline_only.set(True)
        app.status.set('\u5c31\u7eea · \u4ec5\u6d4f\u89c8\u5386\u53f2\u8d44\u6599 · \u754c\u9762\u9884\u89c8\uff0c\u672a\u8fde\u63a5\u6e38\u620f')
        app.metric.set('\u672a\u5f00\u59cb\u8bc6\u522b')
        app.root.geometry('980x820+20000+20000')
        hwnd=user32.GetAncestor(app.root.winfo_id(),2)
        style=user32.GetWindowLongPtrW(hwnd,-20)
        user32.SetWindowLongPtrW(hwnd,-20,style|0x08000000)
        app.root.update_idletasks()
        hwnd=user32.GetAncestor(app.root.winfo_id(),2)
        style=user32.GetWindowLongPtrW(hwnd,-20)
        user32.SetWindowLongPtrW(hwnd,-20,style|0x08000000)
        observe_focus('after_tk_preparation')
        user32.ShowWindow(hwnd,4)
        app.root.update();user32.UpdateWindow(hwnd)
        names=['ui-screen-translation.png','ui-translation-codebook.png','ui-text-translation.png','ui-user-agreement.png','ui-settings.png']
        frames=[]
        for index,name in enumerate(names):
            app.tabs.select(index)
            app.root.update();user32.UpdateWindow(hwnd)
            observe_focus('page_'+str(index))
            shot=print_own_window(hwnd);shot.save(reports/name);frames.append(shot)
            # Footer remains inside the client area on every tab.
            assert app.root.winfo_height()==820
        app.root.geometry('850x720+20000+20000')
        app.root.update()
        app.tabs.select(0)
        app.root.update();user32.UpdateWindow(hwnd)
        print_own_window(hwnd).save(reports/'ui-screen-minimum.png')
        app.run_canvas.yview_moveto(1)
        app.root.update();user32.UpdateWindow(hwnd)
        print_own_window(hwnd).save(reports/'ui-screen-minimum-bottom.png')
        app.tabs.select(4)
        app.settings_canvas.yview_moveto(1)
        app.root.update();user32.UpdateWindow(hwnd)
        print_own_window(hwnd).save(reports/'ui-settings-minimum-bottom.png')
        observe_focus('minimum_size_preview')
        width,height=frames[0].size
        sheet=Image.new('RGB',(width*2,height*3+94),'#F7F3EE')
        draw=ImageDraw.Draw(sheet)
        font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
        draw.text((20,14),f'{BRAND} {__version__} · \u4e94\u9875 MVP · \u65e5\u7cfb\u7ea2\u767d\u754c\u9762',fill='#302E2B',font=font)
        draw.text((20,49),'\u5b9e\u9645\u5e94\u7528\u7a7a\u95f2\u754c\u9762 / \u4ec5\u6d4f\u89c8\u5386\u53f2\u8d44\u6599 / \u672a\u8fde\u63a5\u6e38\u620f / \u65e0 API \u8bf7\u6c42',fill='#756D65',font=font)
        for index,frame in enumerate(frames):sheet.paste(frame,((index%2)*width,94+(index//2)*height))
        sheet.save(reports/'ui-red-white-overview.png')
        user32.ShowWindow(hwnd,0)
        report={'version':__version__,'brand':BRAND,'theme':'vermilion, warm white, charcoal',
                'images':names+['ui-screen-minimum.png','ui-screen-minimum-bottom.png','ui-settings-minimum-bottom.png','ui-red-white-overview.png'],
                'pages':len(app.tabs.tabs()),'offline_only_preview':bool(app.offline_only.get()),
                'profile_choices':list(app.profile_box['values']),'optional_profile':True,
                'capture':'PrintWindow of actual idle application UI','foreground_unchanged':not focus_observations,
                'focus_observations':focus_observations,'explicit_activation_calls':0,
                'game_launched':False,'network_requests':0,'game_memory_writes':0,
                'reviewed_window_sizes':[[980,820],[850,720]],'credential_fields_displayed':False}
        (reports/'ui_snapshot.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        app.close()
        app_module.ROOT = ROOT
        fixture.cleanup()
    assert user32.GetForegroundWindow()==foreground_before,'Preview cleanup changed foreground'


if __name__=='__main__':main()
