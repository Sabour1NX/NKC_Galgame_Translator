// SPDX-License-Identifier: MIT
// HWND-only capture: external screenshots may include overlays while OCR never
// reads them. No picker, input injection, window hiding or affinity toggling.
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>

struct WindowCapture {
    using Pool=winrt::Windows::Graphics::Capture::Direct3D11CaptureFramePool;
    using Item=winrt::Windows::Graphics::Capture::GraphicsCaptureItem;
    using Session=winrt::Windows::Graphics::Capture::GraphicsCaptureSession;
    HWND target=nullptr;
    winrt::com_ptr<ID3D11Device> device;
    winrt::com_ptr<ID3D11DeviceContext> immediate;
    winrt::com_ptr<ID3D11Texture2D> staging;
    winrt::Windows::Graphics::DirectX::Direct3D11::IDirect3DDevice runtime{nullptr};
    Item item{nullptr}; Pool pool{nullptr}; Session session{nullptr};
    int width=0,height=0;
    std::vector<uint8_t> latest;
    explicit WindowCapture(HWND hwnd):target(hwnd) {
        if(!Session::IsSupported()) throw std::runtime_error("Window capture unavailable; disable translated screenshots");
        UINT flags=D3D11_CREATE_DEVICE_BGRA_SUPPORT;
        HRESULT hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,flags,nullptr,0,
            D3D11_SDK_VERSION,device.put(),nullptr,immediate.put());
        if(FAILED(hr)) winrt::check_hresult(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,flags,nullptr,0,
            D3D11_SDK_VERSION,device.put(),nullptr,immediate.put()));
        auto dxgi=device.as<IDXGIDevice>(); winrt::com_ptr<IInspectable> inspectable;
        winrt::check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.get(),inspectable.put()));
        runtime=inspectable.as<winrt::Windows::Graphics::DirectX::Direct3D11::IDirect3DDevice>();
        auto factory=winrt::get_activation_factory<Item,IGraphicsCaptureItemInterop>();
        winrt::check_hresult(factory->CreateForWindow(hwnd,winrt::guid_of<Item>(),winrt::put_abi(item)));
        auto size=item.Size(); validateSize(size.Width,size.Height);
        width=size.Width;height=size.Height;
        pool=Pool::CreateFreeThreaded(runtime,winrt::Windows::Graphics::DirectX::DirectXPixelFormat::B8G8R8A8UIntNormalized,2,size);
        session=pool.CreateCaptureSession(item);
        session.IsCursorCaptureEnabled(false);
        // Secondary windows are excluded by default. Do not request borderless
        // capture access: Windows may show its normal capture indicator.
        session.StartCapture();
    }
    ~WindowCapture() {
        try { if(session)session.Close(); if(pool)pool.Close(); } catch(...) {}
    }
    static void validateSize(int w,int h) {
        if(w<1 || h<1 || w>8192 || h>8192 || int64_t(w)*h>16777216)
            throw std::runtime_error("Window capture dimensions exceed limits");
    }
    void copy(int x,int y,int w,int h,uint8_t* output) {
        using Frame=winrt::Windows::Graphics::Capture::Direct3D11CaptureFrame;
        Frame frame{nullptr};
        auto deadline=Clock::now()+std::chrono::milliseconds(latest.empty()?700:40);
        do {
            auto next=pool.TryGetNextFrame();
            if(next) { if(frame)frame.Close(); frame=std::move(next); }
            else if(frame || !latest.empty())break;
            else std::this_thread::sleep_for(std::chrono::milliseconds(5));
        } while(Clock::now()<deadline);
        if(frame) {
            auto size=frame.ContentSize();validateSize(size.Width,size.Height);
            if(size.Width!=width || size.Height!=height) {
                width=size.Width;height=size.Height;latest.clear();staging=nullptr;frame.Close();
                pool.Recreate(runtime,winrt::Windows::Graphics::DirectX::DirectXPixelFormat::B8G8R8A8UIntNormalized,2,size);
                throw CapturePending("Window resized; waiting for a fresh capture");
            }
            auto access=frame.Surface().as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
            winrt::com_ptr<ID3D11Texture2D> texture;
            winrt::check_hresult(access->GetInterface(__uuidof(ID3D11Texture2D),texture.put_void()));
            if(!staging) {
                D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
                desc.BindFlags=0;desc.MiscFlags=0;desc.Usage=D3D11_USAGE_STAGING;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
                winrt::check_hresult(device->CreateTexture2D(&desc,nullptr,staging.put()));
            }
            immediate->CopyResource(staging.get(),texture.get());
            latest.resize(size_t(width)*height*4);
            D3D11_MAPPED_SUBRESOURCE mapped{};
            winrt::check_hresult(immediate->Map(staging.get(),0,D3D11_MAP_READ,0,&mapped));
            for(int row=0;row<height;++row)
                memcpy(latest.data()+size_t(row)*width*4,static_cast<uint8_t*>(mapped.pData)+size_t(row)*mapped.RowPitch,size_t(width)*4);
            immediate->Unmap(staging.get(),0);frame.Close();
        }
        if(latest.empty()) throw CapturePending("Waiting for the game window capture");
        RECT bounds{};
        if(FAILED(DwmGetWindowAttribute(target,DWMWA_EXTENDED_FRAME_BOUNDS,&bounds,sizeof(bounds))))
            throw std::runtime_error("Cannot locate the captured game window");
        // Reject ambiguous scaling instead of silently translating displaced pixels.
        if(bounds.right-bounds.left!=width || bounds.bottom-bounds.top!=height)
            throw CapturePending("Window capture size changed");
        int left=x-bounds.left,top=y-bounds.top;
        if(left<0 || top<0 || int64_t(left)+w>width || int64_t(top)+h>height)
            throw CapturePending("Capture region moved outside the game window");
        for(int row=0;row<h;++row)
            memcpy(output+size_t(row)*w*4,latest.data()+(size_t(top+row)*width+left)*4,size_t(w)*4);
    }
};
