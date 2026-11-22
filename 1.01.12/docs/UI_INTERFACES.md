# 界面接口与状态契约 · 0.01.27

## 0.01.27 CUDA 运行时与预热契约

当前可选组件锁定 ONNX Runtime GPU 1.32.0、RapidOCR 3.10.0、CUDA 13.x runtime / cuDNN 9.x。本机 RTX 3070 / 驱动 617.42 已验证；其他组合不能据此视为兼容。模型与轮子 SHA 固定；provider arena 预算拆分为检测/识别两部分，默认合计 1 GiB，另有驱动和运行库内存。

`OcrCore(..., cuda_enabled=False, cuda_memory_mb=1024, cuda_quality=75, cuda_instance=None)` 保持底层调用默认不启用的兼容行为；App 按用户配置默认启用，并可交接已经预热的 `CudaOcr` 实例。`App._prepare_cuda()` 的后台线程只调用本地 `warmup()`，不采屏或请求 API；同 helper 可供后续 OCR 复用。预热不保证每个新图像形状没有首次推理开销。

## 0.01.27 CUDA 识别与实际回退

首次语言设置和常规设置共用 CUDA 控件。`cuda_enabled` 默认开启；只在 OCR **自动模式**且源语言为英语、日语或中文时尝试 CUDA。手动 Windows / Pixel 模式明确走 CPU；自动模式检测到经典英语像素画面且便携识别可用时优先 CPU Pixel 路径（`pixel_priority`）；其他语言继续使用已有本地识别。组件缺失、无兼容 GPU、模型校验或推理失败时回退 Windows / Tesseract，并显示实际状态，不能把“文件已安装”当作“CUDA 已运行”。失败后的当前 OCR 实例不反复重试 GPU，修改设置后停止并重新开始。

| 设置 | 默认 | 范围与作用 |
|---|---|---|
| `cuda_enabled` | `true` | 开关；不自动下载或安装组件 |
| `cuda_quality` | `75` | 0–100，高性能到高精度；线性调节检测长边，按 32 像素量化 |
| `cuda_memory_mb` | `1024` | 256–16384 MiB；推理内存 arena 预算，不会强行占满 1 GiB，运行库和驱动另有开销 |

检测长边约为 `768 + 11.52 × cuda_quality` 后按 32 像素量化；75 对应 1632 像素。仅缩小超出上限的图像，小图在不同档位可能等效；数值不是准确率百分比，也不保证单调提速或提高精度。CUDA 模型为 PP-OCRv6-small，GPU/依赖验证结果以本版报告为准，不提前声称所有 NVIDIA 显卡可用。

启用可选云端 AI 图像精读时，CUDA 已输出的行仅在置信度不低于 95 且没有拒绝标记时直接送译，其余仍走核验路径。**95 是模型分数门槛，不是 95% 实测准确率承诺**。CUDA 本地 OCR 不上传图片；云端精读仍遵循独立开关和图片发送规则。

## 0.01.27 窗口身份与运行状态

`window_metadata(hwnd, paths=None)` 返回 `hwnd,pid,title,process_path,exe_name,class_name`；刷新列表时按 PID 共享进程路径查询。`translation_target(row)` 是基于元数据的目标筛选，不按游戏名或引擎白名单判断。资源管理器、桌面、任务栏、系统辅助进程/窗口类及本程序覆盖层不作为候选。列表显示“标题 · 可执行文件名 · PID”。

`App.chosen_window()` 选择时重新读取元数据并检查 HWND/PID，拒绝过期身份和系统辅助窗口。`window_state(hwnd, expected_pid)` 返回 `closed / replaced / minimized / hidden / background / active`；此查询不打开进程。`App._refresh_running_status()` 最多每秒刷新一次，结合目标状态和管线事件区分等待、识别、未找到文字、AI 请求与已显示译文；实际错误保持锁存直到停止或重启。状态文本不是翻译完成证据：后台、最小化或不可见选区不会继续截图翻译。源/目标语言、1–8 选区、截图选项、字体与字距行为不变。


0.01.27 加入可选 CUDA OCR、后台联网语境与整组字号修复。本版新增同图 OCR 评审，对照 0.01.15，分别报告冷启动、背景变化热路径、复访缓存和逐字精度；真实 API 链路另列。历史证据保留原版本标签，当前方法与范围见性能报告及 TEST_REPORT.json。

