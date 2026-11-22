# 1.01.12

Mixed-color dialogue keeps its full source bounds during background reconstruction.

# 1.01.11

光标所指的漏译行可以独立复查和优先翻译。CUDA OCR 在输入尺寸持续下降时回收闲置显存；翻译档案按游戏累计统计，流式显示会合并已过时的中间结果。

# 1.01.10

矢量山峰按屏幕间距保留已显示的山脊。新山脊与已有山脊过近时，整条省略，包括分叉和三角连线。

# 1.01.09

「矢量山峰 (beta)」仅为 CPU／GPU 利用率绘制山脊。接地线、分叉和三角连线均限制在利用率折线下方。内存和显存用量始终以普通折线显示，包括使用自定义线色时。

# 1.01.08

所有主题首次使用普通折线，可在设置中按主题开启几何山体。中文欢迎页更名为 Greeting_cn.html，首屏文案更新为「放下词典，回到故事里。」新增三语 GitHub 入门指南和独立的初始化体验入口 Preview-Setup.cmd。

# NKC_Galgame_Translator 1.01.07

英文和日文界面、安装提示及五页导览已更新。使用「设置」中的手册入口可打开对应语言的操作指南。

[English](PROJECT_MANUAL.en.html) · [日本語（Beta）](PROJECT_MANUAL.ja.html)

# 1.01.07

Windows x64 安装包为 `NKC_Galgame_Translator-1.01.07-setup.exe`。设置页支持按主题调整两条资源线的颜色和样式，OCR 预热期间连续采样。底部显示翻译使用的模型，后端请求失败时显示错误码。

# 1.00.01

运行 NKC_Galgame_Translator-1.00.01-setup.exe 安装 Windows x64 客户版。安装语言将在程序首次启动时沿用。安装成功后，浏览器打开 [中文](Greeting_cn.html)、[English](Greeting.en.html) 或 [日本語（Beta）](Greeting.ja.html) 介绍页。

程序安装到当前用户的 LocalAppData/Programs/Nishokuchou/1.00.01，提供程序启动按钮和独立的 SHA-256 校验文件。公开安装包和免安装包使用同一份验证后的发行内容。

# 0.01.30

[新版项目手册](PROJECT_MANUAL.html) · [性能报告](PERFORMANCE_REPORT.html) · [任务报告](TASK_REPORT.html)
