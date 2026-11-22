# SPDX-License-Identifier: MIT
"""Real capture -> native reconstruction -> opaque GDI rendering, no API/input."""
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageChops
import pytest

from test_native_overlay import core, render, region

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from overlay_smoke import print_window, window_mask


class InfoHeader(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),
              ('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),
              ('size_image',wintypes.DWORD),('xppm',wintypes.LONG),('yppm',wintypes.LONG),
              ('used',wintypes.DWORD),('important',wintypes.DWORD)]


@contextmanager
def source_window(image, x, y, *, activatable=False):
    """Owned, temporary no-activate STATIC bitmap window; never sends input."""
    user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32')
    user.CreateWindowExW.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,
        ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p]
    user.CreateWindowExW.restype=wintypes.HWND
    user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.DestroyWindow.argtypes=[wintypes.HWND]
    user.UpdateWindow.argtypes=[wintypes.HWND]
    user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    gdi.CreateDIBSection.argtypes=[wintypes.HDC,ctypes.POINTER(InfoHeader),wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),wintypes.HANDLE,wintypes.DWORD]
    gdi.CreateDIBSection.restype=wintypes.HBITMAP
    gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ]
    header=InfoHeader();header.size=ctypes.sizeof(header);header.width=image.width
    header.height=-image.height;header.planes=1;header.bits=32
    bits=ctypes.c_void_p();bitmap=gdi.CreateDIBSection(None,ctypes.byref(header),0,ctypes.byref(bits),None,0)
    assert bitmap
    data=image.convert('RGBA').tobytes('raw','BGRA');ctypes.memmove(bits,data,len(data))
    hwnd=user.CreateWindowExW(0x8 if activatable else 0x08000088,'STATIC','Owned background test',0x8000000e,
        x,y,image.width,image.height,None,None,None,None)
    assert hwnd
    try:
        user.SendMessageW(hwnd,0x0172,0,bitmap)  # STM_SETIMAGE / IMAGE_BITMAP
        user.ShowWindow(hwnd,5 if activatable else 4);user.UpdateWindow(hwnd)
        ctypes.windll.dwmapi.DwmFlush()
        yield hwnd
    finally:
        user.DestroyWindow(hwnd);gdi.DeleteObject(bitmap)


