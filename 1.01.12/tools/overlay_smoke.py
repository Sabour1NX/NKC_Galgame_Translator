# SPDX-License-Identifier: MIT
"""Synthetic native overlay end-to-end smoke test. No input or activation.

Creates only its own SW_SHOWNOACTIVATE fixture, observes it, and closes it.
Translations are explicitly synthetic chunks: no API calls and no game access.
"""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import struct
import sys
import time

import win32api
import win32con
import win32gui
import win32ui
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nkc_galgame_translator.ocr import OcrCore

USER32 = ctypes.WinDLL("user32",use_last_error=True)
USER32.PrintWindow.argtypes = [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint]
USER32.PrintWindow.restype = ctypes.c_int
USER32.GetWindowDisplayAffinity.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint)]
USER32.GetWindowDisplayAffinity.restype = ctypes.c_int
USER32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p,ctypes.c_uint]
USER32.SetWindowDisplayAffinity.restype = ctypes.c_int
USER32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
USER32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
GDI32=ctypes.WinDLL("gdi32",use_last_error=True)
GDI32.GetRegionData.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p]
GDI32.GetRegionData.restype=ctypes.c_uint
GDI32.CreateRectRgn.argtypes=[ctypes.c_int]*4
GDI32.CreateRectRgn.restype=ctypes.c_void_p
GDI32.DeleteObject.argtypes=[ctypes.c_void_p]
USER32.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
USER32.GetWindowRgn.restype=ctypes.c_int
NOACTIVATE = 0x08000000
BG = (28,38,55)
SOURCE_EN = "Welcome to the Scarlet Mansion."
SOURCE_JA = "\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002"
SOURCE_JA_FONT = "MS Gothic"
SOURCE_JA_SIZE = 32
FINAL = "\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986\u3002"


def fixture_paint(hwnd,dc):
    rect = win32gui.GetClientRect(hwnd)
    brush=win32gui.CreateSolidBrush(win32api.RGB(*BG))
    win32gui.FillRect(dc,rect,brush); win32gui.DeleteObject(brush)
    font=win32ui.CreateFont({"name":"Microsoft YaHei UI","height":-30,"weight":400})
    previous=win32gui.SelectObject(dc,font.GetSafeHandle())
    win32gui.SetBkMode(dc,win32con.TRANSPARENT)
    win32gui.SetTextColor(dc,win32api.RGB(245,245,245))
    win32gui.DrawText(dc,SOURCE_EN,-1,(24,36,850,80),win32con.DT_LEFT|win32con.DT_SINGLELINE|win32con.DT_NOPREFIX)
    # Render Japanese with a Japanese face rather than Chinese-font fallback.
    # This fixture must pass the production confidence gate unchanged.
    japanese_font=win32ui.CreateFont({"name":SOURCE_JA_FONT,"height":-SOURCE_JA_SIZE,"weight":400})
    win32gui.SelectObject(dc,japanese_font.GetSafeHandle())
    win32gui.DrawText(dc,SOURCE_JA,-1,(24,132,850,180),win32con.DT_LEFT|win32con.DT_SINGLELINE|win32con.DT_NOPREFIX)
    win32gui.SelectObject(dc,previous)


def fixture_proc(hwnd,msg,wp,lp):
    if msg==win32con.WM_PAINT:
        dc,paint=win32gui.BeginPaint(hwnd)
        try: fixture_paint(hwnd,dc)
        finally: win32gui.EndPaint(hwnd,paint)
        return 0
    if msg==win32con.WM_PRINTCLIENT:
        fixture_paint(hwnd,wp); return 0
    if msg==win32con.WM_MOUSEACTIVATE:return 3
    if msg==win32con.WM_NCHITTEST:return -1
    return win32gui.DefWindowProc(hwnd,msg,wp,lp)


