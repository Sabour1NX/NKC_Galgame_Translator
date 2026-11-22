# 二色蝶 0.01.27 · 性能与识别报告

**品质的体验，更少的等待**

固定基线 **0.01.15**，当前 **0.01.27**。本次测量 2026-11-18T18:29:09+0800。以下是图片进入 OcrCore 到本地识别结果，**不是翻译端到端延迟**。

## 范围与方法

3轮交替版本顺序，每个场景/版本独立worker，共3个冷样本、每条热路径15个样本。冷启动含构造、原生/helper/模型初始化；不含Python启动和原图读取，未清空OS文件缓存。背景变化只改变角落1像素、正文不变：整帧缓存断言未命中，但允许局部缓存。原图复访另列，不能视为新文本识别。

实际auto产品路径：.15默认CPU路由；.27启用CUDA、质量75、预算1024MiB，经典英语像素画面优先CPU。这是系统对照，不能解释为相同算法的纯GPU加速。测试期间有并行UI截图负载；保留NEEDY冷启动最大21.886秒，不臆断原因。

| Scene | Version / backend | Cold median ms | Changed-background median ms | Identical revisit ms | Character accuracy |
|---|---|---:|---:|---:|---:|
| spacerogue-game.png | 0.01.15 / portable-tesseract-pixel | 615.119 | 321.146 | 327.417 | 98.347% |
| spacerogue-game.png | 0.01.27 / portable-tesseract-pixel | 654.230 | 317.192 | 7.716 | 98.347% |
| status.png | 0.01.15 / windows-ocr | 40.032 | 23.722 | 23.721 | 40.625% |
| status.png | 0.01.27 / portable-tesseract-pixel | 546.764 | 205.891 | 7.504 | 100.000% |
| cargo.png | 0.01.15 / portable-tesseract-pixel | 338.523 | 123.446 | 123.027 | 47.561% |
| cargo.png | 0.01.27 / portable-tesseract-pixel | 451.943 | 123.234 | 2.561 | 85.366% |
| needy-caution-full.png | 0.01.15 / portable-tesseract | 517.906 | 257.437 | 257.287 | 1.613% |
| needy-caution-full.png | 0.01.27 / rapidocr-cuda | 3286.928 | 226.868 | 20.321 | 98.387% |

## 精度与取舍

准确率=100×（1−Levenshtein编辑差异/标注字符数），做NFKC、去空白和弯引号规范化，区分大小写；评价原文转录，不评价翻译语义。Space Rogue共356字：默认auto 81.461%→95.506%；另列.15强制pixel为83.989%。NEEDY248字：.15 auto 1.613%，.27关闭CUDA对照57.661%，.27 CUDA auto 98.387%。.15 Windows日语OCR因缺语言功能失败，失败不记作零准确率。

更准确的路径可能更慢：Status背景变化中位由23.722增至205.891ms，CUDA首次初始化也更慢；故事场景精度仍为98.347%。缓存收益和某一质量档位不能代表所有新文本速度或准确率。

## 真实API回调与未测显示环节

离线OCR对照API请求为0，不含捕获、云端精读、翻译、SSE和显示。新真实API观测独立注明范围，不用历史.25数据或模拟SSE填补。

计时前载入完整Space Rogue原图，先经过各版本实际Pixel OCR；测试适配层随后只选取左侧剧情region[0,70,450,440]进入追踪和真实流式API。原图没有裁切。起点为pipeline.start之前，终点为译文回调被事件队列消费。不显示窗口或叠层，不含捕获、绘制、联网语境、AI图像精读、DWM或显示器呈现。原生绘制时间为null未测，不能记为零。

| Pair | Version | Result | First callback ms | Final callback ms | Requests |
|---|---|---|---:|---:|---:|
| 1 | 0.01.15 | complete | 2179.033 | 2561.680 | 1 |
| 1 | 0.01.27 | complete | 1202.929 | 1618.103 | 1 |
| 2 | 0.01.27 | complete | 1308.167 | 1689.562 | 1 |
| 2 | 0.01.15 | complete | 1628.940 | 2011.547 | 1 |
| 3 | 0.01.15 | complete | 1529.235 | 1863.335 | 1 |
| 3 | 0.01.27 | complete | 1489.160 | 1982.674 | 1 |

保留两版默认稳定等待与轮询设置；观察tick为.15的40ms、.27的16ms，提示也不同（输入token229/258）。顺序网络/服务商波动未受控，少量配对只描述本组观测，不构成统计确立的服务商加速。第3对新版完整回调更慢：1982.674ms，对照版1863.335ms。这是固定图片真实API回调测试，不是原生绘制或运行中游戏覆盖认证。

| Version | Poll interval ms | Settle ms | Observation tick ms | Model |
|---|---:|---:|---:|---|
| 0.01.15 | 250 | 450 | 40 | deepseek-flash |
| 0.01.27 | 50 | 80 | 16 | deepseek-flash |

本组实际会话请求数：6.

6个样本的源文字串SHA一致。服务商/模型输出波动与版本提示差异仍然属于本次系统级观测的一部分。

| Pair / version | Prompt tokens | Completion tokens |
|---|---:|---:|
| 1 / 0.01.15 | 229 | 39 |
| 1 / 0.01.27 | 258 | 39 |
| 2 / 0.01.27 | 258 | 39 |
| 2 / 0.01.15 | 229 | 39 |
| 3 / 0.01.15 | 229 | 39 |
| 3 / 0.01.27 | 258 | 34 |


## GPU控件与边界

质量0–100（默认75）设检测分辨率上限、按32像素量化；小图可能等效，精度不保证单调。显存256–16384MiB（默认1024）是检测/识别arena预算，不能约束进程/驱动全部分配。Auto支持CUDA en/ja/zh但经典英语像素画面优先CPU；Windows/Pixel模式走CPU。模型分数95不是实测准确率95%。

[完整图表、分布与同图识别证据](PERFORMANCE_REPORT.html)

[评审入口：手册、结构、完整UI图库](teacher-review27/index.html)
