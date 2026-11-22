# 第三方组件

Windows x64 · 1.01.12

二色蝶·游戏实时翻译（`NKC_Galgame_Translator`）主程序、原生核心、项目构建脚本及红白太极图标采用 **MIT**，完整许可证见 `LICENSE`。独立图片/JSON OCR 工具 `tools/ocr_helper.py` 采用 MIT，完整许可写在该源码头部。主程序通过进程管道通信，不导入 Tesseract；原生 OCR 依赖由独立 helper 加载。

各第三方组件沿用各自的原始许可证。发行包的 `licenses/` 保存许可及版权声明，`third_party_sources/` 保存须提供的对应源码。

## 组件与用途

| 组件 | 在二色蝶中的用途 |
|---|---|
| CPython、Tcl/Tk | 运行主程序，绘制窗口、菜单和设置界面 |
| Windows Graphics Capture、Windows OCR、Win32 | 调用系统能力采集窗口、识别文字、绘制覆盖与读取资源占用，由 Windows 提供 |
| Pillow | 处理捕获帧、局部图像和导出截图 |
| tesserocr、Tesseract、tessdata_fast | 运行英语和日语等语言的本地 OCR |
| Leptonica | 为 Tesseract 读入、转换和预处理图像 |
| SQLite、zlib | 保存译文历史和上下文档案，压缩历史记录 |
| HTTPX、httpcore、h11、anyio | 调用配置的翻译接口，读取流式回复，处理 HTTP 连接和 I/O |
| OpenSSL、certifi、idna | 加密 HTTPS 连接、验证证书、处理国际化主机名 |
| 思源黑体 | 显示软件和欢迎页文字 |
| PyInstaller | 生成 Windows 主程序、独立 OCR 工具和安装包 |
| libiconv、libcharset | 为独立 OCR 工具的原生依赖转换和识别字符编码 |
| RapidOCR、ONNX Runtime GPU、NumPy、OpenCV | 可选 CUDA 扩展的 OCR 模型推理、识别流水线和图像运算 |
| NVIDIA CUDA、cuDNN | 可选扩展在兼容 NVIDIA GPU 上执行识别模型 |
| NVIDIA NVML | 读取 CUDA 设备的利用率和显存，由本机 NVIDIA 驱动提供 |
## 运行时与 Python 组件

| 组件 / 实际版本 | 许可及原始资料 |
|---|---|
| CPython 3.14.10 | PSF 及历史许可；官方安装目录 LICENSE.txt 完整复制，含 Microsoft CRT、bzip2、libffi、Zstd、OpenSSL、Tcl/Tk 的附加声明 |
| Tcl/Tk 9.0.4 | Tcl/Tk 各自原始 license.terms；来源为 Python 官方依赖源码标签 |
| OpenSSL 3.5.9（Python TLS） | Apache-2.0，原始 LICENSE.txt |
| Expat 2.9.0 | MIT，原始 COPYING |
| libffi 3.4.4 | MIT，原始 LICENSE |
| zlib-ng 2.2.4（Python zlib，运行接口显示 1.3.1.zlib-ng） | zlib 及上游所列版权；原始 LICENSE.md |
| zlib 1.3.2（Tcl 配套 zlib1.dll） | zlib，原始 LICENSE |
| bzip2 1.0.8 | bzip2 原始许可 |
| liblzma/XZ 5.2.5（Python） | 对应 COPYING 区分 public-domain 库与 GPL/LGPL 工具/构建材料，本程序使用库 |
| mpdecimal 4.0.0 | 上游 COPYRIGHT.txt，BSD 条款及其中附加声明 |
| Zstandard 1.5.7（Python） | BSD，原始 LICENSE |
| LibTomMath（Tcl 9.0.4 vendored） | 上游 LibTom public-domain dedication，原始 LICENSE |
| httpx 0.28.1 / httpcore 1.0.9 | BSD-3-Clause |
| Pillow 13.0.0 | MIT-CMU；其 wheel 自带的编解码库声明也随包保留 |
| anyio 4.16.0 / h11 0.16.0 | MIT |
| idna 3.20 | BSD-3-Clause |
| certifi 2026.10.23 | MPL-2.0；完整源码发行包在 `third_party_sources/certifi-2026.10.23/` |
| PyInstaller 6.22.3 | GPLv2-or-later with bootloader exception；原始许可证及例外条款随包提供 |

Python 安装版附加许可的聚合原文、分组件原文、下载 URL 和 SHA256 记录位于发行包 `licenses/runtime-notices/`，开发目录对应 `vendor/runtime-notices/`。没有通过不完整摘录代替原文。`provenance.json` 记录许可来源；运行时版本来源与 DLL 清单见项目依赖文档及 SBOM。

## 独立 OCR helper

`tesserocr 2.13.0` 为 MIT，捆绑 Tesseract 5.5.4（Apache-2.0）、Leptonica 1.87.0（BSD-style）及动态依赖。日语/英语 `tessdata_fast` 模型为 Apache-2.0，保持其原 LICENSE。本版输入路径只接受经过验证的 BMP，并把原始 RGB 传给 `SetImageBytes`；这不改变所分发组件的许可，也不等于包内所有库没有漏洞。

官方 wheel 的 `licenses/.wheel-licenses/` 提供 libarchive、bzip2、giflib、ICU、Lerc、libcurl、libdeflate、libiconv、libjpeg-turbo、liblzma、libpng、libpsl、libssh2、libtiff、libwebp、libxml2、zlib、OpenJPEG、OpenSSL、zstd、lz4、Tesseract、Leptonica、Microsoft runtime 等原始声明。所有这些文件递归保留；`ocr-bundled-license-audit.json` 将实际 28 个 DLL 映射到随 wheel 提供的许可文件，而非把许可目录中全部条目当成实际加载组件。

实际捆绑的 `iconv`、`charset` 动态库属于 **libiconv 1.18 / LGPL-2.1-only**。`third_party_sources/libiconv-1.18/` 提供 GNU 完整源包、原 LGPL/GPL 文本、准确 conda-forge `hc1393d2_3` Windows 构建配方/补丁、来源/哈希与二进制代码段比对证据。独立 GPL 命令行 iconv.exe 不在程序包中。用户可按该目录说明修改、重新构建和替换库；项目协议不限制这些许可授予的修改、再分发及为调试修改进行逆向工程的权利。

Microsoft CRT/Windows SDK 按各自条款提供；`nkc_galgame_translator_core.dll` 使用 MSVC 静态运行时，运行时相关声明保留。每个第三方组件以随附原始条款为准。没有分发游戏文件、私人 API Key、密文凭据或私人翻译数据库。

## Source Han Sans SC

Adobe Source Han Sans SC Regular and Medium (2.005R) are distributed under the SIL Open Font License 1.1. The original license accompanies the fonts in assets/fonts/OFL.txt. Upstream source: https://github.com/adobe-fonts/source-han-sans/tree/2.005R