def print_window(hwnd, diagnostic_overlay=False):
    left,top,right,bottom=win32gui.GetWindowRect(hwnd)
    width,height=right-left,bottom-top
    window_dc=win32gui.GetWindowDC(hwnd)
    source=win32ui.CreateDCFromHandle(window_dc)
    target=source.CreateCompatibleDC()
    bitmap=win32ui.CreateBitmap(); bitmap.CreateCompatibleBitmap(source,width,height)
    old=target.SelectObject(bitmap)
    try:
        target.FillSolidRect((0,0,width,height),0)
        # PrintWindow is also excluded by WDA on this Windows build. Temporarily
        # lift only this owned synthetic window's capture flag for diagnostics.
        if diagnostic_overlay:
            assert USER32.SetWindowDisplayAffinity(hwnd,0)
            ctypes.windll.dwmapi.DwmFlush()
        if not USER32.PrintWindow(hwnd,target.GetSafeHdc(),2):
            raise RuntimeError("PrintWindow failed")
        data=bitmap.GetBitmapBits(True)
        return Image.frombytes("RGB",(width,height),data,"raw","BGRX",0,1)
    finally:
        if diagnostic_overlay: USER32.SetWindowDisplayAffinity(hwnd,0x11)
        target.SelectObject(old)
        win32gui.DeleteObject(bitmap.GetHandle())
        target.DeleteDC(); source.DeleteDC(); win32gui.ReleaseDC(hwnd,window_dc)


def window_mask(hwnd):
    left,top,right,bottom=win32gui.GetWindowRect(hwnd)
    mask=Image.new("L",(right-left,bottom-top),0)
    region=GDI32.CreateRectRgn(0,0,0,0)
    try:
        kind=USER32.GetWindowRgn(hwnd,region)
        if kind==0:
            return Image.new("L",mask.size,255),[(0,0,*mask.size)]
        size=GDI32.GetRegionData(region,0,None)
        data=ctypes.create_string_buffer(size)
        assert GDI32.GetRegionData(region,size,data)==size
        header=struct.unpack_from("<4I4l",data.raw)
        rectangles=[struct.unpack_from("<4l",data.raw,32+i*16) for i in range(header[2])]
        draw=ImageDraw.Draw(mask)
        for x1,y1,x2,y2 in rectangles:
            if x2>x1 and y2>y1: draw.rectangle((x1,y1,x2-1,y2-1),fill=255)
        return mask,rectangles
    finally:GDI32.DeleteObject(region)


def overlays():
    found=[]
    def visit(hwnd,_):
        _,pid=win32process.GetWindowThreadProcessId(hwnd)
        if pid==os.getpid() and win32gui.GetClassName(hwnd)=="NKC_Galgame_TranslatorReplacement":found.append(hwnd)
    import win32process
    win32gui.EnumWindows(visit,None)
    return found


def wait_overlay():
    end=time.perf_counter()+2
    while time.perf_counter()<end:
        win32gui.PumpWaitingMessages()
        windows=overlays()
        if windows:return windows[0]
        time.sleep(.01)
    raise RuntimeError("Native replacement window did not appear")


