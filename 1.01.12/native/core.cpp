// SPDX-License-Identifier: MIT
// Windows x64 capture, OCR and replacement-text compositor.
#define NKC_GALGAME_TRANSLATOR_EXPORTS
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <roapi.h>
#include <dwmapi.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Globalization.h>
#include <winrt/Windows.Graphics.Imaging.h>
#include <winrt/Windows.Media.Ocr.h>
#include <winrt/Windows.Security.Cryptography.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <climits>
#include <cmath>
#include <memory>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <vector>
#include "core.h"

using namespace winrt;
using namespace winrt::Windows::Graphics::Imaging;
using namespace winrt::Windows::Media::Ocr;
using namespace winrt::Windows::Globalization;
using Clock = std::chrono::steady_clock;
static HINSTANCE moduleHandle;
static thread_local std::string resultText, errorText;
static constexpr UINT UPDATE_OVERLAY = WM_APP + 1;
static constexpr UINT STOP_OVERLAY = WM_APP + 2;

static std::string jsonString(std::string const& s) {
    std::string out = "\"";
    const char* hex = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += c;
    }
    return out + '"';
}

struct Apartment {
    HRESULT hr = RoInitialize(RO_INIT_MULTITHREADED);
    ~Apartment() { if (SUCCEEDED(hr)) RoUninitialize(); }
    void check() { if (FAILED(hr)) throw hresult_error(hr, L"OCR must run on a dedicated MTA worker thread."); }
};
struct CapturePending:std::runtime_error { using std::runtime_error::runtime_error; };
#include "window_capture.h"
struct OverlayOptions {
    bool automatic=true, screenshots=false;
    int size=24, minimum=8, maximum=512;
};
struct OcrRuntime {
    Apartment apartment;
    std::map<std::wstring,OcrEngine> engines;
    OcrRuntime() { apartment.check(); }
};
static OcrRuntime& ocrRuntime() { thread_local OcrRuntime runtime; return runtime; }

struct Region {
    int x = 0, y = 0, w = 0, h = 0, size = 0;
    COLORREF bg = RGB(25,25,25), fg = RGB(255,255,255);
    std::wstring text;
    bool final = true;
    uint64_t trackId = 0, revision = 0;
    std::vector<GLSourceRow> sourceRows;
    RECT anchor{};
    bool anchored=false;
    std::wstring fontFamily;
    bool pixelFont=false, centerLabel=false, flashHeld=false, holdBackground=false, coverSource=false,subtitle=false,menuButton=false,toolbarButton=false;
    bool standaloneSubtitle=false;
};
#include "aero_background.h"
struct RenderLine {
    std::wstring text; int y, width, height; size_t start, length;
    int x=2, inkHeight=0, inkTop=0;
    RECT clip{};
    std::vector<int> advances;
    bool drawable=true;
};
struct OverlayWindow {
    HWND hwnd = nullptr;
    Region region;
    HFONT font = nullptr;
    int fontPixels = 0;
    int independentFontPixels = 0;
    int fontPeers = 1;
    std::wstring fontFace;
    bool fits = false;
    std::vector<RenderLine> lines;
    HDC paintDC = nullptr;
    HBITMAP paintBitmap = nullptr;
    HGDIOBJ originalPaintBitmap = nullptr;
    uint8_t* paintPixels = nullptr;
    HRGN pendingMask = nullptr;
    bool maskReady = false, everShown = false;
    int paintWidth = 0, paintHeight = 0;
    uint64_t paintAllocations = 0, paintCommits = 0;
    uint64_t paintFailures = 0;
    uint64_t firstShowCommits = 0;
    bool bufferedPaint = false;
    std::vector<uint8_t> backgroundPixels;
    uint64_t backgroundSequence = 0, backgroundBuilds = 0;
    size_t backgroundMasked=0,backgroundRepaired=0;
    bool backgroundSuppressed=false;
    std::string backgroundReason="no_frame";
    bool ensurePaintBuffer(HDC compatible, int width, int height) {
        // Bound a single diagnostic region's buffer to 64 MiB. Production
        // rectangles are additionally clipped to the selected game window.
        if (width<=0 || height<=0 || size_t(width)*size_t(height)>4096u*4096u) return false;
        if (paintBitmap && width==paintWidth && height==paintHeight) return true;
        if (!paintDC) paintDC=CreateCompatibleDC(compatible);
        if (!paintDC) return false;
        BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth=width;info.bmiHeader.biHeight=-height;
        info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
        void* replacementPixels=nullptr;
        HBITMAP replacement=CreateDIBSection(compatible,&info,DIB_RGB_COLORS,&replacementPixels,nullptr,0);
        if (!replacement) return false;
        HGDIOBJ previous=SelectObject(paintDC,replacement);
        if (!previous || previous==HGDI_ERROR) {
            DeleteObject(replacement); return false;
        }
        // Allocate/select before releasing the old bitmap: a failed resize
        // leaves the previous buffer valid and does not leak a selected object.
        if (!originalPaintBitmap) originalPaintBitmap=previous;
        if (paintBitmap) DeleteObject(paintBitmap);
        paintBitmap=replacement;paintPixels=static_cast<uint8_t*>(replacementPixels);
        paintWidth=width; paintHeight=height;
        ++paintAllocations; return true;
    }
    void stageMask(HRGN mask, bool entire=false) {
        // Layout must not expose a larger window region before its pixels are
        // ready. The mask is transferred to the HWND only after frame commit.
        if(pendingMask)DeleteObject(pendingMask);
        pendingMask=mask;
        maskReady=mask!=nullptr || entire;
    }
    ~OverlayWindow() {
        if (hwnd) DestroyWindow(hwnd);
        if (font) DeleteObject(font);
        if (paintDC && originalPaintBitmap) SelectObject(paintDC,originalPaintBitmap);
        if (paintBitmap) DeleteObject(paintBitmap);
        if (paintDC) DeleteDC(paintDC);
        if (pendingMask) DeleteObject(pendingMask);
    }
};
struct MissingFontFit {
    uint64_t revision;
    std::wstring text;
    int fontPixels;
    int independentFontPixels;
    Clock::time_point missingSince;
};
static constexpr size_t FONT_HISTORY_LIMIT=64;
static constexpr auto FONT_HISTORY_TTL=std::chrono::seconds(3);
static bool highSurrogate(wchar_t c) { return c>=0xd800 && c<=0xdbff; }
static bool lowSurrogate(wchar_t c) { return c>=0xdc00 && c<=0xdfff; }
static bool latinWord(wchar_t c) {
    // CJK glyphs have natural break opportunities even when a preceding
    // translated label or proper name contains a space. Do not drag the
    // entire Chinese continuation back to that unrelated whitespace.
    return (c>=L'A' && c<=L'Z') || (c>=L'a' && c<=L'z') ||
        (c>=L'0' && c<=L'9') || c==L'_' ||
        (c>=0xc0 && c<=0x2af && c!=0xd7 && c!=0xf7);
}
static bool openingPunctuation(wchar_t c) {
    return std::wstring_view(L"([{（［｛〈《「『【〔〖〘〚“‘").find(c)!=std::wstring_view::npos;
}
static bool closingPunctuation(wchar_t c) {
    return std::wstring_view(L")]}）］｝〉》」』】〕〗〙〛、。，．？！：；％!?;:,%’”").find(c)!=std::wstring_view::npos;
}
static int wrapBoundary(std::wstring const& text, size_t pos, int count, int measured) {
    int fit=std::max(1,measured);
    // GDI reports UTF-16 units. Even a rectangle narrower than one glyph must
    // retain a non-BMP scalar intact, then report fits=false if it cannot fit.
    if (fit<count && highSurrogate(text[pos+fit-1]) && lowSurrogate(text[pos+fit])) {
        if (fit==1) ++fit; else --fit;
    }
    if (fit>=count) return count;
    const int fallback=fit;
    while (fit>0) {
        int next=fit;
        if (latinWord(text[pos+fit-1]) && latinWord(text[pos+fit])) {
            while (next>0 && latinWord(text[pos+next-1])) --next;
            // An overlong word has no earlier legal break: split it only at
            // the measured boundary, never create an empty line or loop.
            if (next==0) return fallback;
        } else if (openingPunctuation(text[pos+fit-1]) || closingPunctuation(text[pos+fit])) {
            --next;
            if (next>0 && lowSurrogate(text[pos+next]) && highSurrogate(text[pos+next-1])) --next;
        } else return fit;
        fit=next;
    }
    // Very narrow punctuation-only runs still need bounded forward progress.
    return fallback;
}
static std::vector<RenderLine> wrapLines(HDC dc, Region const& region) {
    TEXTMETRICW metrics{}; GetTextMetricsW(dc,&metrics);
    int lineHeight=metrics.tmHeight+metrics.tmExternalLeading;
    int available=std::max(1,region.w-4), y=1;
    std::vector<RenderLine> lines;
    std::wstring text=region.text;
    text.erase(std::remove(text.begin(),text.end(),L'\r'),text.end());
    size_t pos=0;
    while (pos<text.size()) {
        size_t newline=text.find(L'\n',pos);
        if (newline==std::wstring::npos) newline=text.size();
        if (newline==pos) { y+=lineHeight; ++pos; continue; }
        int count=int(newline-pos), fit=0; SIZE extent{};
        GetTextExtentExPointW(dc,text.data()+pos,count,available,&fit,nullptr,&extent);
        fit=wrapBoundary(text,pos,count,fit);
        auto current=text.substr(pos,size_t(fit));
        while (!current.empty() && (current.back()==L' ' || current.back()==L'\t')) current.pop_back();
        GetTextExtentPoint32W(dc,current.data(),int(current.size()),&extent);
        if (!current.empty()) {
            auto length=current.size();
            lines.push_back({std::move(current),y,extent.cx,lineHeight,pos,length});
        }
        y+=lineHeight; pos+=size_t(fit);
        while (pos<newline && (text[pos]==L' ' || text[pos]==L'\t')) ++pos;
        if (pos==newline && pos<text.size()) ++pos;
    }
    return lines;
}
#include "fixed_layout.h"
static void prepareOverlay(OverlayWindow& item, bool continuing, std::wstring const& family, OverlayOptions const& options) {
    item.maskReady=false;
    if (!item.region.sourceRows.empty()) { prepareFixedOverlay(item,continuing,family,options); return; }
    HDC dc=GetDC(item.hwnd);
    if (!dc) return;
    int height=item.region.size>0 ? item.region.size : std::min(30,std::max(12,item.region.h-3));
    height=options.automatic?std::clamp(height,options.minimum,options.maximum):options.size;
    int minimum=options.automatic?options.minimum:options.size;
    // The current source revision owns its fitted size. OCR geometry noise,
    // placement changes, repeated final frames and new token chunks cannot
    // enlarge a font that already had to shrink for this same text object.
    if (options.automatic && continuing && item.fontPixels>0) height=std::min(height,item.fontPixels);
    for (;height>=minimum;--height) {
        HFONT font=CreateFontW(-height,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
            DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,item.region.pixelFont?NONANTIALIASED_QUALITY:CLEARTYPE_QUALITY,DEFAULT_PITCH,family.c_str());
        if (!font) { ReleaseDC(item.hwnd,dc); return; }
        HGDIOBJ previous=SelectObject(dc,font);
        wchar_t face[LF_FACESIZE]{}; GetTextFaceW(dc,LF_FACESIZE,face);
        auto lines=wrapLines(dc,item.region);
        bool fits=lines.empty() || lines.back().y+lines.back().height<=item.region.h-1;
        for (auto const& line:lines) fits=fits && line.width<=item.region.w-4;
        SelectObject(dc,previous);
        if (fits || height==minimum) {
            if (item.font) DeleteObject(item.font);
            item.font=font; item.fontPixels=height; item.fits=fits;
            item.fontFace=face;
            item.lines=std::move(lines); break;
        }
        DeleteObject(font);
    }
    ReleaseDC(item.hwnd,dc);
    if (!item.fits) item.stageMask(CreateRectRgn(0,0,0,0));
    else if (item.region.final) item.stageMask(nullptr,true);
    else {
        HRGN mask=CreateRectRgn(0,0,0,0);
        for (auto const& line:item.lines) {
            // Cover only the actual generated line extent, with tiny glyph padding.
            HRGN stripe=CreateRectRgn(0,std::max(0,line.y-1),std::min(item.region.w,line.width+4),
                std::min(item.region.h,line.y+line.height+1));
            CombineRgn(mask,mask,stripe,RGN_OR); DeleteObject(stripe);
        }
        item.stageMask(mask);
    }
}
static bool targetBounds(HWND target, DWORD expectedPid, RECT& area) {
    area = {GetSystemMetrics(SM_XVIRTUALSCREEN),GetSystemMetrics(SM_YVIRTUALSCREEN),0,0};
    area.right=area.left+GetSystemMetrics(SM_CXVIRTUALSCREEN);
    area.bottom=area.top+GetSystemMetrics(SM_CYVIRTUALSCREEN);
    if (!target) return true; // Unbound mode is for diagnostic fixtures only.
    DWORD actualPid=0;
    if (!IsWindow(target) || IsIconic(target) || !IsWindowVisible(target)) return false;
    GetWindowThreadProcessId(target,&actualPid);
    HWND foreground=GetForegroundWindow();
    if (actualPid != expectedPid || (foreground != target && GetAncestor(foreground,GA_ROOT) != target)) return false;
    RECT client{};
    if (!GetClientRect(target,&client)) return false;
    POINT origin{0,0}; if (!ClientToScreen(target,&origin)) return false;
    OffsetRect(&client,origin.x,origin.y);
    RECT clipped{}; if (!IntersectRect(&clipped,&area,&client)) return false;
    area=clipped; return true;
}
static bool clientAnchor(HWND target, RECT& area) {
    POINT origin{0,0};
    if(!target || !GetClientRect(target,&area) || !ClientToScreen(target,&origin))return false;
    OffsetRect(&area,origin.x,origin.y);return true;
}
static bool positionAt(Region const& region,RECT const& anchor,RECT& output) {
    if(!region.anchored) { output={region.x,region.y,region.x+region.w,region.y+region.h};return true; }
    if(anchor.right-anchor.left!=region.anchor.right-region.anchor.left ||
        anchor.bottom-anchor.top!=region.anchor.bottom-region.anchor.top)return false;
    int64_t x=int64_t(region.x)+anchor.left-region.anchor.left;
    int64_t y=int64_t(region.y)+anchor.top-region.anchor.top;
    if(x<INT_MIN || y<INT_MIN || x+region.w>INT_MAX || y+region.h>INT_MAX)return false;
    output={int(x),int(y),int(x)+region.w,int(y)+region.h};return true;
}

