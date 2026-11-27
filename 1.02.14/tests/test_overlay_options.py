# SPDX-License-Identifier: MIT
import ctypes
import os
import time
import pytest
from PIL import Image, ImageGrab
from test_native_overlay import core,render,region
from test_native_fixed_layout import fixed
from test_native_aero import source_window
from nkc_galgame_translator.native import NativeCore
from nkc_galgame_translator.tuning import validate_tuning


def test_invalid_font_ranges_rejected():
    with pytest.raises(ValueError):validate_tuning({'overlay_font_min':60,'overlay_font_max':20})


@pytest.mark.parametrize('options',[
    {'overlay_font_size':True}, {'overlay_font_min':7}, {'overlay_font_max':513},
    {'overlay_font_min':40,'overlay_font_max':20}, {'capture_translations':1}, {'auto_font_size':'yes'}])
def test_native_invalid_options_leave_context_usable(core,options):
    with pytest.raises(ValueError):core.set_overlay_options(**options)
    assert render(core,[fixed()])[0]['fits']


def test_manual_size_and_overflow_preserve_original(core):
    core.set_overlay_options(auto_font_size=False,overlay_font_size=22)
    short=render(core,[fixed()])[0]
    assert short['font_px']==22 and short['fits']
    long=render(core,[fixed('\u8fd9\u662f\u65e0\u6cd5\u653e\u5165\u8fd9\u4e2a\u6846\u7684\u5f88\u957f\u8bd1\u6587'*15)])[0]
    assert long['font_px']==22 and not long['fits']
    from overlay_smoke import window_mask
    assert window_mask(long['hwnd'])[0].getbbox() is None


def test_auto_range_streaming_and_range_change(core):
    core.set_overlay_options(overlay_font_min=14,overlay_font_max=20)
    previous=21
    for length in (2,7,12,18):
        result=render(core,[fixed('\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c\uff0c\u8bf7\u6536\u96c6\u9053\u5177\u7ee7\u7eed\u63a2\u9669\u3002'[:length],final=False)])[0]
        assert 14<=result['font_px']<=20
        assert result['font_px']<=previous
        previous=result['font_px']
    core.set_overlay_options(overlay_font_min=25,overlay_font_max=28)
    result=render(core,[fixed('\u4f60\u597d',_revision=2)])[0]
    assert 25<=result['font_px']<=28 and result['fits']


def test_game_only_capture_never_reads_screenshot_visible_overlay(core):
    x,y=180,180
    source=Image.new('RGB',(280,110),(20,40,60))
    with source_window(source,x,y) as hwnd, NativeCore() as decoration:
        core.set_target(hwnd,os.getpid())
        core.set_overlay_options(capture_translations=True)
        first=core.capture_bgra(x,y,280,110)
        assert Image.frombytes('RGB',(280,110),first['bgra'],'raw','BGRX').tobytes()==source.tobytes()
        item=render(decoration,[region(x=x,y=y,w=280,h=110,text='Screenshot translation',bg=[180,60,30])])[0]
        user=ctypes.WinDLL('user32');user.SetWindowDisplayAffinity.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        assert user.SetWindowDisplayAffinity(item['hwnd'],0)
        ctypes.windll.dwmapi.DwmFlush()
        assert ImageGrab.grab((x,y,x+280,y+110)).convert('RGB').getpixel((0,0))==(180,60,30)
        for _ in range(5):
            time.sleep(.025)
            assert not core.capture_bgra(x,y,280,110)['changed']
        # Toggling back to desktop OCR only happens after restoring exclusion.
        assert user.SetWindowDisplayAffinity(item['hwnd'],0x11)
        ctypes.windll.dwmapi.DwmFlush()
        core.set_overlay_options(capture_translations=False)
        assert not core.capture_bgra(x,y,280,110)['changed']


def test_overlay_follows_client_drag_without_new_ocr_and_rejects_stale_resize(core):
    from ctypes import wintypes as W
    from test_native_aero import image_with_ink,fixed_item
    user=ctypes.WinDLL('user32')
    user.SetForegroundWindow.argtypes=[W.HWND]
    user.SetWindowPos.argtypes=[W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT]
    user.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
    user.IsWindowVisible.argtypes=[W.HWND]
    def position(hwnd):
        rect=W.RECT();assert user.GetWindowRect(hwnd,ctypes.byref(rect))
        return rect.left,rect.top
    with source_window(image_with_ink((245,245,245)),180,180,activatable=True) as hwnd:
        # Owned test window only; no keystrokes or external application actions.
        if not user.SetForegroundWindow(hwnd):
            pytest.skip('Windows foreground lock is held by another active app; run this desktop check separately')
        core.set_target(hwnd,os.getpid())
        core.capture_bgra(180,180,280,110)
        item={**fixed_item(180,180,'\u4f60\u597d'),'_capture_origin':(180,180)}
        original=render(core,[item])[0]
        assert original['fits'] and user.IsWindowVisible(original['hwnd'])
        before=position(original['hwnd'])
        assert user.SetWindowPos(hwnd,None,230,210,0,0,0x15) # NOZORDER|NOSIZE|NOACTIVATE
        deadline=time.monotonic()+.4
        while position(original['hwnd'])!=(before[0]+50,before[1]+30) and time.monotonic()<deadline:time.sleep(.005)
        assert position(original['hwnd'])==(before[0]+50,before[1]+30)
        # Late streamed chunks still carry old absolute OCR coordinates.
        late=render(core,[{**item,'text':'\u4f60\u597d\u4e16\u754c'}])[0]
        assert late['bounds'][:2]==[before[0]+50,before[1]+30]
        assert late['font_px']<=original['font_px'] and late['fits']
        assert user.SetWindowPos(hwnd,None,0,0,300,120,0x16) # NOMOVE|NOZORDER|NOACTIVATE
        deadline=time.monotonic()+.4
        while user.IsWindowVisible(late['hwnd']) and time.monotonic()<deadline:time.sleep(.005)
        assert not user.IsWindowVisible(late['hwnd'])