def main():
    report_dir=ROOT/"reports"; report_dir.mkdir(exist_ok=True)
    before_foreground=win32gui.GetForegroundWindow()
    instance=win32api.GetModuleHandle(None)
    cls=win32gui.WNDCLASS(); cls.hInstance=instance; cls.lpszClassName="NKC_Galgame_TranslatorSyntheticFixture"; cls.lpfnWndProc=fixture_proc
    atom=win32gui.RegisterClass(cls)
    width,height=900,240
    vx,vy=win32api.GetSystemMetrics(76),win32api.GetSystemMetrics(77)
    vw,vh=win32api.GetSystemMetrics(78),win32api.GetSystemMetrics(79)
    x,y=vx+max(0,(vw-width)//2),vy+max(0,(vh-height)//2)
    hwnd=win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST|NOACTIVATE|win32con.WS_EX_TOOLWINDOW,
        atom,"NKC_Galgame_Translator synthetic OCR fixture",win32con.WS_POPUP,x,y,width,height,0,0,instance,None)
    report={"kind":"synthetic own-window end-to-end demo, not game capture", "api_used":False,"stream_source":"fixed synthetic accumulated chunks"}
    core=None
    try:
        win32gui.ShowWindow(hwnd,win32con.SW_SHOWNOACTIVATE); win32gui.UpdateWindow(hwnd)
        win32gui.PumpWaitingMessages(); time.sleep(.08)
        assert win32gui.GetForegroundWindow()==before_foreground,"Fixture changed foreground"
        original=print_window(hwnd); original.save(report_dir/"synthetic-overlay-original.png")
        core=OcrCore()
        en=core.capture_ocr(x,y,width,height,"en")
        candidates=[line for line in en["lines"] if "Scarlet" in line["text"]]
        assert candidates,en
        line=candidates[0]
        japanese=core.capture_ocr(x,y,width,height,"ja")
        assert any("\u3088\u3046\u3053\u305d" in item["text"] for item in japanese["lines"]),japanese
        ja_line=next(item for item in japanese["lines"] if "\u3088\u3046\u3053\u305d" in item["text"])
        if "confidence" in ja_line:
            assert ja_line["confidence"]>=japanese["min_confidence"]
        report["japanese_fixture_font"]={"face":SOURCE_JA_FONT,"pixels":SOURCE_JA_SIZE}
        report["japanese_ocr_confidence"]=ja_line.get("confidence")
        report["production_min_confidence"]=japanese.get("min_confidence")
        report["english_ocr_ms"]=en["ocr_ms"]; report["japanese_ocr_ms"]=japanese["ocr_ms"]
        report["english_source"]=line["text"]
        report["japanese_sources"]=[item["text"] for item in japanese["lines"]]
        report["recognized_rectangle"]={k:line[k] for k in ("x","y","w","h","bg")}
        stages=[]; pictures=[]; composites=[]
        # Empty partial output covers nothing; the mask grows with rendered text.
        for text,complete in (("",False),("\u6b22\u8fce",False),("\u6b22\u8fce\u6765\u5230",False),(FINAL,True)):
            region={**line,"text":text,"final":complete}
            core.show_overlay([region]); overlay=wait_overlay(); time.sleep(.045)
            mask,rectangles=window_mask(overlay)
            masked_area=mask.histogram()[255]
            shot=print_window(overlay,diagnostic_overlay=True) if masked_area else Image.new("RGB",mask.size)
            composed=original.copy(); composed.paste(shot,(line["x"]-x,line["y"]-y),mask)
            digest=hashlib.sha256(composed.tobytes()).hexdigest()
            stages.append({"text":text,"final":complete,"pixel_sha256":digest,"size":list(shot.size),
                           "masked_area":masked_area,"mask_rectangles":rectangles})
            pictures.append(shot)
            composites.append(composed)
            if not complete: assert mask.getpixel((line["w"]-1,line["h"]-1))==0
            else: assert masked_area==line["w"]*line["h"]
        assert len({stage["pixel_sha256"] for stage in stages})==4,"Streaming did not repaint distinct chunks"
        assert stages[0]["masked_area"]==0,"Initial empty text must not cover the source"
        assert 0<stages[1]["masked_area"]<stages[2]["masked_area"]<stages[3]["masked_area"]
        assert composites[0].tobytes()==original.tobytes(),"Initial source must remain untouched"
        style=win32gui.GetWindowLong(overlay,win32con.GWL_EXSTYLE)
        assert style&NOACTIVATE and style&win32con.WS_EX_TRANSPARENT and style&win32con.WS_EX_TOPMOST
        assert win32gui.SendMessage(overlay,win32con.WM_NCHITTEST,0,0)==-1
        affinity=ctypes.c_uint(); assert USER32.GetWindowDisplayAffinity(overlay,ctypes.byref(affinity)) and affinity.value==0x11
        core.reset(); beneath=core.capture_ocr(x,y,width,height,"en")
        assert any("Scarlet" in item["text"] for item in beneath["lines"]),beneath
        assert win32gui.GetForegroundWindow()==before_foreground,"Overlay changed foreground"
        report.update({"progressive_mask_pass":True,"final_full_cover_pass":True,"empty_partial_untouched_pass":True,
                       "stream_repaint_pass":True,"clickthrough_pass":True,"noactivate_pass":True,
                       "capture_exclusion_pass":True,"display_affinity":affinity.value,"stages":stages})
        final=pictures[-1]; final.save(report_dir/"synthetic-overlay-actual-native-window.png")
        core.show_overlay([{**line,"text":FINAL},{**ja_line,"text":FINAL}]); time.sleep(.06)
        ja_windows=[item for item in overlays() if abs(win32gui.GetWindowRect(item)[1]-ja_line["y"])<2]
        assert len(ja_windows)==1,"Japanese replacement rectangle missing"
        ja_actual=print_window(ja_windows[0],diagnostic_overlay=True)
        ja_actual.save(report_dir/"synthetic-overlay-japanese-native-window.png")
        report["japanese_replacement_pass"]=True
        report["japanese_rectangle"]={key:ja_line[key] for key in ("x","y","w","h","bg")}
        # Composite consists only of PrintWindow output from our own fixture/overlay.
        after=original.copy(); after.paste(final,(line["x"]-x,line["y"]-y))
        after.paste(ja_actual,(ja_line["x"]-x,ja_line["y"]-y))
        after.save(report_dir/"synthetic-overlay-composited-result.png")
        progressive=Image.new("RGB",(width,4*(height+38)),(238,241,247)); progressive_draw=ImageDraw.Draw(progressive)
        progressive_font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
        for index,(stage,frame) in enumerate(zip(stages,composites)):
            yy=index*(height+38)
            title=f"SYNTHETIC / {'\u5b8c\u6210\uff1a\u8986\u76d6\u5b8c\u6574\u539f\u6587\u77e9\u5f62' if stage['final'] else '\u6d41\u5f0f\uff1a\u4ec5\u8986\u76d6\u5df2\u7ed8\u5236\u6587\u5b57\u533a\u57df'} / {stage['text'] or '\u5c1a\u65e0\u8bd1\u6587\uff0c\u539f\u6587\u4fdd\u6301\u53ef\u89c1'}"
            progressive_draw.text((12,yy+6),title,font=progressive_font,fill=(20,30,50))
            progressive.paste(frame,(0,yy+38))
        progressive.save(report_dir/"synthetic-overlay-progressive-mask.png")
        proof=Image.new("RGB",(width,2*height+110),(238,241,247)); draw=ImageDraw.Draw(proof)
        font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",19)
        draw.text((16,10),"SYNTHETIC TEST / \u539f\u6587\u7a97\u53e3\uff08\u975e\u6e38\u620f\u622a\u56fe\uff09",font=font,fill=(20,30,50))
        proof.paste(original,(0,45))
        draw.text((16,height+55),"\u5b9e\u9645\u539f\u751f\u8986\u76d6\u5c42 PrintWindow \u6e32\u67d3\u5408\u6210 / \u5408\u6210\u6d41\u5f0f\u8bd1\u6587",font=font,fill=(20,30,50))
        proof.paste(after,(0,height+95)); proof.save(report_dir/"synthetic-overlay-before-after.png")
        wrap_region={"x":x+610,"y":y+30,"w":260,"h":180,"bg":list(BG),"fg":[245]*3,
                     "font_size":22,"text":"\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c\u6587\u5b57\u9010\u6e10\u51fa\u73b0\u5e76\u4e14\u81ea\u52a8\u6362\u884c\nEnglish words wrap across a narrow rectangle.","final":False}
        core.show_overlay([wrap_region]); time.sleep(.06); wrap_window=wait_overlay()
        wrap_mask,wrap_rectangles=window_mask(wrap_window)
        wrap_bounds=wrap_mask.getbbox()
        assert wrap_bounds and wrap_bounds[3]>100,"Newlines and automatic wrapping did not produce several lines"
        assert wrap_mask.getpixel((259,0))==0,"Ungenerated remainder of first line was covered"
        assert wrap_mask.histogram()[255]<260*180,"Partial wrapping covered entire rectangle"
        wrap_shot=print_window(wrap_window,diagnostic_overlay=True)
        wrap_composite=original.copy(); wrap_composite.paste(wrap_shot,(610,30),wrap_mask)
        wrap_composite.save(report_dir/"synthetic-overlay-newline-wrapping.png")
        report["newline_cjk_english_wrap_pass"]=True
        report["wrap_mask_rectangles"]=wrap_rectangles
        # Binding to this deliberately nonforeground fixture must suppress overlays.
        core.set_target(hwnd,os.getpid())
        core.show_overlay([{**line,"text":FINAL}]); time.sleep(.09)
        assert not any(win32gui.IsWindowVisible(item) for item in overlays())
        report["nonforeground_target_suppression_pass"]=True
        report["status"]="passed"
    except Exception as exc:
        report["status"]="failed"; report["error"]=repr(exc)
        raise
    finally:
        if core:core.close()
        win32gui.DestroyWindow(hwnd); win32gui.UnregisterClass(atom,instance)
        (report_dir/"overlay_test.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=True))


if __name__=="__main__":main()
