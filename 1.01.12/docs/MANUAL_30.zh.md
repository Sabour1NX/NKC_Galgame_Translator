<p>在 Windows x64 上读取游戏窗口文字，将译文放回原位置。点击、方向键和确认键仍由游戏处理。</p>
<nav><a href="#start">开始使用</a><a href="#tabs">五个页面</a><a href="#settings">字体、OCR 与刷新</a><a href="#architecture">工程结构</a><a href="PERFORMANCE_REPORT.html">CUDA 性能报告</a><a href="TASK_REPORT.html">任务报告</a></nav>
<h2 id="start">开始使用</h2>
<ol>
<li>首次启动确认软件语言，阅读并同意使用协议。软件语言初始跟随 Windows，可在设置里切换中文、English 或日本語。</li>
<li>到「设置 → API 配置」选择一个槽位，填写 OpenAI 兼容 API 地址、模型及密钥。三个槽位分开保存，密钥由当前 Windows 账户加密。</li>
<li>返回「屏幕翻译」，选择游戏实际窗口与语言方向。可选游戏档案，用来恢复语境与语言设置。</li>
<li>选择「整个游戏窗口」或框选一个或多个文字区域，再点击「开始翻译」。切回游戏窗口查看原位译文。「停止 / 还原」撤下覆盖层。</li>
</ol>
<h2 id="tabs">五个页面</h2>
<div class="grid">
<section class="card"><h3>屏幕翻译</h3><p>选择游戏、语言、档案和识别区域。档案管理可以继续已有档案、保存备注或删除不再需要的档案。</p></section>
<section class="card"><h3>翻译词典</h3><p>可为当前游戏与语言对添加或导入首选译法，也可使用跨游戏通用词典。匹配术语作为 AI 参考，游戏条目优先。</p><p>自动保存的完整译文在「译文与语境档案」，手动术语表为空时也可能有历史记录。</p></section>
<section class="card"><h3>文本翻译</h3><p>粘贴原文，复核单句结果和词典参考范围。</p></section>
<section class="card"><h3>使用协议</h3><p>查阅免责声明与 MIT。接受状态随本机配置保存。</p></section>
<section class="card"><h3>设置</h3><p>配置 API、OCR、字体、截图是否包含译文、语言标注、快捷键及翻译并发和本次请求上限。</p></section>
</div>
<h2 id="settings">字体、OCR 与刷新</h2>
<ul>
<li>自动字号跟随源文字，可设置最小值和最大值，也可以固定字体及字号。译文过长时由自动字号在指定范围内缩小。短按钮如 OK 和 Cancel 在经截图确认的内侧留白范围内居中，保留焦点框。</li>
<li>游戏中的按钮焦点移动属于正常操作。按钮内部字形和留白像素相同时，已有译文继续使用。滚动或真实字形变化会重新核对位置。</li>
<li>默认 <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>R</kbd> 重新识别并翻译当前画面，可在设置中修改或关闭。</li>
<li>在首次设置或「设置」启用 CUDA OCR。默认显存预算 1024 MiB，可调。精度与性能滑条为 0–100。需要兼容的 NVIDIA 驱动与独立 CUDA 扩展。像素字体场景仍可能优先使用 CPU。</li>
<li>窗口选错时，请点「刷新窗口」并选实际游戏进程。首次加载 CUDA 模型可能需要数秒。OCR 可用时仍需已配置的翻译 API 才能产生新译文。</li>
</ul>
<h2 id="architecture">工程结构与工作流</h2>
<div class="flow" aria-label="工作流"><span>游戏窗口截图</span><b>→</b><span>整帧 OCR</span><b>→</b><span>ROI / 字形核对</span><b>→</b><span>文本跟踪</span><b>→</b><span>译文与语境处理</span><b>→</b><span>原位绘制</span></div>
<div class="scroll"><table><thead><tr><th>目录或模块</th><th>职责与接口</th></tr></thead><tbody>
<tr><th><code>nkc_galgame_translator/ocr.py</code></th><td>Python 调用 Windows OCR、便携 Tesseract 或 CUDA。识别结果带文本和矩形，跟踪前转换为屏幕坐标。</td></tr>
<tr><th><code>nkc_galgame_translator/pipeline.py</code></th><td>采集线程、跟踪与翻译池。输出带稳定对象 ID 和修订号的更新，过期修订不会覆盖新对象。</td></tr>
<tr><th><code>nkc_galgame_translator/translation.py</code></th><td>经 OpenAI 兼容 <code>POST /chat/completions</code> 流式请求；以游戏和语言对为边界保存术语与历史。</td></tr>
<tr><th><code>native/</code></th><td>C++17 提供窗口采集和 GDI 原位绘制。<code>gl_overlay_labels</code> 使用与区域数相同的标记数组，居中布局需要一个有效原文行。既有 ABI 2 保留。</td></tr>
<tr><th><code>tools/</code></th><td>辅助 OCR 进程、离线跑分、截图与 Windows x64 构建工具。依赖锁文件随源码分发。</td></tr>
<tr><th><code>config/</code> 与 <code>data/</code></th><td>本机配置与 SQLite 记录。分享时使用公开包；私有开发版包含本机凭据与档案。</td></tr>
</tbody></table></div>
