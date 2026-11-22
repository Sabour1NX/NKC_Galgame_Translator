# SPDX-License-Identifier: MIT
"""Own-window button routing fixture. Input is exclusively supplied by the tester.

No SendInput, cursor movement, foreground activation, hooks, game access, or API.
The caller clicks actual screen coordinates using the authorized computer tool.
"""
from pathlib import Path
import json
import os
import sys
import time

import win32api
import win32con
import win32gui
import win32process

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nkc_galgame_translator.native import NativeCore
from nkc_galgame_translator.windows import enable_dpi
from overlay_smoke import overlays, window_mask

def main():
    enable_dpi()
    reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    path=reports/'click-through-fixture.json'
    stop_path=reports/'click-through-fixture.stop'
    began=time.time();foreground_before=win32gui.GetForegroundWindow()
    events=[];counts={101:0,102:0,103:0};buttons={};labels={};closed=False
    report={'status':'starting','pid':os.getpid(),'kind':'own Win32 BUTTON controls under real native overlays',
            'input_source':'external tester; this script never injects input',
            'game_accessed':False,'api_used':False,'send_input_calls':0,'foreground_before':foreground_before,
            'events':events,'counts':counts,'diagnostic_unbound_overlays':True}
    def save():
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def proc(hwnd,message,wp,lp):
        nonlocal closed
        if message==win32con.WM_MOUSEACTIVATE:return 3
        if message==win32con.WM_COMMAND:
            identity=wp&0xffff;notification=(wp>>16)&0xffff
            if identity in buttons and notification==win32con.BN_CLICKED and lp==buttons[identity]:
                if identity==104:
                    win32gui.PostMessage(hwnd,win32con.WM_CLOSE,0,0);return 0
                counts[identity]+=1
                fg=win32gui.GetForegroundWindow()
                events.append({'id':identity,'kind':'BN_CLICKED','count':counts[identity],
                               'button_hwnd':lp,'foreground':fg,'foreground_unchanged':fg==foreground_before,
                               'elapsed_seconds':round(time.time()-began,3)})
                win32gui.SetWindowText(labels[identity],f'\u5b9e\u9645\u70b9\u51fb\u8ba1\u6570\uff1a{counts[identity]}')
                report['status']='receiving_clicks';save();return 0
        if message==win32con.WM_DESTROY:
            closed=True;win32gui.PostQuitMessage(0);return 0
        return win32gui.DefWindowProc(hwnd,message,wp,lp)
    instance=win32api.GetModuleHandle(None)
    cls=win32gui.WNDCLASS();cls.hInstance=instance;cls.lpszClassName='ErSeDieOwnedClickFixture';cls.lpfnWndProc=proc
    cls.hbrBackground=win32gui.GetStockObject(win32con.WHITE_BRUSH)
    atom=win32gui.RegisterClass(cls)
    width,height=760,300
    vx,vy=win32api.GetSystemMetrics(76),win32api.GetSystemMetrics(77)
    vw,vh=win32api.GetSystemMetrics(78),win32api.GetSystemMetrics(79)
    x=vx+max(0,(vw-width)//2);y=vy+max(0,(vh-height)//2)
    hwnd=win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST|0x08000000|win32con.WS_EX_TOOLWINDOW,
        atom,'ErSeDie Click-through Fixture | \u81ea\u5efa\u6309\u94ae\u7a7f\u900f\u6d4b\u8bd5',win32con.WS_POPUP|win32con.WS_BORDER,
        x,y,width,height,0,0,instance,None)
    logfont=win32gui.LOGFONT();logfont.lfFaceName='Microsoft YaHei UI';logfont.lfHeight=-18
    font=win32gui.CreateFontIndirect(logfont)
    def child(kind,title,left,top,w,h,identity):
        handle=win32gui.CreateWindowEx(0,kind,title,win32con.WS_CHILD|win32con.WS_VISIBLE,
                                      left,top,w,h,hwnd,identity,instance,None)
        win32gui.SendMessage(handle,win32con.WM_SETFONT,font,1)
        return handle
    core=None
    try:
        child('STATIC','\u81ea\u5efa\u7a97\u53e3\uff1a\u6d4b\u8bd5\u9f20\u6807\u70b9\u51fb\u662f\u5426\u7a7f\u8fc7\u5b9e\u9645\u7ffb\u8bd1\u8986\u76d6\u5c42',24,18,710,28,201)
        child('STATIC','\u8bf7\u5206\u522b\u70b9\u51fb\uff1a\u65e0\u906e\u6321\u57fa\u7ebf / \u4e2d\u95f4“\u6d41\u5f0f”\u6587\u5b57 / \u53f3\u4fa7\u5b8c\u6574\u8bd1\u6587',24,48,710,28,202)
        for identity,left,label in [(101,24,'\u65e0\u906e\u6321\u57fa\u7ebf\u6309\u94ae'),(102,270,'\u6d41\u5f0f\u8986\u76d6\u4e0b\u7684\u539f\u6309\u94ae'),(103,516,'\u5b8c\u6574\u8986\u76d6\u4e0b\u7684\u539f\u6309\u94ae')]:
            buttons[identity]=child('BUTTON',label,left,94,220,76,identity)
            labels[identity]=child('STATIC','\u5b9e\u9645\u70b9\u51fb\u8ba1\u6570\uff1a0',left,187,220,28,identity+100)
        buttons[104]=child('BUTTON','\u7ed3\u675f\u6d4b\u8bd5',566,242,170,36,104)
        child('STATIC','\u4e0d\u8c03\u7528 API\u3001\u4e0d\u64cd\u4f5c\u6e38\u620f\uff1b\u70b9\u51fb\u8ba1\u6570\u6765\u81ea\u539f\u751f BN_CLICKED\u3002',24,245,530,28,203)
        win32gui.ShowWindow(hwnd,win32con.SW_SHOWNOACTIVATE);win32gui.UpdateWindow(hwnd)
        win32gui.PumpWaitingMessages()
        rects={identity:list(win32gui.GetWindowRect(handle)) for identity,handle in buttons.items()}
        origin=rects[102];full=rects[103]
        core=NativeCore()
        regions=[{'x':origin[0],'y':origin[1],'w':220,'h':76,'text':'\u6d41\u5f0f','font_size':26,'final':False,
                  'bg':[247,232,224],'fg':[182,51,45]},
                 {'x':full[0],'y':full[1],'w':220,'h':76,'text':'\u5b8c\u6574\u8bd1\u6587\u8986\u76d6\n\u6309\u94ae\u4ecd\u5e94\u6536\u5230\u70b9\u51fb','font_size':18,'final':True,
                  'bg':[247,232,224],'fg':[182,51,45]}]
        core.show_overlay(regions)
        until=time.monotonic()+2
        while len(overlays())<2 and time.monotonic()<until:
            win32gui.PumpWaitingMessages();time.sleep(.01)
        native=[]
        for overlay in overlays():
            mask,rectangles=window_mask(overlay)
            native.append({'hwnd':overlay,'rectangle':list(win32gui.GetWindowRect(overlay)),
                           'mask_rectangles':rectangles,'masked_area':mask.histogram()[255],
                           'styles':win32gui.GetWindowLong(overlay,win32con.GWL_EXSTYLE),
                           'thread_pid':win32process.GetWindowThreadProcessId(overlay)})
        report.update(status='ready',hwnd=hwnd,title=win32gui.GetWindowText(hwnd),
                      fixture_rect=list(win32gui.GetWindowRect(hwnd)),button_rectangles=rects,
                      recommended_screen_clicks={'baseline':[rects[101][0]+110,rects[101][1]+38],
                          'partial_covered_pixel':[origin[0]+20,origin[1]+14],
                          'full_covered_pixel':[full[0]+110,full[1]+38]},
                      native_overlays=native,foreground_after_show=win32gui.GetForegroundWindow())
        save();print(json.dumps({'status':'ready','pid':os.getpid(),'hwnd':hwnd,'report':str(path)},ensure_ascii=False),flush=True)
        deadline=time.monotonic()+600
        while not closed and time.monotonic()<deadline:
            win32gui.PumpWaitingMessages()
            if stop_path.exists() and stop_path.stat().st_mtime>=began:break
            time.sleep(.01)
    finally:
        if core:core.close()
        if win32gui.IsWindow(hwnd):win32gui.DestroyWindow(hwnd)
        win32gui.DeleteObject(font);win32gui.UnregisterClass(atom,instance)
        report['finished']=True
        report['foreground_after_cleanup']=win32gui.GetForegroundWindow()
        report['all_three_buttons_received_clicks']=all(counts[k]>0 for k in (101,102,103))
        save()

if __name__=='__main__':main()