static bool commitOverlayFrame(OverlayWindow& item) {
    if(!item.maskReady)return false;
    HDC screen=GetDC(nullptr);
    bool ready=screen && item.ensurePaintBuffer(screen,item.region.w,item.region.h);
    if(screen)ReleaseDC(nullptr,screen);
    if(!ready)return false;
    RECT area{0,0,item.paintWidth,item.paintHeight};
    if(item.backgroundPixels.size()==size_t(item.paintWidth)*item.paintHeight*4) {
        GdiFlush();
        std::copy(item.backgroundPixels.begin(),item.backgroundPixels.end(),item.paintPixels);
    } else {
        SetDCBrushColor(item.paintDC,item.region.bg);
        if(!FillRect(item.paintDC,&area,static_cast<HBRUSH>(GetStockObject(DC_BRUSH))))return false;
    }
    SetTextColor(item.paintDC,item.region.fg);SetBkMode(item.paintDC,TRANSPARENT);
    HGDIOBJ oldFont=item.font?SelectObject(item.paintDC,item.font):nullptr;
    bool drawn=true;
    if(!item.backgroundSuppressed || item.region.coverSource)for(auto const& line:item.lines) {
        if(item.region.sourceRows.empty())
            drawn=bool(TextOutW(item.paintDC,2,line.y,line.text.data(),int(line.text.size()))) && drawn;
        else if(!line.text.empty() && line.drawable && item.fits)
            drawn=bool(ExtTextOutW(item.paintDC,line.x,line.y,ETO_CLIPPED,&line.clip,
                line.text.data(),UINT(line.text.size()),line.advances.data())) && drawn;
    }
    if(oldFont)SelectObject(item.paintDC,oldFont);
    if(!drawn || !GdiFlush())return false;
    size_t count=size_t(item.paintWidth)*item.paintHeight;
    // GDI text may clear alpha bytes. All covered source/background pixels are
    // explicitly opaque; only the unfinished stream's uncovered area is clear.
    if(!item.pendingMask) {
        for(size_t at=3;at<count*4;at+=4)item.paintPixels[at]=255;
    } else {
        DWORD bytes=GetRegionData(item.pendingMask,0,nullptr);
        if(bytes<sizeof(RGNDATAHEADER))return false;
        std::vector<uint8_t> storage(bytes);
        auto data=reinterpret_cast<RGNDATA*>(storage.data());
        if(GetRegionData(item.pendingMask,bytes,data)!=bytes)return false;
        for(size_t at=3;at<count*4;at+=4)item.paintPixels[at]=0;
        auto rectangles=reinterpret_cast<RECT const*>(data->Buffer);
        for(DWORD i=0;i<data->rdh.nCount;++i) {
            RECT clipped{};if(!IntersectRect(&clipped,&rectangles[i],&area))continue;
            for(int y=clipped.top;y<clipped.bottom;++y)
                for(int x=clipped.left;x<clipped.right;++x)
                    item.paintPixels[(size_t(y)*item.paintWidth+x)*4+3]=255;
        }
        // ULW_ALPHA requires premultiplied RGB, including fully clear pixels.
        for(size_t at=0;at<count*4;at+=4)if(!item.paintPixels[at+3])
            item.paintPixels[at]=item.paintPixels[at+1]=item.paintPixels[at+2]=0;
    }
    POINT destination{item.region.x,item.region.y},source{};
    SIZE size{item.paintWidth,item.paintHeight};
    BLENDFUNCTION blend{AC_SRC_OVER,0,255,AC_SRC_ALPHA};
    // Size, position, opacity mask and fully drawn RGB reach DWM in one commit.
    // Never expose a default bitmap with SetWindowPos(SWP_SHOWWINDOW) first.
    if(!UpdateLayeredWindow(item.hwnd,nullptr,&destination,&size,item.paintDC,&source,0,&blend,ULW_ALPHA))return false;
    ++item.paintCommits;item.bufferedPaint=true;
    if(!SetWindowRgn(item.hwnd,item.pendingMask,FALSE))return false;
    item.pendingMask=nullptr;
    // The first show is after a successful commit. Existing HWNDs also keep
    // their previous committed surface throughout preparation of this frame.
    SetWindowPos(item.hwnd,HWND_TOPMOST,0,0,0,0,
        SWP_NOACTIVATE|SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW);
    return true;
}