def scene_with_ink(color=(245,245,245),same_color_curve=False):
    clean=Image.new('RGB',(280,110))
    clean.putdata([(20+x//2,25+y//2,40+x//4) for y in range(110) for x in range(280)])
    draw=ImageDraw.Draw(clean)
    draw.ellipse((120,2,260,100),outline=color if same_color_curve else (60,100,155),width=8)
    image=clean.copy()
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',23)
    ImageDraw.Draw(image).text((33,29),'Welcome, player',font=font,fill=color)
    return clean,image


def image_with_ink(color):
    return scene_with_ink(color)[1]


def fixed_item(x,y,text='.'):
    return region(x=x+30,y=y+30,w=200,h=42,text=text,final=True,
        font_size=0,_fixed_layout=True,
        _source_rows=[dict(x=0,y=0,w=200,h=42,ink_bounds=[3,3,194,36],font_size=0)])


def test_aero_repairs_only_glyphs_and_preserves_curve_through_ink_bounds(core):
    x,y=region()['x']+50,region()['y']+50
    clean,source=scene_with_ink()
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        # A final whitespace row exposes the real repaired bottom layer without
        # translated glyphs obscuring the background-preservation comparison.
        result=render(core,[fixed_item(x,y,' ')])[0]
        assert result['aero'] and result['background_opaque'] and result['fits']
        assert not result['background_suppressed']
        assert 0<result['background_mask_pixels']==result['background_repaired_pixels']<200*42*.5
        actual=print_window(result['hwnd'],diagnostic_overlay=True).convert('RGB')
        source=source.crop((30,30,230,72));clean=clean.crop((30,30,230,72))
        removed=0;ring=0
        for yy in range(42):
            for xx in range(200):
                before=source.getpixel((xx,yy));base=clean.getpixel((xx,yy));after=actual.getpixel((xx,yy))
                if before==base:
                    assert after==before, (xx,yy,before,after)
                    if before==(60,100,155):ring+=1
                elif min(before)>=225:
                    assert min(after)<220, (xx,yy,before,after)
                    removed+=1
        assert removed>250 and ring>100


def test_rough_dialogue_row_erases_mixed_ink_and_keeps_background(core):
    from nkc_galgame_translator.aoi_dialogue import repair_ocr_rows
    clean=Image.new('RGB',(280,100),(53,83,104))
    for yy in range(0,100,7):
        ImageDraw.Draw(clean).line((0,yy,279,yy),fill=(62,90,119))
    image=clean.copy()
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',23)
    draw=ImageDraw.Draw(image)
    for xx,label,ink in ((30,'White',(246,246,246)),(100,'Kitchen',(127,255,212))):
        draw.text((xx,28),label,fill=ink,font=font,stroke_width=1,stroke_fill=(35,36,38))
    bounds=ImageChops.difference(image,clean).getbbox()
    l,t,r,b=bounds
    row=dict(x=l-4,y=t-4,w=r-l+8,h=b-t+8,text='Dialogue',fg=[246]*3,bg=[53,83,104])
    fixed,=repair_ocr_rows(image,[row])
    assert fixed['_subtitle_read']
    x,y=region()['x']+50,region()['y']+50
    with source_window(image,x,y):
        core.capture_bgra(x,y,*image.size)
        item={**region(),**fixed,'text':' ','final':True,'_fixed_layout':True,
              'x':x+fixed['x'],'y':y+fixed['y']}
        item['_source_ink']=[x+fixed['_source_ink'][0],y+fixed['_source_ink'][1],*fixed['_source_ink'][2:]]
        state=render(core,[item])[0]
        assert state['aero'] and not state['background_suppressed']
        output=print_window(state['hwnd'],diagnostic_overlay=True).convert('RGB')
        for xx in range(fixed['w']):
            for yy in range(fixed['h']):
                original=image.getpixel((xx+fixed['x'],yy+fixed['y']))
                if original in ((246,246,246),(127,255,212)):
                    assert max(output.getpixel((xx,yy)))<180


def test_mint_subtitle_is_removed_even_if_ocr_foreground_was_white(core):
    x,y=region()['x']+50,region()['y']+50
    mint=(127,255,212)
    clean,source=scene_with_ink(mint)
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        item={**fixed_item(x,y,' '),'_subtitle_read':True,'fg':[245,245,245]}
        result=render(core,[item])[0]
        assert result['aero'] and not result['background_suppressed']
        reconstructed=print_window(result['hwnd'],diagnostic_overlay=True).convert('RGB')
        old=source.crop((30,30,230,72))
        covered=[(xx,yy) for yy in range(42) for xx in range(200) if old.getpixel((xx,yy))==mint]
        assert len(covered)>250
        assert all(reconstructed.getpixel(point)!=mint for point in covered)
        assert reconstructed.getpixel((8,35))==clean.getpixel((38,65))


def test_streaming_row_covers_entire_faint_source_ink_on_flat_surface(core):
    bg=(213,230,249)
    fg=(42,33,219)
    x,y=region()['x']+50,region()['y']+50
    with Image.new('RGB',(280,110),bg) as image:
        faded=tuple(round(a*.84+b*.16) for a,b in zip(bg,fg))
        draw=ImageDraw.Draw(image)
        for start in (45,95,150,205):
            draw.rectangle((start,40,start+8,51),fill=faded)
        with source_window(image,x,y):
            core.capture_bgra(x,y,280,110)
            item=fixed_item(x,y,'X')
            item.update(final=False,bg=bg,fg=fg)
            result=render(core,[item])[0]
            assert result['background_reason']=='flat_glyph_repaired'
            actual=print_window(result['hwnd'],diagnostic_overlay=True).convert('RGB')
            assert actual.getpixel((178,16))==bg  # Original ink beyond the current token.
            assert result['background_repaired_pixels']==4*9*12


def test_previous_background_remains_while_a_new_scene_is_untranslated(core):
    x,y=region()['x']+50,region()['y']+50
    _,old=scene_with_ink()
    with source_window(old,x,y):
        core.capture_bgra(x,y,280,110)
        item=fixed_item(x,y,'Ready')
        first=render(core,[item])[0]
        assert first['aero'] and not first['background_suppressed']
    with Image.new('RGB',(280,110),'#e7b5c9') as new, source_window(new,x,y):
        core.capture_bgra(x,y,280,110)
        held=render(core,[{**item,'_hold_previous':True}])[0]
        assert held['hwnd']==first['hwnd']
        assert held['aero'] and not held['background_suppressed']
        assert held['background_mask_pixels']==first['background_mask_pixels']


def test_uncertain_foreground_retains_original_pixels_and_suppresses_translation(core):
    x,y=region()['x']+50,region()['y']+50
    source=image_with_ink((255,0,255))
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        result=render(core,[fixed_item(x,y,'\u4e0d\u80fd\u53e0\u5728\u539f\u5b57\u4e0a')])[0]
        assert not result['aero'] and result['background_suppressed']
        assert result['background_reason']=='foreground_missing'
        assert not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(result['hwnd']))


def test_foreground_colored_curve_crossing_ink_boundary_is_not_erased(core):
    x,y=region()['x']+50,region()['y']+50
    _,source=scene_with_ink(same_color_curve=True)
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        result=render(core,[fixed_item(x,y,'\u4e0d\u8986\u76d6\u4e0d\u786e\u5b9a\u56fe\u5f62')])[0]
        assert not result['aero'] and result['background_suppressed']
        assert result['background_reason']=='foreground_leaks_boundary'
        assert not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(result['hwnd']))


def test_foreground_change_invalidates_cached_mask(core):
    x,y=region()['x']+50,region()['y']+50
    with source_window(image_with_ink((245,245,245)),x,y):
        core.capture_bgra(x,y,280,110)
        first=render(core,[fixed_item(x,y)])[0]
        assert first['aero']
        wrong=render(core,[{**fixed_item(x,y), 'fg':[255,0,255]}])[0]
        assert wrong['background_suppressed'] and wrong['background_reason']=='foreground_missing'
        assert wrong['background_builds']==first['background_builds']+1


def test_aero_reuses_frame_patch_for_streaming_and_clears_on_reset(core):
    x,y=region()['x']+50,region()['y']+50
    with source_window(image_with_ink((255,255,255)),x,y):
        core.capture_bgra(x,y,280,110)
        item=fixed_item(x,y,'\u4e2d');item['final']=False
        first=render(core,[item])[0]
        second=render(core,[{**item,'text':'\u4e2d\u6587'}])[0]
        assert first['aero'] and second['aero']
        assert first['background_frame']==second['background_frame']
        assert first['background_builds']==second['background_builds']==1
        core.reset()
        reset=render(core,[{**item,'text':'\u4e2d\u6587\u7ffb\u8bd1'}])[0]
        assert not reset['aero'] and reset['background_opaque']


def test_aero_does_not_sample_unrelated_screen_rectangles(core):
    x,y=region()['x']+50,region()['y']+50
    with source_window(image_with_ink((255,255,255)),x,y):
        core.capture_bgra(x,y,280,110)
        result=render(core,[fixed_item(x+300,y)])[0]
        assert not result['aero'] and result['background_opaque']
        assert result['background_suppressed'] and result['background_reason']=='source_unavailable'
        assert not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(result['hwnd']))