## 0.01.27 上下文边界

可选上下文层只声明 DeepSeek 服务端联网搜索工具，之后的纯译文请求不声明工具。两层共用额度、并发与 Token 统计。游戏文字、历史、网页与摘要都是不可信参考，客户端不自动访问返回 URL、不执行函数或命令，也不让模型改变本地原文坐标。精确请求、元数据、超时与缓存契约见 [CONTEXT_AGENT.md](CONTEXT_AGENT.md)。

适用版本：0.01.27 · 文档复核：2026-11-18。历史记录保留原版号。

## 多区域与自动字体

在屏幕翻译页选择游戏窗口，点击“框选区域”。连续拖动添加 **1–8 个不重叠矩形**；按 **Enter 确认**，按退格或右键撤销最后一个，Esc 取消并保留原选择。每框至少 20 × 20 像素；合并外接矩形每轴不超过 4096 像素。请把一整段文字留在同一框内，并留少量边距。区域随游戏客户区移动，缩放后裁到客户区；更换游戏窗口后恢复整个客户区。选区仅在本次界面会话保留。

多个选区使用同一帧捕获，框外间隙先遮成黑色再进入 OCR 或可选 AI 图像精读；语句团和对象关联不跨选区。框选不同区域不会分别启动多个 OCR 进程，也不改变翻译并发上限。全屏游戏建议切换窗口模式。

打开“设置 → 译文外观 → 按原文自动选择相似风格字体（支持目标语言）”，保存后重新开始翻译。程序根据原文字形近似选择像素、衬线、无衬线或等宽风格，并逐框检查字体是否支持目标语言与当前译文字形。无需下载字体。默认关闭，关闭时仍使用手动字体。自动字号及上下限独立设置，过长译文继续在允许范围内缩小。

字体匹配不等于还原游戏字体；装饰字、复杂背景、短词和误识别可能影响风格判断。字形不全时改用已安装且覆盖译文的后备字体；没有合适字体时保留原文。当前自动覆盖检查保守支持 BMP 字符；含补充平面字符或 emoji 的该框保留原文，可切回手动字体使用 Windows 字体回退。

状态字段：`capture_region` 保存矩形元组；`capture_region_target` 保存 HWND/PID。Esc 不写入状态，Enter 原子提交；切换目标后清除旧选区。

全部 Tk 控件操作在主线程进行。模块路径保持 `nkc_galgame_translator`；这是发行程序内部接口，未承诺跨版本兼容。本文不包含本机密钥或私人路径。

## App

`App(*, show_setup=True)` 创建五页主窗口、配置存储器、普通事件队列和显示状态。`show_setup=False` 仅禁止自动引导窗口，不跳过协议确认，也不启用缺失的密钥；用于诊断和测试。