static LRESULT CALLBACK overlayProc(HWND hwnd, UINT message, WPARAM wp, LPARAM lp) {
    if (message == WM_NCCREATE) {
        auto create = reinterpret_cast<CREATESTRUCTW*>(lp);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create->lpCreateParams));
    }
    auto overlay = reinterpret_cast<OverlayWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (message == WM_NCHITTEST) return HTTRANSPARENT;
    if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
    if (message == WM_ERASEBKGND) return 1;
    bool showing=(message==WM_SHOWWINDOW && wp) || (message==WM_WINDOWPOSCHANGING &&
        lp && (reinterpret_cast<WINDOWPOS const*>(lp)->flags&SWP_SHOWWINDOW));
    if (showing && overlay && !overlay->everShown) {
        overlay->everShown=true;overlay->firstShowCommits=overlay->paintCommits;
    }
    if ((message==WM_PRINTCLIENT || message==WM_PRINT) && overlay) {
        // PrintWindow diagnostics copy the completed frame, never redraw an
        // intermediate background or rely on a layered HWND's empty GDI DC.
        if(overlay->bufferedPaint && overlay->paintDC)
            BitBlt(reinterpret_cast<HDC>(wp),0,0,overlay->paintWidth,overlay->paintHeight,
                overlay->paintDC,0,0,SRCCOPY);
        return 0;
    }
    if (message == WM_PAINT && overlay) {
        PAINTSTRUCT ps{};
        BeginPaint(hwnd,&ps);
        // ULW owns the visible surface. Invalidation/erase must never replace
        // it with a brush-only frame or fall back to unbuffered drawing.
        EndPaint(hwnd, &ps); return 0;
    }
    return DefWindowProcW(hwnd, message, wp, lp);
}

