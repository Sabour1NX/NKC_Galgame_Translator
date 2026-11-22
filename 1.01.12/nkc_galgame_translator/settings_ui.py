# SPDX-License-Identifier: MIT
"""Parameter controls and asynchronous dictionary preview/import windows."""

from .i18n import NATIVE_NAMES, ui_source
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import font as tkfont
from .tuning import NUMERIC_FIELDS, BOOLEAN_FIELDS, DEFAULT_OVERLAY_FONT, validate_font_family, PERFORMANCE_PRESETS
from .languages import label_translation
from .cuda_settings_ui import CudaControls
from .hotkeys import DEFAULT_HOTKEY, DEFAULT_TOGGLE_HOTKEY

INTERFACE_LANGUAGE_LABELS = {label: code for code, label in NATIVE_NAMES.items()}
OCR_MODE_LABELS = {ui_source('Automatic OCR'):'auto','Windows OCR':'native',ui_source('Pixel-text recognition'):'pixel'}
VISION_MODE_LABELS = {ui_source('Forced screenshot OCR'): 'force', ui_source('Screenshot OCR off'): 'off'}
SAMPLING_MODE_LABELS = {ui_source('Off'):'off',ui_source('Automatic'):'auto',ui_source('Oversampling'):'supersample'}


class SettingsPanel:
    def __init__(self,app,parent,actions):
        self.app=app;self.vars={};self.controls=[];self._busy=False
        ttk.Label(parent,text=self.app.tr(ui_source('Translation and recognition settings')),style='Heading.TLabel').pack(anchor='w')
        app._hint(parent,ui_source('Saved settings apply to the next translation session. Stop the current session first. Higher concurrency increases simultaneous requests and resource use.')).pack(anchor='w',pady=(8,12))
        presets=ttk.Frame(parent);presets.pack(fill='x',pady=(0,8))
        for label,preset in ((ui_source('Faster response'),'responsive'),(ui_source('Balanced resources'),'balanced')):
            button=ttk.Button(presets,text=app.tr(label),command=lambda name=preset:self.apply_performance_preset(name))
            button.pack(side='left',padx=(0,8));self.controls.append(button)
        app._hint(parent,ui_source('Faster response: 50 ms capture, 80 ms settling, 8 translation workers and 4 refinement workers. Uses more CPU, memory and concurrent API requests. Increase settling for typewriter dialogue. Click Save settings to apply.')).pack(anchor='w',pady=(0,12))
        hotkeys=ttk.LabelFrame(parent,text=app.tr(ui_source('Retranslation shortcut')),padding=12)
        hotkeys.pack(fill='x',pady=(0,14))
        self.vars['retranslate_hotkey_enabled']=tk.BooleanVar(value=app.config.get('retranslate_hotkey_enabled',True))
        self.vars['retranslate_hotkey']=tk.StringVar(value=app.config.get('retranslate_hotkey',DEFAULT_HOTKEY))
        self.hotkey_enabled_check=ttk.Checkbutton(hotkeys,text=app.tr(ui_source('Enable global retranslation shortcut')),variable=self.vars['retranslate_hotkey_enabled'])
        self.hotkey_enabled_check.pack(anchor='w')
        row=ttk.Frame(hotkeys);row.pack(fill='x',pady=(8,4))
        ttk.Label(row,text=app.tr(ui_source('Key combination'))).pack(side='left')
        self.hotkey_entry=ttk.Entry(row,textvariable=self.vars['retranslate_hotkey'],width=26)
        self.hotkey_entry.pack(side='left',padx=12)
        self.controls.extend((self.hotkey_enabled_check,self.hotkey_entry))
        app._hint(hotkeys,ui_source('Example: Ctrl+Alt+R. Include Ctrl or Alt; Shift is optional. Use a letter, digit or F1–F24 (except F12). Save to apply.')).pack(anchor='w',pady=(4,6))
        app._hint(hotkeys,ui_source('Retranslates only the selected game area and keeps profiles and history. If a combination conflicts, the previous shortcut remains active.')).pack(anchor='w')
        self.hotkey_status=tk.StringVar(value=app.tr(ui_source('Shortcut: not registered yet')))
        ttk.Label(hotkeys,textvariable=self.hotkey_status,style='Hint.TLabel',wraplength=680).pack(anchor='w',pady=(6,0))
        self.vars['retranslate_hotkey_enabled'].trace_add('write',self.update_hotkey_controls)
        toggle=ttk.Frame(hotkeys);toggle.pack(fill='x',pady=(10,0))
        self.vars['toggle_hotkey_enabled']=tk.BooleanVar(value=app.config.get('toggle_hotkey_enabled',True))
        self.vars['toggle_hotkey']=tk.StringVar(value=app.config.get('toggle_hotkey',DEFAULT_TOGGLE_HOTKEY))
        self.toggle_enabled_check=ttk.Checkbutton(toggle,text=app.tr(ui_source('Enable global translation toggle')),
                                                  variable=self.vars['toggle_hotkey_enabled'])
        self.toggle_enabled_check.pack(side='left')
        self.toggle_hotkey_entry=ttk.Entry(toggle,textvariable=self.vars['toggle_hotkey'],width=19)
        self.toggle_hotkey_entry.pack(side='left',padx=12)
        self.controls.extend((self.toggle_enabled_check,self.toggle_hotkey_entry))
        self.vars['toggle_hotkey_enabled'].trace_add('write',self.update_hotkey_controls)
        self.update_hotkey_controls()
        appearance = ttk.LabelFrame(parent, text=self.app.tr(ui_source('Translation appearance')), padding=12)
        appearance.pack(fill='x', pady=(0, 14))
        row = ttk.Frame(appearance);row.pack(fill='x')
        ttk.Label(row, text=self.app.tr(ui_source('Overlay font'))).pack(side='left')
        family = tk.StringVar(value=app.config.get('overlay_font_family', DEFAULT_OVERLAY_FONT))
        self.vars['overlay_font_family'] = family
        families = sorted(set(name for name in tkfont.families(app.root)
                              if name and not name.startswith('@') and len(name.encode('utf-16-le', errors='replace')) <= 62), key=str.casefold)
        self.font_box = ttk.Combobox(row, textvariable=family, values=families, width=28)
        self.font_box.pack(side='left', fill='x', expand=True, padx=(12, 0));self.controls.append(self.font_box)
        app._hint(appearance, ui_source('Select an installed font or enter its family name. Windows supplies fallback fonts for missing glyphs.')).pack(anchor='w', pady=(6, 8))
        for name in ('auto_font_style','capture_translations','auto_font_size'):
            label,default=BOOLEAN_FIELDS[name]
            variable=tk.BooleanVar(value=app.config.get(name,default));self.vars[name]=variable
            control=ttk.Checkbutton(appearance,text=self.app.tr(label),variable=variable)
            control.pack(anchor='w',pady=3);self.controls.append(control)
        app._hint(appearance,ui_source('Approximate pixel, serif, sans-serif or monospaced styles, checking translated glyphs per box. Keep the source if no supported font is available. Turn off to use the manual font above.')).pack(anchor='w',pady=(4,8))
        self.font_size_controls={}
        for name in ('overlay_font_size','overlay_font_min','overlay_font_max'):
            label,minimum,maximum,default=NUMERIC_FIELDS[name]
            row=ttk.Frame(appearance);row.pack(fill='x',pady=3)
            ttk.Label(row,text=self.app.tr(label),width=28).pack(side='left')
            variable=tk.StringVar(value=str(app.config.get(name,default)));self.vars[name]=variable
            control=ttk.Spinbox(row,from_=minimum,to=maximum,textvariable=variable,width=8)
            control.pack(side='left');self.controls.append(control);self.font_size_controls[name]=control
        app._hint(appearance,ui_source('Automatic sizing follows source height and shrinks within your range. Fixed size does not shrink. Text that cannot fit leaves the original visible.')).pack(anchor='w',pady=(6,4))
        app._hint(appearance,ui_source('Applies to desktop screenshots and recording. In-game captures may contain only game content. When enabled, separate window capture may show a Windows capture border.')).pack(anchor='w',pady=(0,8))
        self.vars['auto_font_size'].trace_add('write',self.update_font_controls)
        self.update_font_controls()
        for name in ('show_source_label', 'source_label_mixed_only', 'show_translation_brackets'):
            label, default = BOOLEAN_FIELDS[name]
            variable = tk.BooleanVar(value=app.config.get(name, default));self.vars[name] = variable
            control = ttk.Checkbutton(appearance, text=self.app.tr(label), variable=variable)
            control.pack(anchor='w', pady=3, padx=(18 if name=='source_label_mixed_only' else 0, 0));self.controls.append(control)
            if name=='source_label_mixed_only':self.mixed_only_check=control
        self.preview_text = tk.StringVar()
        self.preview_label = ttk.Label(appearance, textvariable=self.preview_text, wraplength=660)
        self.preview_label.pack(anchor='w', pady=(10, 4))
        self.preview_hint = tk.StringVar()
        self.preview_hint_label = ttk.Label(appearance, textvariable=self.preview_hint, style='Hint.TLabel', wraplength=660)
        self.preview_hint_label.pack(anchor='w', fill='x')
        appearance.bind('<Configure>', lambda event: self.preview_hint_label.configure(
            wraplength=max(160, event.width - 28)), add='+')
        for name in ('overlay_font_family', 'show_source_label', 'show_translation_brackets', 'source_label_mixed_only'):
            self.vars[name].trace_add('write', self.update_preview)
        self.update_preview()
        interface_row = ttk.Frame(parent);interface_row.pack(fill='x', pady=(0, 14))
        ttk.Label(interface_row, text=self.app.tr(ui_source('Interface language'))).pack(side='left')
        selected = next((label for label, code in INTERFACE_LANGUAGE_LABELS.items()
                         if code == app.config.get('app_language', 'zh-CN')), ui_source('Simplified Chinese'))
        self.app_language_var = tk.StringVar(value=selected)
        self.language_box = ttk.Combobox(interface_row, textvariable=self.app_language_var,
                                        values=tuple(INTERFACE_LANGUAGE_LABELS), state='readonly', width=18)
        self.language_box.pack(side='left', padx=12);self.controls.append(self.language_box)
        ocr_row=ttk.Frame(parent);ocr_row.pack(fill='x',pady=(0,10))
        ttk.Label(ocr_row,text=self.app.tr(ui_source('Local text recognition'))).pack(side='left')
        self.ocr_mode_var=tk.StringVar(value=next((self.app.tr(label) for label,code in OCR_MODE_LABELS.items() if code==app.config.get('ocr_mode','auto')),self.app.tr(ui_source('Automatic OCR'))))
        self.ocr_mode_box=ttk.Combobox(ocr_row,textvariable=self.ocr_mode_var,values=[self.app.tr(label) for label in OCR_MODE_LABELS],state='readonly',width=20)
        self.ocr_mode_box.pack(side='left',padx=12);self.controls.append(self.ocr_mode_box)
        sampling=ttk.Frame(parent);sampling.pack(fill='x',pady=(0,8))
        ttk.Label(sampling,text=app.tr(ui_source('Motion sampling'))).pack(side='left')
        selected_sampling=app.config.get('sampling_mode','auto')
        self.sampling_mode_var=tk.StringVar(value=next(
            (app.tr(label) for label,code in SAMPLING_MODE_LABELS.items() if code==selected_sampling),
            app.tr(ui_source('Automatic'))))
        self.sampling_mode_box=ttk.Combobox(sampling,textvariable=self.sampling_mode_var,
            values=[app.tr(label) for label in SAMPLING_MODE_LABELS],state='readonly',width=20)
        self.sampling_mode_box.pack(side='left',padx=12);self.controls.append(self.sampling_mode_box)
        app._hint(parent,ui_source('Off follows the capture interval. Automatic speeds up briefly during motion. Oversampling starts at the faster rate.')).pack(anchor='w',pady=(0,10))
        app._hint(parent,app.tr(ui_source('Fast capture targets about {ms} ms based on VRAM.')).format(
            ms=getattr(app,'fast_capture_ms',50))).pack(anchor='w',pady=(0,10))
        self.cuda_controls=CudaControls(app,parent,self.vars)
        vision_row = ttk.Frame(parent)
        vision_row.pack(fill='x', pady=(0, 6))
        ttk.Label(vision_row, text=app.tr(ui_source('Image recognition via the LLM backend'))).pack(side='left', padx=(0, 12))
        selected = app.config.get('vision_ocr_mode', 'off')
        self.vision_mode_var = tk.StringVar(value=next(
            (app.tr(label) for label, code in VISION_MODE_LABELS.items() if code == selected), app.tr(ui_source('Screenshot OCR off'))))
        self.vision_mode_box = ttk.Combobox(vision_row, textvariable=self.vision_mode_var,
            values=[app.tr(label) for label in VISION_MODE_LABELS], state='readonly', width=14)
        self.vision_mode_box.pack(side='left')
        app._hint(parent, ui_source('Force sends changed game selections to the active API slot. Custom services must accept images. Off uses local OCR.')).pack(anchor='w', pady=(0, 6))
        if getattr(app,'_initial_vision_note',''):
            app._hint(parent, app._initial_vision_note).pack(anchor='w', pady=(0, 10))
        context_box=ttk.LabelFrame(parent,text=app.tr(ui_source('Translation context and on-screen text')),padding=12)
        context_box.pack(fill='x',pady=(0,12))
        variable=tk.BooleanVar(value=app.config.get('context_web_search',False));self.vars['context_web_search']=variable
        control=ttk.Checkbutton(context_box,text=app.tr(BOOLEAN_FIELDS['context_web_search'][0]),variable=variable)
        control.pack(anchor='w');self.controls.append(control)
        app._hint(context_box,ui_source('Context layer: researches game background and uses compressed history. Display layer: shows only the current translation; local layout controls font size and position.')).pack(anchor='w',pady=(6,4))
        app._hint(context_box,ui_source('Online context sends the game profile, supplied context and an excerpt of the first source text. It adds an API request and waiting time; results are cached for 15 minutes per profile. Requires official DeepSeek deepseek-flash. Search status is shown; direct translation remains available when search is unused or fails.')).pack(anchor='w',pady=(0,6))
        self.context_agent_status=tk.StringVar(value=app.tr(ui_source('Online context: not started')))
        ttk.Label(context_box,textvariable=self.context_agent_status,style='Hint.TLabel',wraplength=680).pack(anchor='w')
        budget=ttk.Frame(parent);budget.pack(fill='x',pady=(0,8))
        variable=tk.BooleanVar(value=app.config.get('unlimited_requests',False));self.vars['unlimited_requests']=variable
        self.unlimited_requests_check=ttk.Checkbutton(budget,text=self.app.tr(BOOLEAN_FIELDS['unlimited_requests'][0]),variable=variable)
        self.unlimited_requests_check.pack(anchor='w',pady=(0,6));self.controls.append(self.unlimited_requests_check)
        row=ttk.Frame(budget);row.pack(fill='x')
        label,minimum,maximum,default=NUMERIC_FIELDS['max_requests']
        ttk.Label(row,text=self.app.tr(label)).pack(side='left')
        variable=tk.StringVar(value=str(app.config.get('max_requests',default)));self.vars['max_requests']=variable
        self.request_limit_control=ttk.Spinbox(row,from_=minimum,to=maximum,textvariable=variable,width=10)
        self.request_limit_control.pack(side='left',padx=12);self.controls.append(self.request_limit_control)
        ttk.Label(row,text=self.app.tr(f'{minimum}—{maximum}'),style='Hint.TLabel').pack(side='left')
        self.vars['unlimited_requests'].trace_add('write',self.update_request_limit)
        self.update_request_limit()
        app._hint(parent,ui_source('Unlimited API requests removes only the session request-count limit. Concurrency, timeouts and retry limits still apply. When disabled, the entered quota applies; 0 means no requests. Without an API key, only saved records can be browsed.')).pack(anchor='w',pady=(0,12))
        table=ttk.Frame(parent);table.pack(fill='x')
        table.columnconfigure(0,weight=1)
        for row,(name,(label,minimum,maximum,default)) in enumerate(NUMERIC_FIELDS.items()):
            if name in ('max_requests','cuda_quality','cuda_memory_mb') or name in self.font_size_controls:continue
            ttk.Label(table,text=self.app.tr(label)).grid(row=row,column=0,sticky='w',pady=6)
            variable=tk.StringVar(value=str(app.config.get(name,default)));self.vars[name]=variable
            increment={'context_max_chars':256, 'translation_hold_ms':50, 'scene_change_sensitivity':5}.get(name,1)
            control=ttk.Spinbox(table,from_=minimum,to=maximum,increment=increment,textvariable=variable,width=10)
            control.grid(row=row,column=1,sticky='e',padx=12,pady=6);self.controls.append(control)
            ttk.Label(table,text=self.app.tr(f'{minimum}—{maximum}'),style='Hint.TLabel').grid(row=row,column=2,sticky='w')
        app._hint(parent,ui_source('The hold covers brief OCR gaps on a stable screen. Set it to 0 to disable. Higher sensitivity clears stale translations sooner.')).pack(anchor='w',pady=(3,0))
        ttk.Separator(parent).pack(fill='x',pady=14)
        for name,(label,default) in BOOLEAN_FIELDS.items():
            if name in self.vars:continue
            variable=tk.BooleanVar(value=bool(app.config.get(name,default)));self.vars[name]=variable
            control=ttk.Checkbutton(parent,text=self.app.tr(label),variable=variable)
            control.pack(anchor='w',pady=5);self.controls.append(control)
        app._hint(parent,ui_source('The confidence threshold applies only to portable OCR; Windows OCR does not supply this score. Request limits count the current engine session. Saving settings creates a new engine and resets the count; retries count toward the limit.')).pack(anchor='w',pady=(0,12))
        app._hint(parent,ui_source('All new translations use AI. History and context are compressed automatically; bounded excerpts inform future requests. Local expert translation rules are removed.')).pack(anchor='w',pady=(0,12))
        self.message=tk.StringVar()
        self.save_button=ttk.Button(actions,text=self.app.tr(ui_source('Save settings')),style='Accent.TButton',command=app.save_settings)
        self.save_button.pack(side='right',anchor='s');self.controls.append(self.save_button)
        self.message_label=ttk.Label(actions,textvariable=self.message,style='Shell.TLabel',wraplength=245)
        self.message_label.pack(side='right',anchor='s',padx=(0,12),pady=(0,5))

    def apply_performance_preset(self,name):
        if self._busy:return
        for key,value in PERFORMANCE_PRESETS[name].items():self.vars[key].set(str(value))
        self.message.set(self.app.tr(ui_source('Values filled in. Click Save settings to apply.')))

    def update_preview(self, *_):
        self.mixed_only_check.configure(state='disabled' if self._busy or not self.vars['show_source_label'].get() else 'normal')
        try:
            family = validate_font_family(self.vars['overlay_font_family'].get())
            show = bool(self.vars['show_source_label'].get())
            mixed = bool(self.vars['source_label_mixed_only'].get())
            brackets = bool(self.vars['show_translation_brackets'].get())
            def sample(label, source, show_label):
                return label_translation(self.app.tr(ui_source(label)), source,
                    show_source_label=show_label, show_translation_brackets=brackets,
                    label_language=self.app.ui_language)
            text = sample('Welcome to the stars', 'en', show and not mixed)
            if show and mixed:
                text = (self.app.tr(ui_source('Single language: ')) + text + '\n' +
                        self.app.tr(ui_source('Mixed languages: ')) + sample('Welcome', 'en', True) +
                        ' / ' + sample('Start', 'ja', True))
            self.preview_label.configure(font=(family, 16))
            self.preview_text.set(text)
            self.preview_hint.set(self.app.tr(ui_source('Show labels only when at least two languages other than the target language are detected on screen. Regional variants count as the same language.') if show and mixed
                                  else ui_source('Appearance preview only; no API call or dictionary changes.')))
        except (ValueError, tk.TclError):
            self.preview_label.configure(font=(DEFAULT_OVERLAY_FONT, 16))
            self.preview_text.set(ui_source('Welcome to the stars'))
            self.preview_hint.set(self.app.tr(ui_source('Enter a valid system font name before saving.')))

    def values(self):
        result = {name:var.get() for name,var in self.vars.items()}
        result.update(self.cuda_controls.values())
        result['app_language'] = INTERFACE_LANGUAGE_LABELS.get(self.app_language_var.get(), '')
        result['ocr_mode'] = next((code for label,code in OCR_MODE_LABELS.items() if self.ocr_mode_var.get()==self.app.tr(label)), '')
        result['sampling_mode'] = next((code for label,code in SAMPLING_MODE_LABELS.items()
                                       if self.sampling_mode_var.get()==self.app.tr(label)), '')
        result['vision_ocr_mode'] = next((code for label, code in VISION_MODE_LABELS.items()
                                         if self.vision_mode_var.get() == self.app.tr(label)), '')
        return result

    def update_request_limit(self,*_):
        self.request_limit_control.configure(state='disabled' if self._busy or self.vars['unlimited_requests'].get() else 'normal')
    def update_hotkey_controls(self,*_):
        self.hotkey_entry.configure(state='normal' if not self._busy and self.vars['retranslate_hotkey_enabled'].get() else 'disabled')
        self.toggle_hotkey_entry.configure(state='normal' if not self._busy and self.vars['toggle_hotkey_enabled'].get() else 'disabled')
    def update_font_controls(self,*_):
        automatic=self.vars['auto_font_size'].get()
        for name,control in self.font_size_controls.items():
            enabled=not self._busy and (not automatic if name=='overlay_font_size' else automatic)
            control.configure(state='normal' if enabled else 'disabled')
    def refresh(self,busy):
        self._busy=bool(busy)
        self.cuda_controls.refresh(busy)
        for control in self.controls:control.configure(state='disabled' if busy else 'normal')
        self.language_box.configure(state='disabled' if busy else 'readonly')
        self.ocr_mode_box.configure(state='disabled' if busy else 'readonly')
        self.sampling_mode_box.configure(state='disabled' if busy else 'readonly')
        self.vision_mode_box.configure(state='disabled' if busy else 'readonly')
        self.mixed_only_check.configure(state='disabled' if busy or not self.vars['show_source_label'].get() else 'normal')
        self.update_request_limit()
        self.update_font_controls()
        self.update_hotkey_controls()
        if hasattr(self,'context_agent_status'):
            status='ready' if self.app.config.get('context_web_search',False) else 'disabled'
            if getattr(self.app,'engine',None):
                info=self.app.engine.get_context_agent_status()
                if isinstance(info,dict):status=info.get('status',status)
            labels={'disabled':ui_source('Online context: off'),'ready':ui_source('Online context: waiting for source text'),
                    'searching':ui_source('Online context: researching background'),'searched':ui_source('Online context: search sources received'),
                    'not_used':ui_source('Online context: model did not use search'),'no_sources':ui_source('Online context: search returned no sources'),
                    'search_failed':ui_source('Online context: search unavailable; using existing context'),
                    'unsupported':ui_source('Online context: unsupported endpoint or model; translating directly'),
                    'budget_skipped':ui_source('Online context: remaining request budget reserved for translation'),
                    'unavailable':ui_source('Online context: temporarily unavailable; translating directly')}
            self.context_agent_status.set(self.app.tr(labels.get(status,labels['unavailable'])))