| 方法 | 参数与返回 | 前置条件、状态变化和失败 |
|---|---|---|
| `show_api_settings()` | 无参数，返回 `ApiSettingsDialog` 或 `None` | 协议未确认时转到协议页；忙时返回 `None`。已有窗口直接复用，不重复创建。 |
| `save_api_settings(base_url, model, *, api_key=None, offline_only=False, slot=None)` | 返回持久化后运行时配置；其中只有当前槽位含解密密钥，不应打印 | 主线程，协议已确认且空闲。slot 为 0–2，None 使用当前索引。调用纯验证函数及 ConfigStore 后，才关闭旧引擎并替换运行时状态。失败不替换现有引擎或 UI 配置。 |
| `save_settings(values=None)` | 成功 `True`，失败 `False` | None 从设置控件取值，dict 作为部分更新。先与当前配置合并，严格验证，持久化成功后按需重建引擎；仅外观变化保留引擎和请求额度。软件语言立即刷新界面。OCR 阈值变化时关闭旧 OCR，下次开始重建。失败原因留在设置页。 |
| `refresh_windows()` | 无返回值 | 新建窗口信息快照；仅保留仍相同 HWND 和 PID 的明确选择。首次不按游戏名或标题自动选窗。 |
| `chosen_window()` | 返回选中窗口信息 dict | 没有选择时抛 `UIValidationError`，不猜测前台或列表第一项。 |
| `term_scope()` | `(game, source_language, target_language)` | 游戏去除首尾空白；语言由有限 UI 语言表映射。留空档案与共享词典不同。 |
| `open_dictionary_import()` | `DictionaryImportDialog` 或 `None` | 忙时返回 None；已有导入窗口复用。创建窗口不自动打开文件选择器。 |
| `manual_translate()` | 无返回值；异步结果经事件队列 | 协议、忙状态、空文本、输入长度、同语言、语境长度先校验。超长输入在创建引擎前拒绝。工作线程进行本地解释及翻译，不访问 Tk。 |
| `stop()` | 无返回值 | 停止屏幕流水线、隐藏覆盖、清显示状态。已经发送的网络请求可能继续至返回/超时，不能据此认为请求全部结束。 |
| `close()` | 无返回值 | 导入进行中时每 100ms 等待其完成后关闭；随后关闭引擎、原生上下文和窗口。不是强杀整个游戏进程。 |
| `drain()` | 无返回值；默认每 40ms | 每次最多处理 256 个事件，再按前台状态绘制。检查屏幕事件的会话、对象和修订。 |
| `settings_error_message(error)` | 最多 500 字符的可显示字符串 | 只透传受控 `ConfigStoreError`、`UIValidationError`、`TuningValidationError`、`SecurityValidationError`、`TranslationError`；其他异常返回固定诊断，不回显 `str(error)`。 |

API 地址、模型及密钥验证由 `nkc_galgame_translator.security` 统一负责。UI 地址首尾普通空格会去除，其他控制字符由验证器拒绝。密钥 `None` 表示保留，空字符串表示清除；改变规范化地址且传入 `None` 时，UI 拒绝自动沿用旧密钥。普通界面不暴露后端显式重用密钥选项。

## 手动翻译流与控件

`manual_input` 为 Tk Text；`manual_count` 为 StringVar。有效字符上限来自 `max_input_chars`，限制在 64–16000，界面显示计数并支持 Ctrl+Enter。忙期间输入控件 disabled；原文和语境校验通过后才获取引擎。空白、超过输入上限、相同语向或超过 2000 字符的语境均不创建请求。

工作线程调用 `_post_manual(text)`：将最多 64000 字符的累计全文放入受锁保护的一个槽位；只有尚未排队时才投递 `('manual', 0, None)` 标记。后续片段替换槽位，避免慢 UI 积压每个累计副本。UI 消费标记时调用 `_take_manual()`，取走最新值并复位标志。该上限与引擎输出约束独立，是显示层防护；不是绕过引擎文本校验的方法。

`_set_manual_output(text)` 只在主线程暂时启用输出 Text、替换有界文本，再设为 disabled。译文可选中复制，不能在控件中改写。模型返回的 HTML、脚本、命令和链接只是 Text 字符，不自动渲染网页、打开链接或执行。

手动事件仍使用 `(kind, generation, payload)`：`manual` 是结果刷新，`manual_status` 是受控完成说明，`manual_done` 解除忙状态；手动 generation 固定为 0，一次只允许一个手动任务。普通屏幕事件的 generation 语义见主 [API.md](API.md)。

## ApiSettingsDialog

构造函数 `ApiSettingsDialog(app)` 创建三槽位编辑窗口，不主动发送请求。`select_slot(index)->bool` 仅接受整数 0–2；忙时拒绝。切换前 `_stash()` 将当前 `(endpoint, model, typed_key, clear_flag)` 保留在窗口内存，`_load_slot()` 恢复所选草稿；已存密钥不进入输入框或草稿。

`save_online()->bool` 调用 App 保存接口。成功只清除当前已保存草稿；其他槽还有未保存草稿时继续显示窗口并提示，否则关闭。`use_offline()->bool` 保留旧方法名，按钮为“稍后配置，仅浏览资料”；不生成新译文，不提交在线表单草稿。失败由受控错误出口显示行内原因，不弹出额外确认框。

`_refresh_endpoint_hint()` 用规范化地址比较是否改变，改变时要求重新填写密钥。配置存在密文绑定/解密问题时，初始 `error` 使用 ConfigStore 的固定诊断；主窗口当前槽位标为“需重新配置”。