struct Context {
    std::mutex captureMutex, overlayMutex, backgroundMutex;
    std::shared_ptr<BackgroundFrame const> backgroundFrame;
    uint64_t backgroundFrameSequence=0;
    void publishBackground(int x,int y,int w,int h) {
        auto frame=std::make_shared<BackgroundFrame>();
        frame->x=x;frame->y=y;frame->w=w;frame->h=h;
        { std::lock_guard<std::mutex> lock(overlayMutex);frame->anchor=captureAnchor;frame->anchored=captureAnchored; }
        frame->pixels.assign(pixels,pixels+size_t(w)*h*4);
        std::lock_guard<std::mutex> lock(backgroundMutex);
        frame->sequence=++backgroundFrameSequence;backgroundFrame=std::move(frame);
    }
    void clearBackground() {
        std::lock_guard<std::mutex> lock(backgroundMutex);backgroundFrame.reset();
    }
    HDC screen = nullptr, memory = nullptr;
    HBITMAP bitmap = nullptr;
    HGDIOBJ oldBitmap = nullptr;
    uint8_t* pixels = nullptr;
    int width = 0, height = 0, previousX = 0, previousY = 0;
    uint64_t previousHash = 0;
    bool hasPrevious = false;
    std::wstring previousLanguage;
    std::thread overlayThread;
    DWORD overlayThreadId = 0;
    HANDLE overlayReady = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    std::vector<Region> pending;
    std::string overlayError;
    std::string overlaySnapshot = "{\"sequence\":0,\"font_family\":\"Microsoft YaHei UI\",\"regions\":[]}";
    uint64_t overlaySequence = 0;
    bool overlayUpdatePending = false;
    HWND targetWindow = nullptr;
    DWORD targetPid = 0;
    uint64_t targetEpoch = 0;
    std::wstring overlayFontFamily = L"Microsoft YaHei UI";
    uint64_t fontEpoch = 0;
    OverlayOptions overlayOptions;
    std::unique_ptr<WindowCapture> windowCapture;
    RECT captureAnchor{};
    int captureOffsetX=0,captureOffsetY=0;
    bool captureAnchored=false;
    bool preferGameCapture=false;
    bool capturePixels(int x,int y,int w,int h) {
        HWND target;DWORD pid;bool screenshots;
        { std::lock_guard<std::mutex> lock(overlayMutex);target=targetWindow;pid=targetPid;screenshots=overlayOptions.screenshots; }
        RECT anchor{};bool anchored=clientAnchor(target,anchor);
        { std::lock_guard<std::mutex> lock(overlayMutex);
          captureAnchor=anchor;captureAnchored=anchored;
          captureOffsetX=anchored?x-anchor.left:0;captureOffsetY=anchored?y-anchor.top:0; }
        bool windowPixels=false;
        if((screenshots || preferGameCapture) && target) {
            DWORD actual=0;GetWindowThreadProcessId(target,&actual);
            if(!IsWindow(target) || actual!=pid || IsIconic(target)) throw std::runtime_error("Game window unavailable");
            try {
                static thread_local Apartment apartment;apartment.check();
                if(!windowCapture || windowCapture->target!=target) windowCapture=std::make_unique<WindowCapture>(target);
                windowCapture->copy(x,y,w,h,pixels);
                windowPixels=true;
            } catch (hresult_error const&) {
                windowCapture.reset();
                if(screenshots) throw;
            }
        }
        if(!windowPixels) {
            windowCapture.reset();
            if(!BitBlt(memory,0,0,w,h,screen,x,y,SRCCOPY|CAPTUREBLT)) throw std::runtime_error("Screen capture failed");
            GdiFlush();
        }
        RECT after{};
        if(anchored && (!clientAnchor(target,after) || !EqualRect(&anchor,&after)))
            throw CapturePending("Game window moved during capture");
        return windowPixels;
    }
    Context() {
        if (!overlayReady) throw std::runtime_error("CreateEvent failed");
        overlayThread = std::thread([this] { overlayLoop(); });
        if (WaitForSingleObject(overlayReady, 10000) != WAIT_OBJECT_0) {
            if (overlayThreadId) PostThreadMessageW(overlayThreadId, STOP_OVERLAY, 0, 0);
            overlayThread.join(); CloseHandle(overlayReady); overlayReady = nullptr;
            throw std::runtime_error("Overlay thread startup timed out");
        }
    }
    void freeBitmap() {
        if (oldBitmap && memory) SelectObject(memory, oldBitmap);
        oldBitmap = nullptr;
        if (bitmap) DeleteObject(bitmap);
        bitmap = nullptr; pixels = nullptr; width = height = 0;
    }
    ~Context() {
        if (overlayThreadId) PostThreadMessageW(overlayThreadId, STOP_OVERLAY, 0, 0);
        if (overlayThread.joinable()) overlayThread.join();
        if (overlayReady) CloseHandle(overlayReady);
        freeBitmap();
        if (memory) DeleteDC(memory);
        if (screen) DeleteDC(screen);
    }
    void overlayLoop() {
        SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        overlayThreadId = GetCurrentThreadId();
        MSG message{}; PeekMessageW(&message, nullptr, WM_USER, WM_USER, PM_NOREMOVE);
        WNDCLASSW cls{}; cls.hInstance = moduleHandle; cls.lpszClassName = L"NKC_Galgame_TranslatorReplacement";
        cls.lpfnWndProc = overlayProc;
        RegisterClassW(&cls);
        UINT_PTR timer=SetTimer(nullptr,0,16,nullptr);
        SetEvent(overlayReady);
        std::vector<std::unique_ptr<OverlayWindow>> windows;
        std::map<uint64_t,MissingFontFit> missingFonts;
        uint64_t renderedTargetEpoch=0, renderedFontEpoch=0;
        while (GetMessageW(&message, nullptr, 0, 0) > 0) {
            if (message.message == STOP_OVERLAY) break;
            if (message.message == WM_TIMER) {
                HWND target; DWORD pid;
                { std::lock_guard<std::mutex> lock(overlayMutex); target=targetWindow; pid=targetPid; }
                RECT bounds{}; bool allowed=targetBounds(target,pid,bounds);
                RECT anchor{};if(target && !clientAnchor(target,anchor))allowed=false;
                for (auto& item:windows) {
                    RECT rectangle{};bool positioned=positionAt(item->region,anchor,rectangle);
                    RECT clipped{};
                    if (!allowed || !positioned || !IntersectRect(&clipped,&rectangle,&bounds) || !EqualRect(&clipped,&rectangle))
                        ShowWindow(item->hwnd,SW_HIDE);
                    else {
                        RECT actual{};GetWindowRect(item->hwnd,&actual);
                        if(!EqualRect(&actual,&rectangle))SetWindowPos(item->hwnd,nullptr,rectangle.left,rectangle.top,
                            0,0,SWP_NOACTIVATE|SWP_NOZORDER|SWP_NOSIZE);
                    }
                }
                continue;
            }
            if (message.message == UPDATE_OVERLAY) {
                std::vector<Region> regions;
                HWND target; DWORD pid;
                uint64_t sequence;
                uint64_t epoch;
                uint64_t currentFontEpoch;
                std::wstring family;
                OverlayOptions options;
                {
                    std::lock_guard<std::mutex> lock(overlayMutex);
                    regions = pending;
                    target=targetWindow; pid=targetPid;
                    sequence=overlaySequence;
                    epoch=targetEpoch;
                    currentFontEpoch=fontEpoch; family=overlayFontFamily;
                    options=overlayOptions;
                    overlayUpdatePending = false;
                }
                std::shared_ptr<BackgroundFrame const> frame;
                { std::lock_guard<std::mutex> lock(backgroundMutex);frame=backgroundFrame; }
                if (epoch!=renderedTargetEpoch || currentFontEpoch!=renderedFontEpoch) {
                    windows.clear(); missingFonts.clear(); renderedTargetEpoch=epoch;
                    renderedFontEpoch=currentFontEpoch;
                }
                auto now=Clock::now();
                for (auto it=missingFonts.begin();it!=missingFonts.end();) {
                    if (now-it->second.missingSince>FONT_HISTORY_TTL) it=missingFonts.erase(it);
                    else ++it;
                }
                RECT bounds{};
                if (!targetBounds(target,pid,bounds)) regions.clear();
                else {
                    std::vector<Region> clippedRegions;
                    for (auto& r:regions) {
                        RECT anchor{},placed{};
                        if(r.anchored) {
                            if(!clientAnchor(target,anchor)||!positionAt(r,anchor,placed))continue;
                            r.x=placed.left;r.y=placed.top;r.anchor=anchor;
                        }
                        RECT source{r.x,r.y,r.x+r.w,r.y+r.h}, clipped{};
                        if (IntersectRect(&clipped,&source,&bounds)) {
                            // Fixed source-row coordinates cannot be rebased by
                            // clipping only their parent. Hide a partly clipped
                            // fixed object rather than paint at a false origin.
                            if (!r.sourceRows.empty() && !EqualRect(&source,&clipped)) continue;
                            r.x=clipped.left; r.y=clipped.top; r.w=clipped.right-clipped.left; r.h=clipped.bottom-clipped.top;
                            clippedRegions.push_back(std::move(r));
                        }
                    }
                    regions=std::move(clippedRegions);
                }
                // Snapshot order is not object identity: OCR/pipeline results
                // can reorder or drop one object while another keeps streaming.
                using Identity = std::pair<uint64_t,size_t>;
                std::map<Identity,std::unique_ptr<OverlayWindow>> reusable;
                for (size_t i=0;i<windows.size();++i) {
                    auto id=windows[i]->region.trackId;
                    reusable.emplace(Identity{id,id ? 0 : i},std::move(windows[i]));
                }
                windows.clear();
                size_t backgroundBudget=64u*1024u*1024u;
                for (size_t i = 0; i < regions.size(); ++i) {
                    auto id=regions[i].trackId;
                    auto found=reusable.find(Identity{id,id ? 0 : i});
                    std::unique_ptr<OverlayWindow> current;
                    if (found!=reusable.end()) {
                        current=std::move(found->second); reusable.erase(found);
                    } else {
                        current=std::make_unique<OverlayWindow>();
                        current->hwnd = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE |
                            WS_EX_TOOLWINDOW | WS_EX_LAYERED, cls.lpszClassName, L"NKC_Galgame_Translator overlay", WS_POPUP,
                            0, 0, 1, 1, nullptr, nullptr, moduleHandle, current.get());
                        if (!current->hwnd) {
                            std::lock_guard<std::mutex> lock(overlayMutex);
                            overlayError = "Cannot create native overlay window"; break;
                        }
                        if (!SetWindowDisplayAffinity(current->hwnd, options.screenshots && target ? 0 : 0x11)) {
                            std::lock_guard<std::mutex> lock(overlayMutex);
                            overlayError = "Capture exclusion unavailable; Windows 10 2004+ with DWM is required";
                            break;
                        }
                    }
                    auto& item = *current;
                    auto const& next=regions[i];
                    // Untracked diagnostic callers provide no identity evidence,
                    // so a reused index must not carry fitting across objects.
                    bool continuing=next.trackId!=0 && item.fontPixels>0 && item.region.trackId==next.trackId &&
                        item.region.revision==next.revision && item.region.centerLabel==next.centerLabel && fixedGeometryContinues(item.region.sourceRows,next.sourceRows) && next.text.size()>=item.region.text.size() &&
                        next.text.compare(0,item.region.text.size(),item.region.text)==0;
                    auto remembered=missingFonts.find(next.trackId);
                    if (remembered!=missingFonts.end()) {
                        auto const& prior=remembered->second;
                        if (!item.font && prior.revision==next.revision && next.text.size()>=prior.text.size() &&
                                next.text.compare(0,prior.text.size(),prior.text)==0) {
                            item.fontPixels=prior.fontPixels; item.independentFontPixels=prior.independentFontPixels; continuing=true;
                        }
                        missingFonts.erase(remembered);
                    }
                    bool samePlacement=item.region.trackId==next.trackId && item.region.revision==next.revision &&
                        item.region.w==next.w && item.region.h==next.h && sameSourceRows(item.region.sourceRows,next.sourceRows);
                    bool holdPatch=next.holdBackground && samePlacement && !item.backgroundSuppressed &&
                        !item.backgroundPixels.empty();
                    bool sameBackground=(frame && item.backgroundSequence==frame->sequence && !next.holdBackground &&
                        !item.region.holdBackground &&
                        item.region.trackId==next.trackId && item.region.revision==next.revision &&
                        item.region.x==next.x && item.region.y==next.y && item.region.w==next.w && item.region.h==next.h &&
                        item.region.bg==next.bg && item.region.fg==next.fg && item.region.flashHeld==next.flashHeld && item.region.subtitle==next.subtitle &&
                        item.region.toolbarButton==next.toolbarButton && sameSourceRows(item.region.sourceRows,next.sourceRows)) || holdPatch;
                    size_t patchBytes=size_t(next.w)*next.h*4;
                    if(patchBytes>backgroundBudget) {
                        item.backgroundPixels.clear();item.backgroundSequence=0;
                        item.backgroundMasked=0;item.backgroundRepaired=0;
                        item.backgroundSuppressed=bool(frame);item.backgroundReason="budget";
                    } else if(!sameBackground) {
                        try {
                            auto sample=next;
                            if(frame && frame->anchored && sample.anchored) {
                                RECT at{};
                                if(positionAt(sample,frame->anchor,at)) { sample.x=at.left;sample.y=at.top; }
                            }
                            auto repaired=frame && !next.holdBackground?reconstructBackground(*frame,sample):RepairedBackground{};
                            item.backgroundPixels=std::move(repaired.pixels);
                            item.backgroundMasked=repaired.masked;item.backgroundRepaired=repaired.repaired;
                            item.backgroundSuppressed=repaired.suppressed;item.backgroundReason=repaired.reason;
                        }
                        catch(std::bad_alloc const&) { item.backgroundPixels.clear();item.backgroundSuppressed=bool(frame);item.backgroundReason="allocation"; }
                        item.backgroundSequence=frame?frame->sequence:0;
                        if(!item.backgroundPixels.empty()) ++item.backgroundBuilds;
                    }
                    backgroundBudget-=item.backgroundPixels.size();
                    item.region=std::move(regions[i]);
                    prepareOverlay(item,continuing,item.region.fontFamily.empty()?family:item.region.fontFamily,options);
                    windows.push_back(std::move(current));
                }
                // Fit all visible members before any member commits its paint.
                // Independent OCR/translation objects may be physical rows of
                // the same paragraph; they share the tightest fitting em size.
                harmonizeFixedFonts(windows,family,options);
                for(auto& current:windows) {
                    auto& item=*current;
                    // Leave the live game visible when the requested source cover
                    // cannot be reconstructed, including while tokens are pending.
                    if ((item.region.coverSource || !item.region.sourceRows.empty()) &&
                        (item.backgroundSuppressed || (item.backgroundPixels.empty() && (item.region.coverSource || target)) ||
                         (item.region.coverSource && (!item.fits || item.region.text.empty()) && item.backgroundReason!="flat_glyph_repaired"))) {
                        ShowWindow(item.hwnd,SW_HIDE);
                        continue;
                    }
                    bool committed=false;
                    try {committed=commitOverlayFrame(item);}
                    catch(std::bad_alloc const&) {}
                    if(!committed) {
                        item.bufferedPaint=false;++item.paintFailures;
                        // An allocation/upload failure must reveal the source,
                        // never substitute black or a stale translation frame.
                        ShowWindow(item.hwnd,SW_HIDE);
                    }
                }
                // A brief OCR miss must hide immediately without forgetting a
                // source revision's fitted size. Retain plain data only, never
                // an invisible HWND/HFONT. TTL starts at disappearance, not the
                // last repaint (a static game screen may be idle for minutes).
                for (auto const& previous:reusable) {
                    auto const& item=*previous.second;
                    if (item.region.trackId && item.fontPixels>0)
                        missingFonts.insert_or_assign(item.region.trackId,MissingFontFit{
                            item.region.revision,item.region.text,item.fontPixels,item.independentFontPixels,now});
                }
                while (missingFonts.size()>FONT_HISTORY_LIMIT) {
                    auto oldest=std::min_element(missingFonts.begin(),missingFonts.end(),
                        [](auto const& a,auto const& b) { return a.second.missingSince<b.second.missingSince; });
                    missingFonts.erase(oldest);
                }
                reusable.clear();
                std::ostringstream snapshot;
                snapshot << "{\"sequence\":" << sequence << ",\"font_family\":" << jsonString(to_string(family)) << ",\"regions\":[";
                for (size_t i=0;i<windows.size();++i) {
                    auto const& item=*windows[i]; auto const& r=item.region;
                    RECT actual{}; GetWindowRect(item.hwnd,&actual);
                    if (i) snapshot << ',';
                    snapshot << "{\"track_id\":" << r.trackId << ",\"revision\":" << r.revision
                        << ",\"hwnd\":" << reinterpret_cast<uintptr_t>(item.hwnd)
                        << ",\"font_px\":" << item.fontPixels << ",\"font_intrinsic_px\":" << item.independentFontPixels << ",\"font_peers\":" << item.fontPeers << ",\"fits\":" << (item.fits ? "true" : "false")
                        << ",\"font_face\":" << jsonString(to_string(item.fontFace))
                        << ",\"pixel_font\":" << (item.region.pixelFont?"true":"false")
                        << ",\"fixed_layout\":" << (!r.sourceRows.empty() ? "true" : "false")
                        << ",\"source_rows\":" << r.sourceRows.size()
                        << ",\"aero\":" << (!item.backgroundPixels.empty()&&!item.backgroundSuppressed?"true":"false")
                        << ",\"background_suppressed\":" << (item.backgroundSuppressed?"true":"false")
                        << ",\"background_mask_pixels\":" << item.backgroundMasked
                        << ",\"background_repaired_pixels\":" << item.backgroundRepaired
                        << ",\"background_reason\":" << jsonString(item.backgroundReason)
                        << ",\"background_frame\":" << item.backgroundSequence
                        << ",\"background_builds\":" << item.backgroundBuilds
                        << ",\"background_opaque\":true"
                        << ",\"paint\":{\"buffered\":" << (item.bufferedPaint ? "true" : "false")
                        << ",\"atomic_layered\":true,\"failures\":" << item.paintFailures
                        << ",\"first_show_commits\":" << item.firstShowCommits
                        << ",\"buffer_allocations\":" << item.paintAllocations
                        << ",\"size\":[" << item.paintWidth << ',' << item.paintHeight
                        << "],\"commits\":" << item.paintCommits << '}'
                        << ",\"final\":" << (r.final ? "true" : "false") << ",\"text_units\":" << r.text.size()
                        << ",\"bounds\":[" << actual.left << ',' << actual.top << ','
                        << actual.right-actual.left << ',' << actual.bottom-actual.top << "],\"lines\":[";
                    for (size_t line=0;line<item.lines.size();++line) {
                        auto const& rendered=item.lines[line];
                        if (line) snapshot << ',';
                        snapshot << "{\"y\":" << rendered.y << ",\"x\":" << rendered.x << ",\"width\":" << rendered.width << ",\"drawable\":" << (rendered.drawable?"true":"false")
                            << ",\"height\":" << rendered.height << ",\"start\":" << rendered.start
                            << ",\"length\":" << rendered.length
                            << ",\"ink_y\":" << rendered.inkTop << ",\"ink_height\":" << rendered.inkHeight
                            << ",\"clip\":[" << rendered.clip.left << ',' << rendered.clip.top << ','
                            << rendered.clip.right-rendered.clip.left << ',' << rendered.clip.bottom-rendered.clip.top << "]}";
                    }
                    snapshot << "]}";
                }
                snapshot << "]}";
                { std::lock_guard<std::mutex> lock(overlayMutex); overlaySnapshot=snapshot.str(); }
            } else { TranslateMessage(&message); DispatchMessageW(&message); }
        }
        if (timer) KillTimer(nullptr,timer);
        windows.clear();
    }
    void ensureBuffer(int w, int h) {
        // CreateDC/DeleteDC ownership is process-scoped, unlike GetDC/ReleaseDC
        // which require release on the same thread that acquired the common DC.
        if (!screen) screen = CreateDCW(L"DISPLAY",nullptr,nullptr,nullptr);
        if (!screen) throw std::runtime_error("CreateDC failed");
        if (!memory) memory = CreateCompatibleDC(screen);
        if (!memory) throw std::runtime_error("CreateCompatibleDC failed");
        if (width == w && height == h && bitmap) return;
        freeBitmap();
        BITMAPINFO bi{}; bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bi.bmiHeader.biWidth = w; bi.bmiHeader.biHeight = -h;
        bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
        bitmap = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, reinterpret_cast<void**>(&pixels), nullptr, 0);
        if (!bitmap) throw std::runtime_error("CreateDIBSection failed");
        oldBitmap = SelectObject(memory, bitmap); width = w; height = h; hasPrevious = false;
    }
};