class DictionaryImportDialog:
    def __init__(self,app):
        self.app=app;self.entries=None;self.preview_scope=None;self.closed=False
        self.window=tk.Toplevel(app.root);self.window.title(self.app.tr(ui_source('Import glossary · NKC_Galgame_Translator')))
        self.window.geometry('760x620');self.window.minsize(700,580)
        self.window.transient(app.root);self.window.protocol('WM_DELETE_WINDOW',self.close)
        body=ttk.Frame(self.window,padding=22);body.pack(fill='both',expand=True)
        ttk.Label(body,text=self.app.tr(ui_source('Preview before importing')),style='Heading.TLabel').pack(anchor='w')
        ttk.Label(body,text=self.app.tr(ui_source('CSV / TSV / JSON / TMX · Up to 20 MiB and 100,000 entries; up to 5,000 entries per game dictionary.')),
                  style='Hint.TLabel',wraplength=700).pack(anchor='w',pady=(8,12))
        self.path=tk.StringVar();self.shared=tk.BooleanVar(value=True);self.replace=tk.BooleanVar(value=False)
        row=ttk.Frame(body);row.pack(fill='x')
        self.path_entry=ttk.Entry(row,textvariable=self.path);self.path_entry.pack(side='left',fill='x',expand=True)
        self.browse_button=ttk.Button(row,text=self.app.tr(ui_source('Choose file')),command=self.browse);self.browse_button.pack(side='left',padx=(8,0))
        self.shared_check=ttk.Checkbutton(body,text=self.app.tr(ui_source('Import into shared dictionary (same language pair, across games)')),variable=self.shared,command=self.invalidate)
        self.shared_check.pack(anchor='w',pady=(12,6))
        self.replace_check=ttk.Checkbutton(body,text=self.app.tr(ui_source('Replace conflicting translations (existing entries kept by default)')),variable=self.replace)
        self.replace_check.pack(anchor='w')
        self.scope_label=ttk.Label(body,text=self.app.tr(''),style='Hint.TLabel');self.scope_label.pack(anchor='w',pady=8)
        self.message=tk.StringVar(value=self.app.tr(ui_source('Choose a file, then preview it. This step does not change the dictionary.')))
        # Reserve the action row before the expandable preview so the bottom
        # buttons cannot be compressed at the minimum window size.
        row=ttk.Frame(body);row.pack(side='bottom',fill='x')
        self.preview_button=ttk.Button(row,text=self.app.tr(ui_source('Preview file')),command=self.preview);self.preview_button.pack(side='left')
        self.commit_button=ttk.Button(row,text=self.app.tr(ui_source('Import')),command=self.commit,style='Accent.TButton',state='disabled')
        self.commit_button.pack(side='left',padx=8)
        self.close_button=ttk.Button(row,text=self.app.tr(ui_source('Close')),command=self.close);self.close_button.pack(side='right')
        ttk.Label(body,textvariable=self.message,foreground='#B6332D',wraplength=650).pack(side='bottom',anchor='w',pady=10)
        self.preview_text=app._text(body,height=10);self.preview_text.pack(fill='both',expand=True)
        self.preview_text.configure(state='disabled')
        self.path.trace_add('write',lambda *_:self.invalidate())
        self._modal=self.window.after_idle(self._make_modal)
        self.invalidate()

    def _make_modal(self):
        self._modal=None
        if self.window.winfo_viewable():self.window.grab_set()

    def invalidate(self):
        self.entries=None;self.preview_scope=None
        game,source,target=self.app.term_scope()
        template = (ui_source('Import destination: {source} → {target} · Shared dictionary') if self.shared.get()
                    else ui_source('Import destination: {source} → {target} · Game profile: {profile}'))
        self.scope_label.configure(text=self.app.tr(template).format(
            source=source, target=target, profile=game or self.app.tr(ui_source('(Unspecified)'))))
        self.commit_button.configure(state='disabled')

    def browse(self):
        if self.app._mode_busy():return
        path=filedialog.askopenfilename(parent=self.window,title=self.app.tr(ui_source('Choose dictionary file')),
            filetypes=[(self.app.tr(ui_source('Dictionary files')),'*.csv *.tsv *.json *.tmx'),(self.app.tr(ui_source('All files')),'*.*')])
        if path:self.path.set(path)

    def _busy(self,value):
        self.app.import_busy=value;self.app._refresh_mode_control()
        for control in (self.path_entry,self.browse_button,self.shared_check,self.replace_check,self.preview_button):
            control.configure(state='disabled' if value else 'normal')
        self.commit_button.configure(state='normal' if not value and self.entries is not None else 'disabled')

    def preview(self):
        if self.app._mode_busy():return False
        path=self.path.get().strip()
        if not path:self.message.set(self.app.tr(ui_source('Choose a dictionary file first.')));return False
        self.invalidate();scope=(*self.app.term_scope(),bool(self.shared.get()))
        self._busy(True);self.message.set(self.app.tr(ui_source('Reading file…')))
        def work():
            from .dictionary_import import parse_dictionary, DictionaryImportError
            try:payload=('preview',parse_dictionary(path,scope[1],scope[2]),scope)
            except DictionaryImportError as error:payload=('error',str(error),None)
            except Exception:payload=('error',ui_source('Could not parse the dictionary. Check the file format.'),None)
            self.app.events.put(('dictionary_result',0,(self,payload)))
        threading.Thread(target=work,daemon=True,name='dictionary-preview').start();return True

    def commit(self):
        if self.app._mode_busy():return False
        if self.entries is None or self.preview_scope is None:
            self.message.set(self.app.tr(ui_source('Preview the file first.')));return False
        entries=self.entries;game,source,target,shared=self.preview_scope;replace=bool(self.replace.get())
        if (*self.app.term_scope(),bool(self.shared.get()))!=self.preview_scope:
            self.invalidate();self.message.set(self.app.tr(ui_source('The dictionary scope changed. Preview the file again.')));return False
        if not shared and not game:
            self.message.set(self.app.tr(ui_source('Select a game profile or the shared dictionary. Unassigned legacy terms are for browsing only.')));return False
        try:engine=self.app.get_engine()
        except Exception:
            self.message.set(self.app.tr(ui_source('Could not open the local dictionary. Check write access to the data folder.')));return False
        self._busy(True);self.message.set(self.app.tr(ui_source('Writing dictionary…')))
        def work():
            from .translation import TranslationError
            try:payload=('import',engine.import_terms(entries,game,source,target,shared=shared,replace=replace),None)
            except TranslationError as error:payload=('error',str(error),None)
            except Exception:payload=('error',ui_source('Import failed. Check the dictionary file and data folder.'),None)
            self.app.events.put(('dictionary_result',0,(self,payload)))
        threading.Thread(target=work,daemon=True,name='dictionary-import').start();return True

    def receive(self,payload):
        kind,result,scope=payload
        if kind=='preview':
            self.entries=result;self.preview_scope=scope
            self.preview_text.configure(state='normal')
            self.preview_text.delete('1.0','end')
            for row in result[:5]:self.preview_text.insert('end',f'{row["source"][:200]} → {row["target"][:200]}\n\n')
            self.preview_text.configure(state='disabled')
            self.message.set(self.app.tr(f'\u9884\u89c8\u6210\u529f\uff0c\u5171 {len(result)} \u6761\uff1b\u4e0a\u65b9\u5c55\u793a\u524d 5 \u6761\uff0c\u5c1a\u672a\u5199\u5165\u3002'))
        elif kind=='import':
            self.message.set(self.app.tr(f'\u5df2\u5bfc\u5165\uff1a\u65b0\u589e {result.get("inserted",0)}\uff0c\u66f4\u65b0 {result.get("updated",0)}\uff0c\u4fdd\u7559/\u8df3\u8fc7 {result.get("skipped",0)}\u3002'))
            self.entries=None;self.preview_scope=None
        else:self.message.set(self.app.tr(result))
        self._busy(False)
        if kind=='import':self.app.refresh_terms()

    def close(self):
        if self.app.import_busy:
            self.message.set(self.app.tr(ui_source('Wait for the current parsing or write operation to finish.')));return False
        if self.closed:return True
        self.closed=True;self.entries=None
        if self._modal is not None:self.window.after_cancel(self._modal)
        if self.window.grab_current()==self.window:self.window.grab_release()
        self.window.destroy()
        if self.app.import_dialog is self:self.app.import_dialog=None
        return True