`close()` 清除 typed key 和全部草稿，释放当前窗口 grab 后销毁。忙时控件 disabled；关闭编辑窗口不自动保存其他槽位。

## SettingsPanel 与参数

`SettingsPanel(app, parent)` 生成数值控件、显示字体/软件语言选择以及布尔开关，`vars` 按配置键索引 Tk 变量。`values()->dict` 返回控件内容；数值为字符串、开关为 bool。`refresh(busy)` 禁用或启用所有编辑控件与保存按钮。

`validate_tuning(values)->dict` 不做 I/O，仅返回受管理字段。要求 dict；缺项使用 `TUNING_DEFAULTS`。整数控件只接受真正 int 或最多 6 位十进制数字字符串，不接受 bool、浮点数、NaN 或无穷值；随后检查各自范围。布尔值必须为 bool，不做“非空即真”的转换。失败抛 `TuningValidationError(ValueError)`，诊断不包含被拒绝的原始值。`max_concurrency` 总是与 `translation_workers` 同步。范围表见 [LOCAL_TRANSLATION.md](LOCAL_TRANSLATION.md)。

## DictionaryImportDialog

| 方法 | 返回与作用 | 线程和约束 |
|---|---|---|
| `browse()` | 显式点击后调用文件选择器；不自动解析 | 主线程，忙时不执行 |
| `invalidate()` | 清除已解析 entries 和 preview_scope，禁用提交 | 路径或范围改变时调用，防止提交过期预览 |
| `preview()->bool` | 启动解析成功返回 True，否则 False | 固定本次 `(game,src,dst,shared)`；后台仅调用 parse_dictionary，结果经 `dictionary_result` 事件传回 |
| `commit()->bool` | 有预览时启动事务导入，成功启动为 True | 使用预览时固定的 entries 和范围、提交时的 replace 开关；调用前取得有效引擎，工作线程不读 Tk |
| `receive(payload)` | 消费 preview/import/error，更新主线程状态 | `preview` 显示前 5 条，每字段最多预览 200 字符；展示 Text 只读。`import` 显示 inserted/updated/skipped 并刷新列表 |
| `close()->bool` | 忙时 False 并提示等待，否则销毁且返回 True | 不在写入中关闭引擎，不中断 SQLite 事务；重复关闭幂等 |

后台结果载荷为 `('dictionary_result',0,(dialog,(kind,result,scope)))`。解析的 DictionaryImportError 和引擎的 TranslationError 使用受控诊断，其他异常固定化；不把文件正文或任意异常字段放进提示。导入期间 `App.import_busy=True`，模式、API 与参数编辑不可用。文件解析边界详见 [INPUT_INTERFACES.md](INPUT_INTERFACES.md)。

## 0.01.20 外观和界面语言

SettingsPanel 顶部提供 `font_box`（本机字体列表且可手输）、`preview_text/preview_hint/preview_label` 和 `update_preview()`。预览仅在本地格式化并绘制；字体先 strip，再验证非空、1–31 UTF-16 单元、无 Cc/Cf/Cs。`show_source_label/show_translation_brackets` 默认 true 且分别独立；`source_label_mixed_only` 默认 false，来源总开关关闭时其控件禁用。预览同时展示单语和混合语言结果，字号仍由原生层自动适配。失效字体可能由 Windows 回退。

App.start 在创建流水线前调用 `core.set_overlay_font()`，并传递三个显示布尔选项。只改显示选项不会关闭 TranslationEngine，也不重置 session request budget；全部保存仍须先停译并等待在途任务结束。新增显示选项不改原文、词典、语境或缓存键。source_lang/target_lang 从配置恢复并持久保存，兼容 zh-CN/TW 别名，与 app_language 独立。

首次语言选择器先于协议/API，以 Windows 用户显示语言预选 zh-CN/en/ja，不支持时 English；仅显式选择才写 app_language_selected。设置保存软件语言后立即刷新界面，无需重启，保留输入与数据；不自动确认协议或发 API。中文和英文完整手册独立离线可读，日文界面使用英文完整手册。英文协议常量 `AGREEMENT_TEXT_EN` 与 `get_agreement_text_en()` 提供完整英文免责声明和未经改写的 MIT 原文。

### 仅在同屏多种外文时标注