static double elapsed(Clock::time_point start) { return std::chrono::duration<double, std::milli>(Clock::now() - start).count(); }
static void validateCapture(int x, int y, int w, int h) {
    SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (w <= 0 || h <= 0 || w > 4096 || h > 4096)
        throw std::runtime_error("Invalid capture region (maximum 4096x4096)");
    int vx = GetSystemMetrics(SM_XVIRTUALSCREEN), vy = GetSystemMetrics(SM_YVIRTUALSCREEN);
    int vw = GetSystemMetrics(SM_CXVIRTUALSCREEN), vh = GetSystemMetrics(SM_CYVIRTUALSCREEN);
    if (x < vx || y < vy || int64_t(x)+w > int64_t(vx)+vw || int64_t(y)+h > int64_t(vy)+vh)
        throw std::runtime_error("Capture region is outside the virtual desktop");
}
static std::array<int,3> background(uint8_t const* pixels, int width, int height, int x, int y, int w, int h) {
    // Quantized histogram of the surrounding strip, ignoring individual text strokes.
    std::array<unsigned,512> counts{};
    std::array<std::array<unsigned,3>,512> sums{};
    auto sample = [&](int xx, int yy) {
        xx = std::clamp(xx, 0, width - 1); yy = std::clamp(yy, 0, height - 1);
        auto p = pixels + (size_t(yy) * width + xx) * 4;
        unsigned slot = (p[2] >> 5) * 64 + (p[1] >> 5) * 8 + (p[0] >> 5);
        ++counts[slot]; sums[slot][0] += p[2]; sums[slot][1] += p[1]; sums[slot][2] += p[0];
    };
    for (int xx = x - 2; xx <= x + w + 2; xx += 2) { sample(xx,y-2); sample(xx,y+h+1); }
    for (int yy = y; yy < y+h; yy += 2) { sample(x-2,yy); sample(x+w+1,yy); }
    size_t best = std::distance(counts.begin(), std::max_element(counts.begin(), counts.end()));
    auto n = std::max(1u,counts[best]);
    return {int(sums[best][0]/n), int(sums[best][1]/n), int(sums[best][2]/n)};
}

