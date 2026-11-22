# 依赖、构建与供应链 · 0.01.27

## 0.01.27 CUDA 运行时与预热契约

当前可选组件锁定 ONNX Runtime GPU 1.32.0、RapidOCR 3.10.0、CUDA 13.x runtime / cuDNN 9.x。本机 RTX 3070 / 驱动 617.42 已验证；其他组合不能据此视为兼容。模型与轮子 SHA 固定；provider arena 预算拆分为检测/识别两部分，默认合计 1 GiB，另有驱动和运行库内存。

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` 保持底层调用默认不启用的兼容行为；App 按用户配置默认启用，并可交接已经预热的 `CudaOcr` 实例。`App._prepare_cuda()` 的后台线程只调用本地 `warmup()`，不采屏或请求 API；同 helper 可供后续 OCR 复用。预热不保证每个新图像形状没有首次推理开销。

## 0.01.27 可选 CUDA 组件安装

CUDA 运行组件独立于基础程序，约 2.1 GiB，另有约 31 MB 的模型；实际分发大小以清单为准。用户显式执行 `vendor/python/python.exe tools/setup_cuda_ocr.py` 才下载和安装到项目内 `vendor/cuda` / `models/cuda`；`--verify` 检查已安装版本与模型哈希，不等同真实 GPU 推理测试。不会修改全局 PATH/CUDA，不在普通设置开关时自动安装。缺组件仍可用 CPU。

第三方版本、SHA 与许可分别见 `requirements-cuda.lock`、`CUDA_DEPENDENCY_MANIFEST.json`、`third_party/cuda/` 和 `models/cuda/LICENSE`。主进程仅使用受限图片/JSON IPC，不加载深度学习包。运行库 arena 预算不包含驱动及所有临时缓冲；整机 nvidia-smi 数值不是本进程显存用量。

## 0.01.27 CUDA 识别与实际回退

首次语言设置和常规设置共用 CUDA 控件。`cuda_enabled` 默认开启；只在 OCR **自动模式**且源语言为英语、日语或中文时尝试 CUDA。手动 Windows / Pixel 模式明确走 CPU；自动模式检测到经典英语像素画面且便携识别可用时优先 CPU Pixel 路径（`pixel_priority`）；其他语言继续使用已有本地识别。组件缺失、无兼容 GPU、模型校验或推理失败时回退 Windows / Tesseract，并显示实际状态，不能把“文件已安装”当作“CUDA 已运行”。失败后的当前 OCR 实例不反复重试 GPU，修改设置后停止并重新开始。

| 设置 | 默认 | 范围与作用 |
|---|---|---|
| `cuda_enabled` | `true` | 开关；不自动下载或安装组件 |
| `cuda_quality` | `75` | 0–100，高性能到高精度；线性调节检测长边，按 32 像素量化 |
| `cuda_memory_mb` | `1024` | 256–16384 MiB；推理内存 arena 预算，不会强行占满 1 GiB，运行库和驱动另有开销 |

检测长边约为 `768 + 11.52 × cuda_quality` 后按 32 像素量化；75 对应 1632 像素。仅缩小超出上限的图像，小图在不同档位可能等效；数值不是准确率百分比，也不保证单调提速或提高精度。CUDA 模型为 PP-OCRv6-small，GPU/依赖验证结果以本版报告为准，不提前声称所有 NVIDIA 显卡可用。

启用可选云端 AI 图像精读时，CUDA 已输出的行仅在置信度不低于 95 且没有拒绝标记时直接送译，其余仍走核验路径。**95 是模型分数门槛，不是 95% 实测准确率承诺**。CUDA 本地 OCR 不上传图片；云端精读仍遵循独立开关和图片发送规则。

0.01.27 加入可选 CUDA OCR、后台联网语境与整组字号修复。本版新增同图 OCR 评审，对照 0.01.15，分别报告冷启动、背景变化热路径、复访缓存和逐字精度；真实 API 链路另列。历史证据保留原版本标签，当前方法与范围见性能报告及 TEST_REPORT.json。

适用版本：0.01.27 · 文档复核：2026-11-18。历史记录保留原版号。

## 依赖复核

本版未新增第三方包或字体包。字体风格分析复用 Pillow13.0.0；安装字体与字形检查使用 Windows GDI。新增原生导出已重新编译，不能用旧 DLL 代替。实际锁定依赖及许可见 DEPENDENCY_MANIFEST.json 和 THIRD_PARTY_NOTICES.md。

目标平台：Windows 10/11 x86-64。发行 ZIP 自带 Python、Tk、网络库、原生核心、OCR 辅助程序及日语/英语 OCR 模型，使用者无需另装 Python。Windows OCR 可用语言取决于系统语言组件；便携 OCR 为日语/英语提供后备。翻译目标语言交给配置的 AI 服务商，不等于 OCR 可识别任意语言。

## 精确版本与用途

| 组件 | 本版版本 | 用途 | 许可来源 |
|---|---|---|---|
| CPython x64 | 3.14.10 | Python 运行时，含 tkinter/sqlite3/ctypes | 官方 Python LICENSE 与 Tcl/Tk notices |
| OpenSSL | 3.5.9 | CPython TLS 实现 | 官方 Python 分发中的 OpenSSL notices |
| httpx / httpcore / h11 | 0.28.1 / 1.0.9 / 0.16.0 | HTTPS 与有界 SSE 传输 | 各包原始 LICENSE |
| anyio / typing_extensions | 4.16.0 / 4.16.0 | 网络库依赖 | 各包原始 LICENSE |
| certifi / idna | 2026.10.23 / 3.20 | CA 信任集合与域名编码 | 各包原始 LICENSE |
| Pillow | 13.0.0 | 本机截图像素、受限 BMP 解码及测试图片 | MIT-CMU 与原始 notices |
| tesserocr | 2.13.0，cp314-win_amd64 wheel | 独立 OCR 工具的 Python/C++ 封装 | MIT |
| Tesseract / Leptonica | 5.5.4 / 1.87.0 | OCR 与原始像素处理，随 tesserocr wheel | Apache-2.0 / BSD-2-Clause；保留 wheel notices |
| tessdata_fast eng/jpn | 随包模型，精确 SHA256 见清单 | 英语、日语 OCR 模型 | 模型目录 Apache-2.0 LICENSE |
| MSVC / Windows SDK | 构建日志与清单记录实际工具版本 | C++17、WinRT、GDI 原生 DLL | Microsoft 工具链及系统组件条款 |
| PyInstaller | 6.22.3 | 打包程序与独立 OCR EXE | GPL 加 bootloader exception；仅构建依赖 |
| pytest / pywin32 | 9.2.0 / 312 | 回归及 Windows 图形测试 | MIT / PSF 等，见实际包元数据 |
| pip-audit | 2.10.1 | 查询 Python 包的公开漏洞记录 | Apache-2.0；仅审计工具 |

完整传递依赖、下载 URL、wheel SHA256、用途分组与上游许可字段见 [DEPENDENCY_MANIFEST.json](DEPENDENCY_MANIFEST.json)。发行目录另提供 `SBOM.cdx.json` 和 `licenses/components.json`。`licenses/` 保留原始许可文本，主程序的 MIT 不会重新许可第三方文件。上表是组件清单，不是把所有依赖视为同一许可证的法律结论。

## 锁文件

- `requirements-runtime.lock`：主程序 8 个 Python 包。
- `requirements-ocr.lock`：独立 OCR wheel；主程序不导入 tesserocr。
- `requirements-build.lock`：PyInstaller 及其构建依赖。
- `requirements-test.lock`：测试所需包。
- `requirements-audit.lock`：审计工具及其依赖。
- `requirements-docs.lock`：离线 HTML 手册生成器所用 markdown-it-py；运行程序不需要。

这些文件针对本版 **CPython 3.14 / Windows x64** 的确切 wheel。每项同时锁版本和 SHA256，使用 `--require-hashes --only-binary=:all:`。其他 Python 小版本、ARM64 或平台不可照搬该锁文件。`requirements.txt` 只引用运行时锁文件。更新依赖需更新锁、许可、清单并重新测试，不应删除哈希来绕过安装失败。

## 从源码构建

1. 使用 [Python 3.14.10 官方 x64 安装包](https://www.python.org/downloads/release/python-31410/)，启用 Tcl/Tk 和 pip。已验证安装包 SHA256：`92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965`。开发时可使用独立 runtime，不修改已有 Conda 或 PATH；下例假设已放入 `vendor/python`，否则将 `$pythonExe` 设为实际安装路径。
2. 准备 Visual Studio 2022 Build Tools 的 x64 C++ 工具和 Windows SDK。`native/build.ps1` 自动定位工具；可选 `tools/setup_compiler.ps1` 会修改当前用户 PATH/INCLUDE/LIB，只有开发者明确执行才生效。
3. 在版本根目录执行以下命令；`$pythonExe` 指向所选的官方 Python。使用完整路径时无需全局 PATH。

```powershell
$pythonExe = (Resolve-Path '.\vendor\python\python.exe').Path
& $pythonExe -m pip install --require-hashes --only-binary=:all: -r requirements-runtime.lock -r requirements-build.lock -r requirements-test.lock
& $pythonExe -m pip install --require-hashes --only-binary=:all: --no-deps --target vendor/ocr -r requirements-ocr.lock
& .\native\build.ps1
& $pythonExe -m pytest -q
& $pythonExe main.py --self-test
& .\tools\package.ps1 -Python $pythonExe
```

源码 ZIP 不重复分发 3rd-party wheel 或 OCR 模型。日语/英语模型来自 [tessdata_fast 官方仓库](https://github.com/tesseract-ocr/tessdata_fast)，放入 `models/tessdata`；本版精确模型哈希在 `DEPENDENCY_MANIFEST.json` 中。可从本版已校验的程序 ZIP 提取相同模型与其 LICENSE。打包前检查模型 SHA256，避免同名文件被替换。

`package.ps1` 不联网安装，不触碰私有配置；构建环境版本与清单不符时失败。完整构建更新 EXE 内的 Python 代码；`-SkipBuild` 仅适用于已完成构建后的公开文档/清单刷新，不能把源代码变化补进旧 EXE。

## 安全更新与审计范围

0.01.11 已从 Python 3.13.5、Pillow 11.1.0 更新到上述版本；0.01.20 沿用这一依赖基线。[Python 3.14.10 公告](https://www.python.org/downloads/release/python-31410/) 涵盖证书信任等安全修复；[Pillow 的 JPEG2000 公告](https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8) 和 [TIFF/EXIF 公告](https://github.com/python-pillow/Pillow/security/advisories/GHSA-wqgw-9xfh-qf2g) 标明修复版本为 13.0.0。程序仍限制实际可解码格式，升级依赖不能代替输入边界检查。

2026-11-14 对运行、OCR 和打包锁文件执行 pip-audit，未发现该查询所覆盖的 Python 包版本的已知漏洞记录。原始结果见发行的 `DEPENDENCY_AUDIT.json`；此结论不涵盖所有 C/C++ 库、未知漏洞、操作系统和用户的 API 服务商。

**原生依赖的剩余核验项：** tesserocr wheel 的版本信息仍报告 OpenJPEG 2.5.4。不能仅凭该字符串确认其是否包含上游补丁。本应用不把文件交给 Leptonica 通用格式探测：OCR 助手只接受受限 BMP，经 Pillow 明确 BMP 白名单解码，再用 `SetImageBytes` 传原始 RGB。回归测试禁止 `SetImage`/`SetImageFile` 路径，并拒绝伪后缀图片。该限制缩小本程序的可达路径，不是给 OpenJPEG 二进制出具无漏洞证明；二次开发若开放新格式，应重新审计。

## 清单与重现

`tools/dependency_manifest.py` 可根据 pip 的 `--report` 安装记录生成版本/哈希锁；现有公开锁文件已经生成，正常构建不必重新生成。`tools/package.ps1` 创建软件物料清单、文件 SHA256 和两个独立 ZIP。`tools/verify_release.py` 验证包内容、哈希、私密文件排除及对应源码一致性。见 [发布验证](RELEASE.md)。

更新检查是开发时执行，程序运行时没有自动更新器、自动下载模型或遥测接口。依赖审计只查询包名称与版本，不发送用户译文、截图或密钥。

## 文档与演示工具

安装 `requirements-docs.lock` 后执行 `& .\vendor\python\python.exe tools/build_html_docs.py` 和 `& .\vendor\python\python.exe tools/build_english_docs.py`，可由 Markdown 与已审阅的 SVG 生成完整离线中文 `PROJECT_MANUAL.html` 和英文 `PROJECT_MANUAL.en.html`（各 18 章）。无需浏览器脚本或联网渲染器。

源码启动使用 `& .\vendor\python\python.exe main.py`，自检使用 `& .\vendor\python\python.exe main.py --self-test`，测试使用 `& .\vendor\python\python.exe -m pytest`。这些 PowerShell 命令从版本根目录运行。不要用裸 `python` 命令：它可能指向已有 Anaconda 或其他 Python 小版本，而本版便携 OCR wheel 绑定 CPython 3.14 x64。若源码提示 `Portable OCR helper failed`，先确认实际解释器版本与路径，再检查模型和其他诊断；发行 EXE 自带运行时，不受系统 PATH 中 Python 的影响。

可选 `vendor/python/python.exe tools/record_demo.py --frames-only` 验证实际 Tk 界面并保存 PNG 帧；`--ffmpeg <本机编码器路径>` 另可使用外部 FFmpeg 的 Windows Media Foundation H.264 编码器生成 MP4。画面明确标注“模拟 AI 流式响应”：通过 httpx MockTransport 返回 SSE，实际网络请求为零，不代表真实游戏翻译质量或速度。临时假密钥与协议记录不会修改真实配置。FFmpeg 不随程序或源码 ZIP 分发，也不是翻译运行依赖。

0.01.20 字体选择只引用本机安装字体，不增加字体文件依赖，不分发 Microsoft 字体。

0.01.20 的可选图片识别复用 Pillow/HTTPX，不增加本地神经模型或额外云 SDK。本版重建原生 DLL 以修正混排换行；保留 gl_ocr_bgra，加载时与 gl_set_font 一起检查，保持 ABI 2/56 字节结构。

0.01.20 无上限选项仅改变 Python 请求次数策略，不增加依赖或改变原生 ABI。

0.01.20 的 `ocr_quality.py` 仅使用 Python 标准库进行有界本地规则匹配；不新增词库下载、神经模型、联网校验或原生 ABI。


## 0.01.20 依赖变更范围

本版新增背景修补、OCR细化和压缩语境功能复用现有 C++/Pillow/SQLite/zlib，没有新增依赖或改变锁文件。当前漏洞查询证据沿用已保存报告，不表示本次重新联网查询漏洞数据库。打包校验和本版测试状态分别以发布报告和 TEST_REPORT.json 为准。

## 0.01.20 · 截图与字号 · 2026-11-17

在“设置 → 译文外观”可调整以下项目，保存后停止并重新开始翻译生效。

| 设置键 | 默认值 | 规则 |
|---|---|---|
| `capture_translations` | true | 桌面截图/录屏包含译文；关闭后通过 Windows 捕获排除保留原游戏画面 |
| `auto_font_size` | true | 参考原文字高，在允许范围内寻找合适字号，同一流式对象只保持或缩小 |
| `overlay_font_size` | 24 | 关闭自动调整时的固定字号，8–512 物理像素 |
| `overlay_font_min` | 8 | 自动字号下限，8–512 |
| `overlay_font_max` | 72 | 自动字号上限，8–512，必须不小于下限 |

字号使用像素而非排版点数。固定字号不缩小；自动模式达到下限仍放不下时保留原文。维持原文字框和物理行，完成时调整字距，不把内容画到相邻框。

包含译文时，OCR 改用 Windows Graphics Capture 直接采集已选游戏 HWND 的原始画面，译文覆盖窗口不进入 OCR，不隐藏覆盖层、不逐帧切换捕获标志。游戏内截图或仅采集游戏 HWND 的录制器可能仍只有原文；若要拍到译文，请用桌面截图/显示器录制。Windows 可能显示系统采集边框。采集不可用时显示错误，可关闭该选项使用原有桌面采集；不会默默采集译文递归翻译。

API 配置中，已存密钥用固定 12 个圆点表示，聚焦也保留；圆点只存在于标签，不是输入值，不解密回填。输入新值、切换到空槽位、变更地址或勾选清除时隐藏；同地址空输入保存仍保留原加密密钥。

新增 `NativeCore.set_overlay_options(*, auto_font_size=True, overlay_font_size=24, overlay_font_min=8, overlay_font_max=72, capture_translations=True)`，由 `OcrCore` / `VisionCore` 转发。C 导出 `int gl_overlay_options(void*, int automatic, int size, int minimum, int maximum, int screenshots)`；布尔仅 0/1，字号 8–512、下限≤上限，失败返回 0 且不修改状态。相同配置不重排，新配置异步重新拟合。ABI 仍为 2，Python 同时校验新导出。原生诊断未绑定游戏时仍排除截图。`gl_hide` 和重新绑定关闭窗口采集会话。

新增 `native/window_capture.h`：C++/WinRT + Direct3D 11，硬件设备失败时尝试系统 WARP；固定 BGRA 格式，最多 2 个帧池缓冲，窗口≤8192/轴且≤16777216像素，输出区域≤4096/轴。按 DWM 物理边界裁切，不接受比例不匹配；尺寸变化时丢弃旧帧并重建。没有新增第三方包，不申请无边框捕获权限、不更改系统隐私设置。

实现参考：[Windows Graphics Capture](https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture)、[SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)。