def test_measured_red_foreground_flows_into_native_glyph_repair(core):
    from nkc_galgame_translator.ocr_regions import RegionRefiner
    x,y=region()['x']+50,region()['y']+50
    source=Image.new('RGB',(280,110),(10,10,10))
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',23)
    ImageDraw.Draw(source).text((33,29),'Welcome, player',font=font,fill=(240,35,45))
    original=dict(text='Welcome, player',x=30,y=30,w=200,h=42,bg=[10,10,10],fg=[245,245,245],
                  _source_ink=[33,33,194,36])
    refiner=RegionRefiner(2)
    try:measured=refiner.refine(source,[original])[0]
    finally:refiner.close()
    assert measured['fg']==[240,35,45] and original['fg']==[245,245,245]
    ix,iy,iw,ih=measured['_source_ink']
    item=fixed_item(x,y,' ')
    item['fg']=measured['fg']
    item['_source_rows'][0]['ink_bounds']=[ix-30,iy-30,iw,ih]
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        result=render(core,[item])[0]
        assert result['aero'] and not result['background_suppressed']
        actual=print_window(result['hwnd'],diagnostic_overlay=True).convert('RGB')
        # AA below the conservative mask threshold can differ by <18 levels;
        # no visible red stroke survives and the solid background is retained.
        assert max(channel[1] for channel in actual.getextrema())<=28