static std::string recognizeBgra(uint8_t const* pixels, int w, int h, wchar_t const* language,
                                 int x=0, int y=0, double captureMs=0) {
    auto started=Clock::now();
    auto& runtime=ocrRuntime();
    if (w>int(OcrEngine::MaxImageDimension()) || h>int(OcrEngine::MaxImageDimension()))
        throw std::runtime_error("Image exceeds installed OCR engine limits");
    auto found=runtime.engines.find(language);
    if (found==runtime.engines.end())
        found=runtime.engines.emplace(language,OcrEngine::TryCreateFromLanguage(Language(language))).first;
    auto& engine=found->second;
    if (!engine) engine=OcrEngine::TryCreateFromLanguage(Language(language));
    if (!engine) throw std::runtime_error("OCR language is not installed. Install its Windows language OCR feature or select an available language.");
    auto bytes=winrt::Windows::Security::Cryptography::CryptographicBuffer::CreateFromByteArray(
        array_view<uint8_t const>(pixels,pixels+size_t(w)*h*4));
    auto image=SoftwareBitmap::CreateCopyFromBuffer(bytes,BitmapPixelFormat::Bgra8,w,h,BitmapAlphaMode::Ignore);
    auto result=engine.RecognizeAsync(image).get();
    std::ostringstream out;
    out << "{\"changed\":true,\"capture_ms\":" << captureMs << ",\"ocr_ms\":" << elapsed(started)
        << ",\"engine\":\"windows-ocr\",\"lines\":[";
    bool first=true;
    for (auto const& line:result.Lines()) {
        float rowTop=float(h),rowBottom=0;
        std::vector<OcrWord> words;
        for (auto const& word:line.Words()) {
            auto box=word.BoundingRect();
            if (box.Width<=0 || box.Height<=0) continue;
            rowTop=std::min(rowTop,box.Y); rowBottom=std::max(rowBottom,box.Y+box.Height);
            words.push_back(word);
        }
        if (words.empty()) continue;
        std::vector<std::vector<OcrWord>> cells(1);
        float previousRight=-1;
        for (auto const& word:words) {
            auto box=word.BoundingRect();
            // These are measured word bounds, never estimated string widths.
            // Ordinary spaces remain in one source row; distant columns do not.
            if (previousRight>=0 && box.X-previousRight>=std::max(24.f,3*(rowBottom-rowTop)))
                cells.emplace_back();
            cells.back().push_back(word);
            previousRight=std::max(previousRight,box.X+box.Width);
        }
        for (auto const& cell:cells) {
            float left=float(w),top=float(h),right=0,bottom=0;
            std::wstring text;
            for (auto const& word:cell) {
                auto box=word.BoundingRect();
                left=std::min(left,box.X);top=std::min(top,box.Y);
                right=std::max(right,box.X+box.Width);bottom=std::max(bottom,box.Y+box.Height);
                if (!text.empty()) text+=L' ';
                text+=word.Text();
            }
            if (cells.size()==1) text=line.Text();
            int ix=std::max(0,int(std::floor(left))),iy=std::max(0,int(std::floor(top)));
            int ir=std::min(w,int(std::ceil(right))),ib=std::min(h,int(std::ceil(bottom)));
            int lx=std::max(0,ix-2),ly=std::max(0,iy-2);
            int lw=std::min(w-lx,ir-lx+3),lh=std::min(h-ly,ib-ly+3);
            if (lw<=0 || lh<=0) continue;
            auto bg=background(pixels,w,h,lx,ly,lw,lh);
            int bright=(bg[0]*299+bg[1]*587+bg[2]*114)/1000,fg=bright>140?20:245;
            if (!first) out << ','; first=false;
            out << "{\"text\":" << jsonString(to_string(text)) << ",\"x\":" << x+lx << ",\"y\":" << y+ly
                << ",\"w\":" << lw << ",\"h\":" << lh << ",\"bg\":[" << bg[0] << ',' << bg[1] << ',' << bg[2]
                << "],\"fg\":[" << fg << ',' << fg << ',' << fg << "],\"ink_bounds\":["
                << x+ix << ',' << y+iy << ',' << ir-ix << ',' << ib-iy << ']';
            if (cells.size()>1) out << ",\"separated_cell\":true";
            out << '}';
        }
    }
    out << "]}";
    return out.str();
}

GL_API uint32_t gl_abi_version() { return 2; }