`show_source_label` 是总开关，`source_label_mixed_only` 是默认关闭的独立布尔子选项“仅在同屏出现多种外文时标注”。总开关关闭时子选项不可操作，译文不显示来源；总开关开启且子选项关闭时始终显示来源；二者都开启时，仅当前可见 OCR 对象包含至少两种外语才显示来源。按规范化语言基础代码去重，排除目标语言：`en-US/en` 同组，`zh-Hans/zh-CN` 同组。例如目标中文，只有英语时不标来源，同时英语与日语时标来源。实际识别结果决定计数，界面语言不参与。

对象出现、消失或场景变化会重新格式化已经累计的译文，不重新调用 LLM，不更改对象 ID、revision、词典或缓存。外侧方括号仍独立：关闭来源也可显示 `[译文]`。设置预览同时展示单语/混合示例，不联网。上表四种基本组合描述来源标签生效时的格式；mixed-only 决定来源标签何时生效。


## 本地界面语言接口（i18n.py）

以下方法只处理程序自有界面文案；游戏原文、译文、密钥、词典单元格不通过本地化器。无网络调用。

```python
detect_system_language(langid=None) -> str
initial_language(config, *, interactive=True) -> str
translate(value, language='zh-CN')
localize_widgets(root, language) -> None
agreement_text(language) -> str
class LanguageLabels(dict): ...
```

- `detect_system_language()` 调用 `GetUserDefaultUILanguage`，按主语言 ID 识别中文/英语/日语，不读取地区、键盘、IP 或网络；不支持、非 Windows、无效传入 ID 或系统调用不可用时返回 `en`。传入 int ID 用于无 UI 的确定性检查。
- `initial_language()` 在交互流程中仅在已支持的保存值且 `app_language_selected is True` 时优先采用保存值，否则用系统预选。`interactive=False` 的测试/非引导路径使用支持的保存值，否则 `zh-CN`；这不写设置或接受协议。
- `translate()` 在本地目录表中转换自有文案与带命名占位符的状态模板，替换不执行表达式；空值/非字符串原样返回，未知语言回到 `zh-CN`。不要把它作为通用游戏翻译接口。
- `localize_widgets()` 在 Tk 主线程刷新按钮、标签、页签、列标题及窗口标题，不修改 Entry、Text 正文或数据表内容。App 另行刷新受控状态变量与协议显示。
- `LanguageLabels` 的常规迭代保留稳定中文名称；`__getitem__/get` 同时接受本地化英文/日文显示别名，映射到不变的翻译语言代码。
- `agreement_text('en'/'ja')` 返回相应免责声明与原始 MIT；其他值返回中文版本。切换仅影响显示，不设置 agreement_version/accepted_at。

`App.tr(value)` 使用当前界面语言；`show_language_setup()` 创建或复用首次语言对话框；`apply_ui_language(code)` 校验支持代码、即时刷新控件/状态/协议显示，非法代码抛 UIValidationError，自身不代表接受协议。`open_manual()->bool` 通过 Windows 默认浏览器打开随包本地 HTML：中文用 PROJECT_MANUAL.html，英文/日文用 PROJECT_MANUAL.en.html；缺失或打开失败返回 false 并显示受控提示。保存入口负责在空闲时持久化，字体/标签外观仍下次开始屏幕翻译生效。


## 选择识别方式与 AI 图像精读

设置中的 OCR 模式为自动（默认）、Windows、像素文字。自动模式对英语低色数、高对比像素画面使用本地像素精读，其余优先 Windows OCR；像素文字模式适合旧游戏字体，仍会发生拼字错误。此三种 OCR 选择本身不联网。识别同一捕获帧，段落合并保留原文物理换行与源行几何，显示按原行数和占位约束；图片精读不等于提高截图帧率。

“AI 图像精读”是另一个默认关闭的开关。需要在线模式和当前槽位支持图像的模型；开启后向该槽位发送游戏选区 PNG 和本地 OCR 锚框/文字提示，仅校正这些已有框的原文，不新增模型猜测坐标。它可能改善像素字形，但增加识别延迟和费用；默认最短请求间隔 3 秒，可调 1–60 秒，只有稳定文字才提交，随后译文仍按 SSE 流式显示。失败回退本地识别，没有可靠本地定位的文字不能凭模型猜测坐标覆盖；0.01.27 额外提供仅用于精读的已测候选，并可附带同游戏区域小字放大图，详见 INPUT_INTERFACES.md。