def test_dense_foreground_is_not_erased_as_a_large_graphic(core):
    x,y=region()['x']+50,region()['y']+50
    source=Image.new('RGB',(280,110),(20,30,40))
    ImageDraw.Draw(source).rectangle((33,33,226,68),fill=(245,245,245))
    with source_window(source,x,y):
        core.capture_bgra(x,y,280,110)
        result=render(core,[fixed_item(x,y,'\u4e0d\u64e6\u56fe\u5f62')])[0]
        assert result['background_suppressed'] and result['background_reason']=='dense_foreground'
        assert not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(result['hwnd']))

def test_mandatory_coverage_does_not_repaint_rejected_source_patch(core):
    from PIL import ImageChops
    x,y=region()['x']+50,region()['y']+50
    paper=(253,248,253)
    with Image.new('RGB',(280,110),paper) as source:
        ImageDraw.Draw(source).rectangle((133,40,215,53),fill=(77,33,203))
        with source_window(source,x,y):
            core.capture_bgra(x,y,280,110)
            for text in ('','\u4e2d'):
                item=fixed_item(x,y,text)
                item.update(bg=paper,fg=(30,30,30),_cover_source=True,final=False)
                result=render(core,[item])[0]
                assert result['background_suppressed'] and result['background_reason']=='foreground_missing'
                assert not ctypes.windll.user32.IsWindowVisible(wintypes.HWND(result['hwnd']))




def test_textured_background_repairs_both_ink_and_dark_outline(core):
    from PIL import ImageChops
    x,y=region()['x']+50,region()['y']+50
    with Image.new('RGB',(300,110)) as clean:
        clean.putdata([(64+xx//6,100+yy//5,142+xx//12) for yy in range(110) for xx in range(300)])
        with clean.copy() as source:
            font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',26)
            pos=(38,37)
            ImageDraw.Draw(source).text(pos,'Office opens today.',font=font,fill=(246,246,246),
                                        stroke_width=2,stroke_fill=(20,20,20))
            with ImageChops.difference(clean,source) as delta:
                l,t,r,b=delta.getbbox()
            item={**fixed_item(x,y,' '),'w':260,'h':55,'fg':(246,246,246),'bg':(85,110,152)}
            item['_source_rows']=[dict(x=0,y=0,w=260,h=55,ink_bounds=[l-30,t-30,r-l,b-t])]
            with source_window(source,x,y):
                core.capture_bgra(x,y,*source.size)
                state=render(core,[item])[0]
                assert state['background_reason']=='outlined_glyph_repaired'
                with print_window(state['hwnd'],diagnostic_overlay=True).convert('RGB') as actual, source.crop((30,30,290,85)) as original, clean.crop((30,30,290,85)) as backdrop:
                    dark=leftover=0
                    for source_pixel,painted,base in zip(original.get_flattened_data(),actual.get_flattened_data(),backdrop.get_flattened_data()):
                        if source_pixel==base:assert painted==base
                        if source_pixel==(20,20,20):
                            dark+=1
                            leftover+=max(abs(a-b) for a,b in zip(painted,base))>32
                    assert dark>100 and leftover<=dark*.08,(dark,leftover)