GL_API uint64_t gl_video_memory_mb(uint32_t vendor) {
    winrt::com_ptr<IDXGIFactory1> factory;
    if(FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory1),factory.put_void())))return 0;
    uint64_t best=0;
    for(UINT index=0;index<32;++index) {
        winrt::com_ptr<IDXGIAdapter1> adapter;
        if(FAILED(factory->EnumAdapters1(index,adapter.put())))break;
        DXGI_ADAPTER_DESC1 desc{};
        if(FAILED(adapter->GetDesc1(&desc)) || (desc.Flags&DXGI_ADAPTER_FLAG_SOFTWARE) ||
            (vendor && desc.VendorId!=vendor)) continue;
        best=std::max(best,std::max(uint64_t(1),uint64_t(desc.DedicatedVideoMemory)/(1024*1024)));
    }
    return best;
}
GL_API void* gl_create() {
    try { errorText.clear(); return new Context(); }
    catch (std::exception const& e) { errorText = e.what(); return nullptr; }
}
GL_API void gl_destroy(void* context) { delete static_cast<Context*>(context); }
GL_API const char* gl_error() { return errorText.c_str(); }
GL_API const char* gl_languages() {
    try {
        ocrRuntime();
        std::ostringstream out; out << '['; bool first = true;
        for (auto const& lang : OcrEngine::AvailableRecognizerLanguages()) {
            if (!first) out << ','; first = false;
            out << jsonString(to_string(lang.LanguageTag()));
        }
        out << ']'; resultText = out.str();
    } catch (hresult_error const& e) { resultText = "{\"error\":" + jsonString(to_string(e.message())) + "}"; }
    catch (std::exception const& e) { resultText = "{\"error\":" + jsonString(e.what()) + "}"; }
    return resultText.c_str();
}
GL_API void gl_reset(void* context) {
    if (!context) return;
    auto& c = *static_cast<Context*>(context);
    std::lock_guard<std::mutex> lock(c.captureMutex); c.hasPrevious = false; c.clearBackground();
}
GL_API const char* gl_capture_frame(void* context, int x, int y, int w, int h) {
    try {
        if (!context) throw std::runtime_error("Invalid native context");
        validateCapture(x,y,w,h);
        auto& c = *static_cast<Context*>(context);
        std::lock_guard<std::mutex> lock(c.captureMutex);
        SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        auto started = Clock::now(); c.ensureBuffer(w,h);
        bool windowPixels=c.capturePixels(x,y,w,h);
        uint64_t hash = 1469598103934665603ull;
        auto words = reinterpret_cast<uint32_t const*>(c.pixels);
        for (size_t i = 0,n = size_t(w)*h; i < n; ++i) { hash ^= words[i]&0xffffff; hash *= 1099511628211ull; }
        bool changed = !(c.hasPrevious && hash == c.previousHash && x == c.previousX &&
                         y == c.previousY && c.previousLanguage == L"__raw__");
        c.previousHash = hash; c.previousX = x; c.previousY = y; c.previousLanguage = L"__raw__"; c.hasPrevious = true;
        if(changed) c.publishBackground(x,y,w,h);
        std::ostringstream out;
        out << "{\"changed\":" << (changed ? "true" : "false") << ",\"window_pixels\":" << (windowPixels ? "true" : "false")
            << ",\"capture_ms\":" << elapsed(started) << '}';
        resultText = out.str();
    } catch (CapturePending const&) { resultText="{\"changed\":false,\"pending\":true,\"capture_ms\":0,\"ocr_ms\":0,\"lines\":[]}"; }
    catch (hresult_error const& e) { resultText = "{\"error\":"+jsonString("Game window capture unavailable ("+std::to_string(e.code().value)+"); disable translated screenshots")+"}"; }
    catch (std::exception const& e) { resultText = "{\"error\":" + jsonString(e.what()) + "}"; }
    return resultText.c_str();
}
GL_API int gl_copy_frame(void* context, uint8_t* destination, int capacity) {
    if (!context || !destination) return 0;
    auto& c = *static_cast<Context*>(context);
    std::lock_guard<std::mutex> lock(c.captureMutex);
    size_t bytes = size_t(c.width)*c.height*4;
    if (!c.pixels || capacity < 0 || size_t(capacity) < bytes) return 0;
    memcpy(destination,c.pixels,bytes); return int(bytes);
}
GL_API const char* gl_capture_ocr(void* context, int x, int y, int w, int h, const wchar_t* language) {
    try {
        if (!context || !language) throw std::runtime_error("Invalid native context or OCR language");
        validateCapture(x,y,w,h);
        auto& c = *static_cast<Context*>(context);
        std::lock_guard<std::mutex> lock(c.captureMutex);
        SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        auto started = Clock::now(); c.ensureBuffer(w,h);
        c.capturePixels(x,y,w,h);
        uint64_t hash = 1469598103934665603ull;
        // Hash every RGB pixel: sampling may otherwise miss a single changed character.
        auto words = reinterpret_cast<uint32_t const*>(c.pixels);
        for (size_t i = 0, n = size_t(w)*h; i < n; ++i) { hash ^= words[i] & 0xffffff; hash *= 1099511628211ull; }
        double captureMs = elapsed(started);
        std::ostringstream out;
        if (c.hasPrevious && hash == c.previousHash && x == c.previousX && y == c.previousY && c.previousLanguage == language) {
            out << "{\"changed\":false,\"lines\":[],\"capture_ms\":" << captureMs << ",\"ocr_ms\":0}";
            resultText = out.str(); return resultText.c_str();
        }
        c.publishBackground(x,y,w,h);
        auto recognized=recognizeBgra(c.pixels,w,h,language,x,y,captureMs);
        c.previousHash = hash; c.previousX = x; c.previousY = y; c.previousLanguage = language; c.hasPrevious = true;
        resultText=std::move(recognized);
    } catch (CapturePending const&) { resultText="{\"changed\":false,\"pending\":true,\"capture_ms\":0,\"ocr_ms\":0,\"lines\":[]}"; }
    catch (hresult_error const& e) { resultText = "{\"error\":" + jsonString(to_string(e.message())) + "}"; }
    catch (std::exception const& e) { resultText = "{\"error\":" + jsonString(e.what()) + "}"; }
    return resultText.c_str();
}
GL_API const char* gl_ocr_bgra(const uint8_t* pixels, int length, int w, int h, const wchar_t* language) {
    try {
        if (!pixels || !language || w<1 || h<1 || w>4096 || h>4096 || length!=int64_t(w)*h*4
            || !*language || wcsnlen_s(language,65)>64)
            throw std::runtime_error("Invalid OCR image");
        resultText=recognizeBgra(pixels,w,h,language);
    } catch (hresult_error const& e) { resultText="{\"error\":"+jsonString(to_string(e.message()))+"}"; }
    catch (std::exception const& e) { resultText="{\"error\":"+jsonString(e.what())+"}"; }
    return resultText.c_str();
}
GL_API int gl_overlay_options(void* context,int automatic,int size,int minimum,int maximum,int screenshots) {
    try {
        if(!context || (automatic!=0 && automatic!=1) || (screenshots!=0 && screenshots!=1)
            || size<8 || size>512 || minimum<8 || maximum>512 || minimum>maximum)
            throw std::runtime_error("Invalid overlay options");
        auto& c=*static_cast<Context*>(context);
        std::lock_guard<std::mutex> lock(c.overlayMutex);
        auto const& prior=c.overlayOptions;
        if(prior.automatic==bool(automatic) && prior.size==size && prior.minimum==minimum && prior.maximum==maximum && prior.screenshots==bool(screenshots))return 1;
        if(!c.overlayUpdatePending && !PostThreadMessageW(c.overlayThreadId,UPDATE_OVERLAY,0,0))
            throw std::runtime_error("Overlay thread is unavailable");
        c.overlayUpdatePending=true;c.overlayOptions={automatic!=0,screenshots!=0,size,minimum,maximum};
        ++c.fontEpoch;++c.overlaySequence;return 1;
    } catch(std::exception const& e) { errorText=e.what();return 0; }
}
GL_API int gl_set_font(void* context, const wchar_t* family) {
    try {
        if (!context || !family) throw std::runtime_error("Invalid overlay font family");
        size_t units=wcsnlen_s(family,LF_FACESIZE);
        if (!units || units>=LF_FACESIZE) throw std::runtime_error("Invalid overlay font family");
        bool visible=false;
        for (size_t i=0;i<units;++i) {
            wchar_t ch=family[i];
            if (ch<32 || (ch>=0x7f && ch<=0x9f)) throw std::runtime_error("Invalid overlay font family");
            if (ch>=0xd800 && ch<=0xdbff) {
                if (i+1>=units || family[i+1]<0xdc00 || family[i+1]>0xdfff)
                    throw std::runtime_error("Invalid overlay font family");
                ++i;
            } else if (ch>=0xdc00 && ch<=0xdfff) throw std::runtime_error("Invalid overlay font family");
            WORD classification{};
            if (!GetStringTypeW(CT_CTYPE1,&ch,1,&classification) || !(classification&C1_SPACE)) visible=true;
        }
        if (!visible) throw std::runtime_error("Invalid overlay font family");
        std::wstring next(family,units);
        auto& c=*static_cast<Context*>(context);
        std::lock_guard<std::mutex> lock(c.overlayMutex);
        if (next==c.overlayFontFamily) return 1; // Preserve streaming font fit.
        if (!c.overlayUpdatePending && !PostThreadMessageW(c.overlayThreadId,UPDATE_OVERLAY,0,0))
            throw std::runtime_error("Overlay thread is unavailable");
        c.overlayUpdatePending=true;
        c.overlayFontFamily=std::move(next); ++c.fontEpoch; ++c.overlaySequence;
        return 1;
    } catch (std::exception const& e) { errorText=e.what(); return 0; }
}
static int submitOverlay(void* context, const GLRegion* regions, int count,
    const GLSourceRow* rows,int rowCount,const int32_t* offsets,bool fixed,const int32_t* origins=nullptr,
    const wchar_t* const* families=nullptr,const int32_t* pixelFonts=nullptr,const int32_t* centerLabels=nullptr) {
    try {
        if (!context || count < 0 || count > 512 || (count && !regions)) throw std::runtime_error("Invalid overlay regions");
        if (fixed && (rowCount<0 || rowCount>16384 || (rowCount && !rows) || !offsets
            || offsets[0]!=0 || offsets[count]!=rowCount)) throw std::runtime_error("Invalid source rows");
        auto& c = *static_cast<Context*>(context);
        std::lock_guard<std::mutex> lock(c.overlayMutex);
        if (count && !c.overlayError.empty()) throw std::runtime_error(c.overlayError);
        std::vector<Region> next; next.reserve(count);
        std::set<uint64_t> identities;
        size_t totalTextUnits=0;
        for (int i = 0; i < count; ++i) {
            auto const& r = regions[i];
            if (fixed && (offsets[i]<0 || offsets[i+1]<offsets[i] || offsets[i+1]>rowCount
                || offsets[i+1]-offsets[i]>32)) throw std::runtime_error("Invalid source row offsets");
            if (r.width <= 0 || r.height <= 0 || r.width > 8192 || r.height > 8192
                || r.x > INT_MAX-r.width || r.y > INT_MAX-r.height) {
                if (fixed) throw std::runtime_error("Invalid fixed overlay bounds");
                continue;
            }
            if (r.font_size<0 || r.font_size>512) throw std::runtime_error("Invalid overlay font size");
            size_t units=r.text ? wcsnlen_s(r.text,64001) : 0;
            totalTextUnits+=units;
            if (units>64000 || totalTextUnits>1048576) throw std::runtime_error("Overlay text exceeds limit");
            if (fixed && r.text) for (size_t j=0;j<units;++j) {
                if (highSurrogate(r.text[j])) {
                    if (j+1>=units || !lowSurrogate(r.text[j+1])) throw std::runtime_error("Invalid overlay Unicode");
                    ++j;
                } else if (lowSurrogate(r.text[j])) throw std::runtime_error("Invalid overlay Unicode");
            }
            if (r.track_id && !identities.insert(r.track_id).second)
                throw std::runtime_error("Duplicate overlay text-object identity");
            next.push_back({r.x,r.y,r.width,r.height,r.font_size,r.background,r.foreground,
                r.text ? std::wstring(r.text,units) : L"",r.final!=0,r.track_id,r.revision});
            if(centerLabels) {
                int flag=centerLabels[i];
                if(flag<0 || flag>255 || ((flag&96) && !(flag&1)) || ((flag&152) && offsets[i+1]==offsets[i]) || ((flag&1) && offsets[i+1]-offsets[i]!=1) ||
                    ((flag&2) && offsets[i+1]==offsets[i]))
                    throw std::runtime_error("Invalid centered label");
                next.back().centerLabel=(flag&1)!=0;
                next.back().flashHeld=(flag&2)!=0;
                next.back().holdBackground=(flag&4)!=0;
                next.back().coverSource=(flag&8)!=0;
                next.back().subtitle=(flag&16)!=0;
                next.back().menuButton=(flag&32)!=0;
                next.back().toolbarButton=(flag&64)!=0;
                next.back().standaloneSubtitle=(flag&128)!=0;
            }
            if(families) {
                size_t length=families[i]?wcsnlen_s(families[i],LF_FACESIZE):0;
                if(!length||length>=LF_FACESIZE||!pixelFonts||pixelFonts[i]<0||pixelFonts[i]>1)
                    throw std::runtime_error("Invalid per-object font");
                for(size_t j=0;j<length;++j)
                    if(families[i][j]<32||highSurrogate(families[i][j])||lowSurrogate(families[i][j]))
                        throw std::runtime_error("Invalid per-object font name");
                next.back().fontFamily.assign(families[i],length);
                next.back().pixelFont=pixelFonts[i]!=0;
            }
            RECT anchor{};
            if(c.targetWindow && clientAnchor(c.targetWindow,anchor)) {
                auto& translated=next.back();translated.anchored=true;translated.anchor=anchor;
                if(origins && c.captureAnchored) {
                    int64_t x=int64_t(r.x)-origins[i*2]+c.captureOffsetX+anchor.left;
                    int64_t y=int64_t(r.y)-origins[i*2+1]+c.captureOffsetY+anchor.top;
                    if(x<INT_MIN||y<INT_MIN||x+r.width>INT_MAX||y+r.height>INT_MAX)
                        throw std::runtime_error("Overlay anchor overflow");
                    translated.x=int(x);translated.y=int(y);
                    translated.anchor.right=anchor.left+(c.captureAnchor.right-c.captureAnchor.left);
                    translated.anchor.bottom=anchor.top+(c.captureAnchor.bottom-c.captureAnchor.top);
                }
            }
            if (fixed) for (int j=offsets[i];j<offsets[i+1];++j) {
                auto const& row=rows[j];
                if (row.x<0 || row.y<0 || row.width<=0 || row.height<=0
                    || int64_t(row.x)+row.width>r.width || int64_t(row.y)+row.height>r.height
                    || row.ink_x<row.x || row.ink_y<row.y || row.ink_width<=0 || row.ink_height<=0
                    || int64_t(row.ink_x)+row.ink_width>int64_t(row.x)+row.width
                    || int64_t(row.ink_y)+row.ink_height>int64_t(row.y)+row.height
                    || row.font_size<0 || row.font_size>512) throw std::runtime_error("Invalid source row bounds");
                for (auto const& prior:next.back().sourceRows)
                    if (std::max(prior.ink_x,row.ink_x)<std::min(prior.ink_x+prior.ink_width,row.ink_x+row.ink_width)
                        && std::max(prior.ink_y,row.ink_y)<std::min(prior.ink_y+prior.ink_height,row.ink_y+row.ink_height))
                        throw std::runtime_error("Overlapping source row ink");
                next.back().sourceRows.push_back(row);
            }
        }
        c.pending = std::move(next);
        ++c.overlaySequence;
        // Streaming tokens can arrive faster than painting: retain only the newest
        // snapshot and at most one queued update, rather than accumulating work.
        if (!c.overlayUpdatePending) {
            if (!PostThreadMessageW(c.overlayThreadId, UPDATE_OVERLAY, 0, 0))
                throw std::runtime_error("Overlay thread is unavailable");
            c.overlayUpdatePending = true;
        }
        return 1;
    } catch (std::exception const& e) { errorText = e.what(); return 0; }
}
GL_API int gl_overlay(void* context,const GLRegion* regions,int count) {
    return submitOverlay(context,regions,count,nullptr,0,nullptr,false);
}
GL_API int gl_overlay_fixed(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int rowCount,const int32_t* offsets) {
    return submitOverlay(context,regions,count,rows,rowCount,offsets,true);
}
GL_API int gl_overlay_anchored(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int rowCount,const int32_t* offsets,const int32_t* origins) {
    if(count && !origins) { errorText="Missing capture origins";return 0; }
    return submitOverlay(context,regions,count,rows,rowCount,offsets,true,origins);
}
GL_API int gl_overlay_styled(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int rowCount,const int32_t* offsets,const int32_t* origins,
    const wchar_t* const* families,const int32_t* pixelFonts) {
    if(count && (!families||!pixelFonts)) { errorText="Missing font choices";return 0; }
    return submitOverlay(context,regions,count,rows,rowCount,offsets,true,origins,families,pixelFonts);
}
GL_API int gl_overlay_labels(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int rowCount,const int32_t* offsets,const int32_t* origins,
    const wchar_t* const* families,const int32_t* pixelFonts,const int32_t* centerLabels) {
    if(count && !centerLabels) { errorText="Missing centered label flags";return 0; }
    return submitOverlay(context,regions,count,rows,rowCount,offsets,true,origins,families,pixelFonts,centerLabels);
}
static int CALLBACK installedFace(const LOGFONTW* font,const TEXTMETRICW*,DWORD,LPARAM output) {
    *reinterpret_cast<std::wstring*>(output)=font->lfFaceName;return 0;
}
GL_API int gl_font_supports(const wchar_t* family,const wchar_t* text) {
    if(!family||!text) return 0;
    size_t nameLength=wcsnlen_s(family,LF_FACESIZE),units=wcsnlen_s(text,4097);
    if(!nameLength||nameLength>=LF_FACESIZE||units>4096) return 0;
    for(size_t i=0;i<units;++i) if(highSurrogate(text[i])||lowSurrogate(text[i])) return 0;
    HDC dc=CreateCompatibleDC(nullptr);if(!dc)return 0;
    LOGFONTW query{};query.lfCharSet=DEFAULT_CHARSET;wcscpy_s(query.lfFaceName,family);
    std::wstring installed;
    EnumFontFamiliesExW(dc,&query,installedFace,reinterpret_cast<LPARAM>(&installed),0);
    if(installed.empty()){DeleteDC(dc);return 0;}
    HFONT font=CreateFontW(-24,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,
        OUT_TT_ONLY_PRECIS,CLIP_DEFAULT_PRECIS,DEFAULT_QUALITY,DEFAULT_PITCH,family);
    if(!font){DeleteDC(dc);return 0;}
    auto prior=SelectObject(dc,font);
    wchar_t actual[LF_FACESIZE]{};GetTextFaceW(dc,LF_FACESIZE,actual);
    WORD glyphs[4096]{};
    bool supported=_wcsicmp(actual,family)==0 || _wcsicmp(actual,installed.c_str())==0;
    if(supported&&units) {
        supported=GetGlyphIndicesW(dc,text,int(units),glyphs,GGI_MARK_NONEXISTING_GLYPHS)!=GDI_ERROR;
        for(size_t i=0;i<units&&supported;++i) supported=glyphs[i]!=0xffff && glyphs[i]!=0;
    }
    SelectObject(dc,prior);DeleteObject(font);DeleteDC(dc);return supported?1:0;
}
GL_API const char* gl_overlay_snapshot(void* context) {
    if (!context) { resultText="{\"error\":\"Invalid native context\"}"; return resultText.c_str(); }
    auto& c=*static_cast<Context*>(context);
    std::lock_guard<std::mutex> lock(c.overlayMutex);
    resultText=c.overlaySnapshot;
    return resultText.c_str();
}
GL_API void gl_hide(void* context) {
    if (!context) return;
    auto& c=*static_cast<Context*>(context);
    std::lock_guard<std::mutex> captureLock(c.captureMutex);
    c.windowCapture.reset();
    std::lock_guard<std::mutex> lock(c.overlayMutex);
    // Explicit stop/focus loss ends fitting history; an ordinary empty
    // gl_overlay snapshot only represents temporarily missing OCR objects.
    ++c.targetEpoch;
    c.pending.clear(); ++c.overlaySequence;
    if (!c.overlayUpdatePending && PostThreadMessageW(c.overlayThreadId,UPDATE_OVERLAY,0,0)) c.overlayUpdatePending=true;
}
GL_API void gl_prefer_game_capture(void* context, int enabled) {
    if(!context) return;
    auto& c=*static_cast<Context*>(context);
    std::lock_guard<std::mutex> lock(c.captureMutex);
    if(c.preferGameCapture==bool(enabled)) return;
    c.preferGameCapture=bool(enabled);
    c.windowCapture.reset();
    c.hasPrevious=false;
}
GL_API void gl_set_target(void* context, uintptr_t window, uint32_t processId) {
    if (!context) return;
    auto& c=*static_cast<Context*>(context);
    std::lock_guard<std::mutex> captureLock(c.captureMutex);
    c.windowCapture.reset();
    std::lock_guard<std::mutex> lock(c.overlayMutex);
    c.targetWindow=reinterpret_cast<HWND>(window); c.targetPid=processId;
    c.captureAnchored=false;
    c.clearBackground();
    ++c.targetEpoch;
    c.pending.clear();
    ++c.overlaySequence;
    if (!c.overlayUpdatePending && PostThreadMessageW(c.overlayThreadId,UPDATE_OVERLAY,0,0)) c.overlayUpdatePending=true;
}
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    // Static CRT and thread-local WinRT engines need normal thread notifications.
    if (reason == DLL_PROCESS_ATTACH) moduleHandle = instance;
    return TRUE;
}
