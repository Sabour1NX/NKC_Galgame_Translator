# libiconv / libcharset 对应源码与构建资料

本目录随二色蝶 0.01.11 的程序包和源码包提供 GNU libiconv **1.18** 的完整上游源码，以及 OCR wheel 中动态库对应的 conda-forge **`libiconv-1.18-hc1393d2_3`（win-64）** 构建配方与补丁。库采用 LGPL-2.1-only（见该包的 `info/recipe/meta.yaml` 和完整 `COPYING.LIB`）。完整上游源码还含 GPL 许可的独立工具和构建材料，其原有 `COPYING` 等声明保持不变。

## 文件与核验

- `libiconv-1.18.tar.gz`：GNU 官方完整源码，SHA256 `3b08f5f4f9b4eb82f151a7040bfd6fe6c6fb922efe4b1659c66ea933276965e8`，与准确二进制包内配方声明一致。
- `info/recipe/`：从经 SHA256 核验的 conda 二进制包中原样取出的配方、Windows CMake/配置补丁、安装脚本及脚本许可证。
- `info/index.json`、`info/hash_input.json`：该构建的版本/依赖元数据。
- `provenance.json`：下载 URL、原始包及源包哈希、发布 DLL 的哈希和代码段比对结果。
- `binary-match-candidates.json`：四个官方 win-64 1.18 构建的对照；只有构建 `_3` 与本 wheel 的 iconv 代码/展开/重定位段一致。配套 charset DLL 也已单独比对一致。
- `tesserocr-v2.13.0-build.yml` 和 `tesserocr-v2.13.0-windows-install-tesseract.ps1`：该版本官方构建过程，作为独立 OCR wheel 来源说明，未在本次审计中执行。

wheel 的 delvewheel 打包过程重命名 DLL 及导入引用，所以整文件哈希与 conda 原始 DLL 不同；本目录分别记录两者，不声称位元相同。相同的 `.text`、`.pdata`、`.reloc` 段及相同导出版本用于确认来源。

## 重建与替换

1. 解压上游 tar.gz，保留其全部许可及版权文件。
2. 按 `info/recipe/meta.yaml` 的 Windows 顺序应用 `info/recipe/parent/` 中 `CMakeLists.txt.patch`、`config.h.patch`、`configure.cmake.patch`。
3. 该配方使用 MSVC、CMake `<4` 和 Ninja；精确构建/主机依赖及版本已保存在渲染后的 `meta.yaml`。按原始 `bld.bat`/`install.bat` 和配方执行构建、测试与安装，路径和构建环境按本机调整。本目录提供源码与配方，本项目没有重新编译并验收这个上游库。
4. OCR 程序使用独立、可替换的动态 DLL；不使用它们执行游戏注入。修改版本应保持对应 ABI/导出，按原 wheel 的打包步骤处理依赖名，或重新构建 OCR helper。完整项目中有 `tools/ocr_helper.py` 及打包脚本。替换前备份，停止翻译并关闭程序；修改后的二进制不再与本发行 SHA256 清单相同。

本软件协议不限制 LGPL 授予的修改、再分发及为调试这些修改进行逆向工程的权利。请遵守该库自身许可；本目录不把第三方库或其上游工具重新标记为主程序的 GPL-2.0-only，也不承诺所有派生组合自动兼容。
