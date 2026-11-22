# NKC_Galgame_Translator 1.01.12

英文和日文界面、安装提示及五页导览已更新。使用「设置」中的手册入口可打开对应语言的操作指南。

[English](PROJECT_MANUAL.en.html) · [日本語（Beta）](PROJECT_MANUAL.ja.html)

# 0.01.30 文档入口

- [操作与工程手册](PROJECT_MANUAL.html)
- [English guide](PROJECT_MANUAL.en.html)
- [CUDA 开关实测](PERFORMANCE_REPORT.html)
- [任务报告](TASK_REPORT.html)
- [接口规范](INPUT_INTERFACES.md)
- [依赖清单](DEPENDENCY_MANIFEST.json)

下文为历史文档索引。

# 文档目录 · 0.01.27

0.01.27 加入可选 CUDA OCR、后台联网语境与整组字号修复。本版新增同图 OCR 评审，对照 0.01.15，分别报告冷启动、背景变化热路径、复访缓存和逐字精度；真实 API 链路另列。历史证据保留原版本标签，当前方法与范围见性能报告及 TEST_REPORT.json。

更新：2026-11-18。当前资料全部对应0.01.27；带0.01.22文件名的性能报告为原始历史资料，不替代随本版提供的0.01.15→0.01.25历史实测；0.01.27调度模拟单列。

| 用途 | 中文 | English |
|---|---|---|
| 客户使用 | [客户手册](CUSTOMER_GUIDE.html) | [User guide](CUSTOMER_GUIDE.en.html) |
| 完整项目 | [完整HTML手册](PROJECT_MANUAL.html) | [Complete manual](PROJECT_MANUAL.en.html) |
| 性能与原图 | [性能报告](PERFORMANCE_REPORT.html) | [Performance](PERFORMANCE_REPORT.en.html) |
| 结构与流程 | [可视化总览](PROJECT_GUIDE.html) | [Diagrams](PROJECT_MANUAL.en.html#visual) |
| 接口与边界 | [API](API.md)、[输入](INPUT_INTERFACES.md)、[UI](UI_INTERFACES.md) | [API](en/API.md)、[Input](en/INPUT_INTERFACES.md)、[UI](en/UI_INTERFACES.md) |
| 上下文与显示层 | [联网理解与分层](CONTEXT_AGENT.md) | [Context and display](en/CONTEXT_AGENT.md) |
| 依赖与发布 | [依赖](DEPENDENCIES.md)、[发布](RELEASE.md) | [Dependencies](en/DEPENDENCIES.md)、[Release](en/RELEASE.md) |
| 协议 | [中文](USER_AGREEMENT.md)、[日本語](USER_AGREEMENT.ja.md) | [English](USER_AGREEMENT.en.md) |
| 实测与验收 | [测量JSON](PERFORMANCE_REPORT.json)、[测试JSON](TEST_REPORT.json) | Same machine-readable data |

公开资料在delivery/customer，源码与程序包在delivery/release。开发目录config及demo/NeedyGirlOverdose的配置和历史属于私人资料。当前用户条款见 USER_AGREEMENT.md。