提交 AI 前先按严格本地规则把同一行的叙述碎片拼回物理行，保留每行位置；纵向段落合并仍在识别后进行。识别失败沿用这些本地行，不由模型生成新坐标。

默认本地 OCR 不传图，AI 精读不发送整个桌面或游戏文件、不使用 File API 建立远端文件。它与翻译共享请求预算，没有 Key 时不会调用。改变模式/间隔前先停止翻译，等在途任务完成后保存；r4 使用协议会说明这项数据流变化。


## 游戏身份、识别模式与界面状态

`warmup_identity` 和 `App.current_warmup_scope` 保留旧名称，只提供命名档案或可执行文件身份用于档案隔离，不启动旧学习策略。软件参数移除专家、本地、积极、暖机与智能混合开关；无Key仅浏览已有资料。当前源语言下拉选择与对象实际语言检测保持独立。

`SettingsPanel` 保存 `ocr_mode=auto/native/pixel`、`ocr_refine_workers=1..8`、`context_max_chars=512..16000`、`context_history_records=1..64`，默认4/6000/24。`vision_ocr` 明确发送游戏选区图片，默认关闭。`timing` 的错误仅显示状态，不作为译文覆盖。

`App.open_translation_history()->Toplevel|None` 在空闲时读取当前档案/语向/身份的最多24条记录与状态，不请求API；忙或受控错误返回None。只读窗口显示更新时间、资料目录、每条原文/译文/语境。没有新事件时提示旧词条仍可浏览。不把SQLite完整内容装入Tk，也不回显密钥。

## API 请求无上限控件（0.01.20）

`unlimited_requests` 是独立复选框，默认关闭，跨中英日切换保持同一个布尔值。启用后额度数字输入禁用但不清空、不改写原值；关闭后按忙碌状态恢复输入。所有语言的保存入口都使用严格 bool 校验。运行屏幕翻译、手动请求、导入或待结束请求期间不允许保存策略；成功保存后下一引擎使用所选次数策略。

统计返回 `requests_remaining=None` 时表示无上限，不能把 null 显示为“0 次剩余”。`max_requests=0` 与无上限复选框是不同语义。引导不自动开启无上限，公开默认仍是有限模式。

## OCR 原像素保留状态（0.01.20）

界面从现有 objects 快照接收保留标记，OverlayState 立即清除对应旧覆盖并拒绝迟到译文。`Pipeline.get_stats().preserved_source` 供界面显示当前保留原文框数；不产生额外窗口，不把识别错字重画为“原文”。停止/失焦仍按现有会话规则清理。

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

## 窗口拖动跟随接口

`gl_overlay_anchored(context, regions, count, rows, row_count, offsets, origins)` 是 ABI 2 的新增导出。前六项与 `gl_overlay_fixed` 相同；`origins` 为 `2*count` 个 int32，逐项保存生成文字对象时的屏幕捕获原点 `(x,y)`。Python `NativeCore.show_overlay()` 从各对象的 `_capture_origin` 校验并构建数组，不把模型输出作为坐标。所有对象提供原点时使用新接口，否则走原有入口。

提交时将绝对 OCR 坐标换算为游戏客户区局部坐标，原生线程每 16 毫秒检查客户区位置，以 `SetWindowPos` 只移动覆盖 HWND，不重新翻译、不重新拟合字体、不抢焦点。即使后续 token 携带旧捕获原点，也不会跳回旧窗口位置。系统调度决定实际延迟，16 毫秒是检查周期而非延迟保证。

源行局部坐标保持不变；背景采样按对应帧的客户区原点重定位。窗口大小变化时隐藏旧尺寸覆盖，等待新的识别布局；最小化、失焦、越出客户区或虚拟屏幕时隐藏。原生捕获遇到瞬时移动、缩放或尚无首帧时返回 `changed:false,pending:true,lines:[]`，OCR/VisionCore 转发，Pipeline 不确认旧行、不发新请求，下一周期重试。不可恢复的接口错误仍终止当前捕获并显示错误。
