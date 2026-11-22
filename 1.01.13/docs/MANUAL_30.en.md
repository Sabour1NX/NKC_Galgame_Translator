<p>NKC_Galgame_Translator reads game text on Windows x64 and places translations over the original text. The game still handles mouse, controller and keyboard input.</p>
<nav><a href="#start">Getting started</a><a href="#pages">Application tabs</a><a href="#ocr">OCR and typography</a><a href="PERFORMANCE_REPORT.html">CUDA benchmark (Chinese)</a></nav>
<h2 id="start">Getting started</h2>
<ol>
<li>Choose the application language at first launch and review the agreement. The initial suggestion follows Windows. You can change the language in Settings.</li>
<li>In Settings, open API Configuration. Choose one of three slots and enter your OpenAI-compatible endpoint, model and key. The current Windows account encrypts the saved key.</li>
<li>In Screen Translation, select the game window and language pair. Choose a profile to resume its saved context, or leave the profile blank.</li>
<li>Select the whole game window or mark one or more regions. Start translation and switch back to the game. Stop / Restore removes the translated overlays.</li>
</ol>
<h2 id="pages">Application tabs</h2>
<div class="grid">
<section class="card"><h3>Screen Translation</h3><p>Choose the window, language pair, game profile and capture regions.</p></section>
<section class="card"><h3>Translation Dictionary</h3><p>Manage preferred terminology for the current game or shared glossary. Matching terms guide the model. Automatic translation history is available in Translation and Context Archive.</p></section>
<section class="card"><h3>Text Translation</h3><p>Translate pasted text and review applicable terminology.</p></section>
<section class="card"><h3>User Agreement</h3><p>Read the disclaimer and the MIT terms. Acceptance is saved with local settings.</p></section>
<section class="card"><h3>Settings</h3><p>Manage API slots, OCR, fonts, screenshot inclusion, source labels, the refresh shortcut and request limits.</p></section>
</div>
<h2 id="ocr">OCR and typography</h2>
<p>Enable CUDA at first launch or in Settings. The optional CUDA add-on and a compatible NVIDIA driver are required. The default memory budget is 1,024 MiB. The quality slider covers 0–100. Recognized retro pixel-font scenes can continue to use the CPU path.</p>
<p>Automatic sizing follows source text and the configured size limits. Supported short actions such as OK and Cancel use verified space around the original glyphs. Selecting such a button keeps the existing translation when its interior pixels remain the same.</p>
<p>Press <kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>R</kbd> to deliberately refresh the recognized regions. The shortcut can be changed or disabled. First-time model initialization can take several seconds.</p>
<p>See the <a href="USER_AGREEMENT.en.md">English user agreement</a> and the <a href="DEPENDENCY_MANIFEST.json">dependency manifest</a>.</p>
