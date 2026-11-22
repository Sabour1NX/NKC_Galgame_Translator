# 用户条款

NKC_Galgame_Translator · 1.01.12

## 1. 同意与软件许可
首次使用或条款更新后，请阅读并确认。程序在本机记录已确认的版本和时间。二色蝶自有代码使用 MIT 许可证，允许按许可使用、修改和分发，包括商用。本条款说明软件行为和数据处理，不改变 MIT 或第三方许可证授予的权利。发行目录中的 LICENSE 收录 MIT 原文。

## 2. 画面识别与覆盖
程序采集你选定的游戏窗口或区域，识别文字并在原位显示译文。程序不修改游戏文件，也不向游戏进程注入代码或读写游戏内存。OCR、位置和译文可能有误，请以原文为准。停止翻译或退出程序即可关闭覆盖。

## 3. API 请求与费用
新译文由你配置的 API 生成。请求可能包含原文、语向、备注、已有摘要和相关历史。启用后端图片识别时，选定区域的图片也会发送给当前服务商。开启联网语境研究或自动摘要时，软件可发出额外请求。服务商按自己的条款处理请求并可能计费，应用内的请求次数上限不等于费用上限。

## 4. 本机数据与密钥
译文、上下文档案、备注和摘要保存在本机。启用汉化组工具后，指定目录还会保存游戏截图和译文。压缩只节省空间。API 密钥由当前 Windows 用户的 DPAPI 加密保存，调用接口时才解密供认证使用。软件不内置使用行为统计。

## 5. 第三方组件
CPython 和 Tcl/Tk 负责程序运行及界面。Pillow 处理截图和像素。tesserocr、Tesseract 及其模型用于英语、日语等文字的本地识别，Leptonica 提供 OCR 图像预处理。可选 CUDA 扩展使用 RapidOCR 和 ONNX Runtime GPU 运行本地识别模型，并依赖 NVIDIA CUDA 与 cuDNN。HTTPX、httpcore、OpenSSL 和 certifi 负责接口通信及证书验证。SQLite 和 zlib 保存及压缩档案。思源黑体用于界面和欢迎页，PyInstaller 用于打包。全部许可和上游声明见 THIRD_PARTY_NOTICES.md 及 licenses 目录。

## 6. 使用范围与责任
请仅处理你有权使用的游戏、画面与文本。软件按 MIT 许可证现状提供，适用法律不得排除的权利和责任仍然有效。

## MIT 许可证

Copyright (c) 2026 NKC_Galgame_Translator contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
