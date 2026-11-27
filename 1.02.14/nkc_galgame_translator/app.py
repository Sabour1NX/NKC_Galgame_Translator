# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import queue
import threading
import sys
import time
import os
import tkinter as tk
from tkinter import ttk, messagebox
from . import __version__
from .event_queue import DisplayEvents
from .workbench_icons import load_icons
from .branding import configure_process_identity, install_window_icon
from .config_store import ConfigStore, ConfigStoreError
from .agreement import AGREEMENT_VERSION, AGREEMENT_TITLE, AGREEMENT_TEXT
from .i18n import translate, initial_language, localize_widgets, agreement_text, LanguageLabels, SUPPORTED, ui_source
from .language_setup import CUDA_FIELDS, InitializationDialog
from .setup_ui import ApiSettingsDialog
from .feature_ui import FeaturePanel, shortcut_popup
from .themes import DEFAULT_THEME, chart_style, mix, palette, validate_theme
from .resource_usage import ResourceUsage, version_colors
from .ui_font import UI_BODY_SIZE, UI_SMALL_SIZE, load_ui_font
from .localization_export import Exporter, Line, export_preferences
from .api_providers import local_endpoint
from .settings_ui import (SettingsPanel, DictionaryImportDialog, INTERFACE_LANGUAGE_LABELS, OCR_MODE_LABELS,
                          SAMPLING_MODE_LABELS, VISION_MODE_LABELS)
from .tuning import (validate_tuning, TuningValidationError, TUNING_DEFAULTS, APPEARANCE_FIELDS,
                     fast_capture_interval_ms, default_sampling_mode)
from .security import SecurityValidationError, validate_api_url, validate_model, normalize_api_key
from .native import NativeCore, video_memory_mb
from .translation import TranslationEngine, TranslationError
from .pipeline import Pipeline
from .game_identity import warmup_identity
from .presentation import OverlayState
from .windows import (enable_dpi, window_list, client_rect, foreground, virtual_screen,
                      visible_client_selections, window_metadata, window_state, translation_target, GameProcess)
from .selection_regions import client_selections, capture_plan, overlaps, MAX_REGIONS, limit_two_layers
from .scrolling import ComboboxPopupGuard
from .profile_ui import ProfileManagerDialog
from .hotkeys import GlobalHotkey, DEFAULT_TOGGLE_HOTKEY
from .window_profiles import matching_window

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
BRAND = ui_source('NKC_Galgame_Translator')
PAPER = '#F7F3EE'
WHITE = '#FFFEFC'
INK = '#302E2B'
MUTED = '#756D65'
RED = '#B6332D'
PALE = '#F5E8E0'
LINE = '#E2D8CE'

LANGUAGES = LanguageLabels({ui_source('Japanese'): 'ja', ui_source('English'): 'en', ui_source('Simplified Chinese'): 'zh-Hans', ui_source('Traditional Chinese'): 'zh-Hant', ui_source('Korean'): 'ko', ui_source('French'): 'fr', ui_source('German'): 'de', ui_source('Spanish'): 'es'})


def translation_language_name(code, default):
    """Restore supported selections, including old zh-CN/zh-TW aliases."""
    code = str(code or '').lower()
    code = {'zh-cn':'zh-hans', 'zh-tw':'zh-hant'}.get(code, code)
    return next((name for name, value in LANGUAGES.items() if value.lower() == code),
                next((name for name, value in LANGUAGES.items() if value == code.split('-')[0]), default))


class UIValidationError(ValueError):
    """A controlled, non-sensitive UI diagnostic."""


class App:
    def __init__(self, *, show_setup=True):
        enable_dpi()
        configure_process_identity()
        self.ui_font = load_ui_font(ROOT)
        self.welcome_session = None
        self.root = tk.Tk()
        self.project_root = ROOT
        self.config_store = ConfigStore(ROOT)
        self.config = self.config_store.load()
        nvidia_mb=video_memory_mb(ROOT,0x10de)
        self.fast_capture_ms=fast_capture_interval_ms(nvidia_mb or video_memory_mb(ROOT))
        self.config.setdefault('sampling_mode',default_sampling_mode(nvidia_mb))
        self._initial_vision_note=''
        if self.config.get('vision_ocr_mode') in (None,'hardware'):
            from .cuda_ocr import CudaOcr
            installed=bool(nvidia_mb and CudaOcr(ROOT).available())
            self.config['vision_ocr_mode']='off' if installed else 'force'
            self._initial_vision_note=(ui_source('CUDA OCR detected. LLM backend image recognition defaults to Off.')
                                       if installed else ui_source('CUDA OCR unavailable. LLM backend image recognition defaults to Force.'))
            if show_setup:
                try:self.config=self.config_store.save(dict(self.config))
                except ConfigStoreError:pass
        self.ui_language = initial_language(self.config, interactive=bool(show_setup))
        self.setup_dialog = None
        self._system_palette_watch = None
        self.window_icon_path=install_window_icon(self.root, ROOT)
        self.root.title(self.tr(f'{BRAND} {__version__}'))
        self.root.geometry('980x820')
        self.root.minsize(850, 720)
        self.root.configure(bg=PAPER)
        self.events = DisplayEvents()
        self._backend_alerts = {}
        self._backend_dialog_open = False
        self.pipeline, self.core, self.engine = None, None, None
        self.exporter = None
        self.export_session = None
        self._export_seen = None
        self._export_ready_at = 0.
        self._exported_page = None
        self.overlay_state = OverlayState(hold_until_next=True)
        self.regions = self.overlay_state.rendered
        self.active_generation, self.capture_region = -1, None
        self.status = tk.StringVar(value=self.tr(ui_source('Ready · On-screen translation')))
        self.metric = tk.StringVar(value=self.tr(ui_source('Recognition not started')))
        self.object_metric = tk.StringVar(value=self.tr(ui_source('Tracked 0 · Translations shown 0')))
        self.show_setup = bool(show_setup)
        self.api_dialog = None
        self.import_dialog = None
        self.import_busy = False
        self._closing = False
        self.agreement_accepted = (self.config.get('agreement_version') == AGREEMENT_VERSION
                                   and bool(self.config.get('agreement_accepted_at')))
        self.agreement_checked = tk.BooleanVar(value=self.agreement_accepted)
        self.has_api_key = str(self.config.get('api_key') or '').strip().upper() not in {'','YOUR_API_KEY'}
        initial_offline = not self.backend_ready or (local_endpoint(self.config['base_url']) and bool(self.config.get('offline_only')))
        self.config['offline_only'] = initial_offline
        self.config['aggressive_mode']=False  # Retired mode never controls the AI route.
        self.offline_only = tk.BooleanVar(value=initial_offline)
        self.manual_mode_text = tk.StringVar()
        self.api_slot_hint = tk.StringVar()
        self.source = tk.StringVar(value=self.tr(translation_language_name(self.config.get('source_lang'), ui_source('Japanese'))))
        self.target = tk.StringVar(value=self.tr(translation_language_name(self.config.get('target_lang'), ui_source('Simplified Chinese'))))
        self.game = tk.StringVar(value=self.config.get('last_profile') or self.config.get('game') or '')
        self.context = tk.StringVar(value=self.config.get('context_note') or '')
        self.profile_summary = tk.StringVar()
        self._selected_profile_name = self.game.get().strip()
        self._saved_profile_notes = self.context.get().strip()
        self._saved_profile_languages = (self.config.get('source_lang'), self.config.get('target_lang'))
        self._profile_loading = False
        self._profile_save_after = None
        self.profile_dialog = None
        self.hotkey = None
        self.toggle_hotkey = None
        self.hotkey_hint=tk.StringVar(value=self.tr(ui_source('{key} · Retranslate current screen')).format(
            key=self.config.get('retranslate_hotkey','Ctrl+Alt+R')) if self.config.get('retranslate_hotkey_enabled',True) else self.tr(ui_source('Retranslation shortcut disabled')))
        self.popup_guard = ComboboxPopupGuard(self.root)
        self.target_window = None
        self._game_process = None
        self._next_process_check = 0.
        self._window_refresh_id=0
        self._window_scan_pending=False
        self._run_status_error = False
        self._next_target_status = 0
        self._capture_region_unavailable = False
        self._last_ocr_line_count = None
        self._gpu_warm_core=None
        self._gpu_warm_busy=False
        self.manual_busy = False
        self._manual_lock = threading.Lock()
        self._manual_pending = None
        self._manual_event_queued = False
        self.next_stats_update = 0
        self.scope_controls = []
        self._style()
        self._build()
        self._sync_mode_labels()
        self._refresh_mode_control()
        self.status.set(self.tr(f'\u5c31\u7eea · {self._mode_name()}'))
        self.refresh_windows()
        self.refresh_profiles()
        self.restore_profile()
        self.context.trace_add('write', self._queue_profile_save)
        self.apply_ui_language(self.ui_language)
        if self.show_setup:self._configure_hotkey()
        self.root.after(40, self.drain)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        if self.show_setup:self.root.after_idle(self.show_initial_setup)
        if self.show_setup:self.root.after(250,self._prepare_cuda)
        if self.show_setup:self.root.after(2000,self._scan_windows_periodically)

    def tr(self, value):
        return translate(value, self.ui_language)

    def apply_ui_language(self, code):
        if code not in SUPPORTED:raise UIValidationError(ui_source('Choose Simplified Chinese, English, or Japanese for the interface.'))
        self.ui_language = code
        localize_widgets(self.root, code)
        if self.windows_box.current() < 0:
            self.windows_box.set(self.tr(ui_source('Choose a game window')))
        self.feature_panel.theme_fields.localize()
        # Source/target use localized display aliases with stable language codes.
        for control, _ in self.scope_controls:
            if isinstance(control, ttk.Combobox):
                values=tuple(control.cget('values'))
                if values and all(LANGUAGES.get(value) is not None for value in values):
                    control.configure(values=[self.tr(label) for label in LANGUAGES])
        self.source.set(self.tr(self.source.get()));self.target.set(self.tr(self.target.get()))
        self.settings_panel.app_language_var.set(next(label for label,value in INTERFACE_LANGUAGE_LABELS.items() if value==code))
        self.settings_panel.ocr_mode_box.configure(values=[self.tr(label) for label in OCR_MODE_LABELS])
        self.settings_panel.ocr_mode_var.set(self.tr(self.settings_panel.ocr_mode_var.get()))
        self.settings_panel.sampling_mode_box.configure(values=[self.tr(label) for label in SAMPLING_MODE_LABELS])
        self.settings_panel.sampling_mode_var.set(self.tr(self.settings_panel.sampling_mode_var.get()))
        self.settings_panel.vision_mode_box.configure(values=[self.tr(label) for label in VISION_MODE_LABELS])
        self.settings_panel.vision_mode_var.set(self.tr(self.settings_panel.vision_mode_var.get()))
        for owner, names in ((self, ('status','metric','object_metric','manual_mode_text','api_slot_hint','agreement_status','manual_count','hotkey_hint')),
                             (self.settings_panel, ('message','preview_hint','hotkey_status')),
                             (self.api_dialog, ('error','key_hint','editing_hint')),
                             (self.import_dialog, ('message',))):
            if owner is not None:
                for name in names:
                    var=getattr(owner,name,None)
                    if var is not None:var.set(self.tr(var.get()))
        self.agreement_text.configure(state='normal')
        self.agreement_text.delete('1.0','end')
        self.agreement_text.insert('1.0',agreement_text(code))
        self.agreement_text.configure(state='disabled')
        self.settings_panel.update_preview()
        self.settings_panel.cuda_controls.refresh()
        self.resource_usage.draw()
        ttk.Style(self.root).configure('Title.TLabel',font=(self.ui_font,19 if code=='en' else 24,'bold'))
        self._sync_agreement_gate()

    def open_manual(self):
        name={'en':'PROJECT_MANUAL.en.html','ja':'PROJECT_MANUAL.ja.html'}.get(self.ui_language,'PROJECT_MANUAL.html')
        manual=ROOT/'docs'/name
        if not manual.is_file():
            self.status.set(self.tr(ui_source('The bundled manual is missing. Check the complete release folder.')));return False
        try:os.startfile(str(manual))
        except OSError:
            self.status.set(self.tr(ui_source('The bundled manual is missing. Check the complete release folder.')));return False
        return True

    def _apply_colors(self, colors=None):
        self._style(colors)
        paper,surface,ink,_,accent,selection,border,_=self._ui_colors
        self.resource_usage.configure_colors(paper, surface, ink, accent,
                                             self.config.get('interface_theme', DEFAULT_THEME),
                                             self.config.get('chart_picture'), ROOT / 'assets/taiji.png',
                                             chart_style(self.config), self.config.get('chart_colors', {}).get(
                                                 self.config.get('interface_theme', DEFAULT_THEME), ()))
        todo=list(self.root.winfo_children())
        while todo:
            widget=todo.pop()
            todo.extend(widget.winfo_children())
            if isinstance(widget,tk.Text):
                widget.configure(bg=surface,fg=ink,insertbackground=accent,
                                 selectbackground=selection,selectforeground=ink,
                                 highlightbackground=border,highlightcolor=accent)
        primary, secondary = ((accent, '#78E3E5') if self.config.get('interface_theme', DEFAULT_THEME) == 'neon'
                              else (surface, mix(surface, accent, .3)))
        self.workbench_icons = load_icons(self.root, ink, primary, secondary, self._ui_colors[3])
        self._refresh_workbench()
        for canvas in (self.run_canvas,self.settings_canvas):
            canvas.configure(bg=surface)

    def _update_system_palette(self):
        self._system_palette_watch = None
        colors = palette(self.config)
        if colors != self._ui_colors:
            self._apply_colors(colors)
        self._system_palette_watch = self.root.after(1500, self._update_system_palette)

    def _apply_features(self):
        self._apply_colors()
        if self._system_palette_watch is not None:
            self.root.after_cancel(self._system_palette_watch)
            self._system_palette_watch = None
        theme = self.config.get('interface_theme', DEFAULT_THEME)
        if theme == 'system':
            self._system_palette_watch = self.root.after(1500, self._update_system_palette)
        if self.config.get('localization_enabled') is True:
            self.export_button.pack(side='left',padx=12)
        else:
            self.export_button.pack_forget()

    def save_initial_preferences(self, preferences):
        if not preferences:
            return
        self.config = self.config_store.save({**self.config, **preferences})
        for key in CUDA_FIELDS:
            if key in preferences:
                self.settings_panel.vars[key].set(self.config[key])
        self.settings_panel.cuda_controls.refresh()
        self.feature_panel.theme_fields.apply_config(self.config)
        self.feature_panel.apply_export_config(self.config)
        self._apply_features()

    def open_greeting(self):
        from .welcome import WelcomeSession
        try:
            if self.welcome_session is None:
                self.welcome_session = WelcomeSession(ROOT)
                self.root.after(150, self._check_greeting)
            self.welcome_session.open(self.ui_language)
        except OSError:
            if self.welcome_session:
                self.welcome_session.close()
                self.welcome_session = None
            self.status.set(self.tr(ui_source('The product introduction is missing.')))

    def _check_greeting(self):
        if not self.welcome_session:
            return
        if not self.welcome_session.finished.is_set():
            self.root.after(150, self._check_greeting)
            return
        self.welcome_session.close()
        self.welcome_session = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def open_localization_folder(self):
        if self.config.get('localization_enabled') is not True or not self._require_agreement():
            return
        try:
            path=Path(self.config.get('localization_folder') or ROOT)
            path.mkdir(parents=True,exist_ok=True)
            os.startfile(str(path))
        except OSError:
            self.status.set(self.tr('\u6c49\u5316\u6587\u672c\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u4fdd\u5b58\u76ee\u5f55\u3002'))

    def _target_prompt(self,title,message,*,confirm=False):
        if getattr(self,'_hotkey_starting',False):
            self._shortcut_popup_shown=True
            return shortcut_popup(self,title,message,confirm=confirm)
        if confirm:
            return messagebox.askyesno(title,message,parent=self.root)
        return messagebox.showinfo(title,message,parent=self.root)

    def _begin_localization_export(self,hwnd,pid,executable):
        prefs=export_preferences(self.config)
        name=self.game.get().strip() or PureWindowsPath(executable).stem or 'Game'
        self.export_session=((hwnd,pid,time.monotonic_ns()),name)
        self._export_seen=self._exported_page=None
        if self.exporter is None:
            self.exporter=Exporter(prefs['localization_folder'] or ROOT,prefs['localization_format'],
                                   prefs['localization_wait'],lambda:self.events.put(('export_error',0,None)))

    def _poll_localization_page(self):
        if not self.pipeline or self.pipeline.stop_event.is_set() or not self.export_session:
            return
        shot=self.overlay_state.completed_page()
        if shot is None:
            self._export_seen=None
            return
        signature=tuple((identity,item['revision'],line['_raw_translation']) for identity,item,line in shot)
        signature=(self.pipeline.generation,signature)
        if signature==self._exported_page:
            return
        now=time.monotonic()
        if signature!=self._export_seen:
            self._export_seen=signature
            self._export_ready_at=now+.22
            return
        if now<self._export_ready_at or now<getattr(self,'_shortcut_notice_until',0):
            return
        self._exported_page=signature
        row=self.target_window
        bounds=client_rect(row['hwnd'])
        if not bounds or not foreground(row['hwnd'],row['pid']):
            self._exported_page=None
            return
        # A single game-client screenshot serves every completed row on this page.
        x,y,w,h=bounds
        visible=visible_client_selections(None,bounds)
        if not visible:
            return
        x,y,w,h=visible
        if w*h>33_554_432:
            return
        try:
            from PIL import ImageGrab
            image=ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True)
        except (OSError,ValueError):
            self.events.put(('export_error',0,None))
            return
        if not foreground(row['hwnd'],row['pid']) or client_rect(row['hwnd'])!=bounds:
            image.close()
            self._exported_page=None
            return
        rows=[]
        for identity,item,line in shot:
            source=item['line']
            confidence=source.get('confidence') or 0
            score=(int(bool(source.get('_vision_verified') or source.get('_subtitle_read'))),confidence)
            rows.append(Line(identity,source['text'],line['_raw_translation'],self.pipeline._scope[2],score))
        self.exporter.offer(*self.export_session,rows,image)

    def _style(self, colors=None):
        self._ui_colors = colors if colors is not None else palette(self.config)
        PAPER,WHITE,INK,MUTED,RED,PALE,LINE,button_text = self._ui_colors
        shell_text = '#F4EBFF' if self.config.get('interface_theme', DEFAULT_THEME)=='neon' else INK
        self.root.configure(bg=PAPER)
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.', background=WHITE, foreground=INK, font=(self.ui_font, UI_BODY_SIZE),
                    bordercolor=LINE, lightcolor=WHITE, darkcolor=LINE, troughcolor=PAPER)
        s.configure('TFrame', background=WHITE)
        s.configure('Shell.TFrame', background=PAPER)
        s.configure('TLabel', background=WHITE, padding=0)
        s.configure('Shell.TLabel', background=PAPER, foreground=shell_text)
        s.configure('Title.TLabel', background=PAPER, foreground=shell_text,
                    font=(self.ui_font, 19 if self.ui_language=='en' else 24, 'bold'))
        s.configure('Heading.TLabel', font=(self.ui_font, 13, 'bold'))
        section_color = version_colors(__version__, WHITE)[0]
        s.configure('GameSection.TLabel', font=(self.ui_font, 13, 'bold'), foreground=section_color)
        s.configure('Hint.TLabel', foreground=MUTED)
        s.configure('TButton', padding=(14,9), background=WHITE, foreground=INK,
                    borderwidth=1, bordercolor=LINE, focusthickness=1, focuscolor=RED)
        s.map('TButton', background=[('disabled',PAPER),('pressed',PALE),('active',PALE)],
              foreground=[('disabled',MUTED)], bordercolor=[('focus',RED),('active',RED)])
        s.map('Region.TButton', background=[('disabled',mix(WHITE,INK,.14)),('pressed',PALE),('active',PALE)],
              foreground=[('disabled',MUTED)])
        s.configure('Accent.TButton', background=RED, foreground=button_text, bordercolor=RED)
        s.configure('Start.TButton', background=RED, foreground=button_text, bordercolor=RED,
                    font=(self.ui_font, 14, 'bold'), padding=(28,12))
        for name in ('Start.TButton','Accent.TButton'):
            s.map(name,background=[('disabled',mix(RED,WHITE,.5)),('pressed',mix(RED,INK,.10)),('active',mix(RED,WHITE,.1))],
                  foreground=[('disabled',button_text),('active',button_text)])
        s.configure('TEntry', fieldbackground=WHITE, foreground=INK, insertcolor=INK, padding=6)
        s.map('TEntry', bordercolor=[('focus',RED)])
        s.configure('TCombobox', fieldbackground=WHITE, background=WHITE, foreground=INK,
                    arrowcolor=RED, arrowsize=12, padding=5)
        s.map('TCombobox', fieldbackground=[('readonly',WHITE)], foreground=[('readonly',INK)],
              bordercolor=[('focus',RED)], selectbackground=[('readonly',WHITE)], selectforeground=[('readonly',INK)])
        s.configure('TNotebook', background=PAPER, borderwidth=0, tabmargins=(0,0,0,0))
        selected_bg = PAPER if self.config.get('interface_theme', DEFAULT_THEME) == 'neon' else INK
        selected_fg = shell_text if self.config.get('interface_theme', DEFAULT_THEME) == 'neon' else WHITE
        s.configure('Chosen.Region.TButton', background=selected_bg, foreground=selected_fg)
        s.map('Chosen.Region.TButton', background=[('active', selected_bg), ('!disabled', selected_bg)],
              foreground=[('!disabled', selected_fg)])
        s.configure('TNotebook.Tab', padding=(9,9), background=WHITE, foreground=INK, borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected',selected_bg),('active',PALE)],
              foreground=[('selected',selected_fg),('active',INK),('disabled',mix(shell_text,PAPER,.35))])
        s.configure('Treeview', background=WHITE, fieldbackground=WHITE, foreground=INK,
                    rowheight=32, borderwidth=0)
        s.configure('Treeview.Heading', background=PALE, foreground=INK, padding=(8,8), relief='flat')
        s.map('Treeview', background=[('selected',PALE)], foreground=[('selected',INK)])
        for style in ('TCheckbutton', 'TRadiobutton'):
            s.configure(style, background=WHITE, foreground=INK, focuscolor=RED)
            s.map(style, background=[('active',WHITE)], foreground=[('disabled',MUTED)],
                  indicatorbackground=[('selected',RED),('!selected',WHITE)], indicatorcolor=[('selected',RED)])
        s.configure('Vertical.TScrollbar', background=LINE, arrowcolor=MUTED, borderwidth=0, arrowsize=11)
        self.root.option_add('*TCombobox*Listbox.background', WHITE)
        self.root.option_add('*TCombobox*Listbox.foreground', INK)
        self.root.option_add('*TCombobox*Listbox.selectBackground', PALE)
        self.root.option_add('*TCombobox*Listbox.selectForeground', INK)
        self.root.option_add('*TCombobox*Listbox.font', (self.ui_font, UI_BODY_SIZE))

    def _hint(self, parent, text, **options):
        label=ttk.Label(parent,text=self.tr(text),style='Hint.TLabel',wraplength=760,**options)
        def wrap(event):
            padding=parent.tk.splitlist(parent.cget('padding'))
            horizontal=(parent.winfo_pixels(str(padding[0]))+
                        parent.winfo_pixels(str(padding[2] if len(padding)>2 else padding[0]))) if padding else 0
            label.configure(wraplength=max(160,event.width-horizontal-12))
        parent.bind('<Configure>',wrap,add='+')
        return label

    def _text(self,parent,**options):
        _,WHITE,INK,_,RED,PALE,LINE,_=self._ui_colors
        return tk.Text(parent,bg=WHITE,fg=INK,insertbackground=RED,selectbackground=PALE,
                       selectforeground=INK,relief='flat',font=(self.ui_font, UI_BODY_SIZE),
                       padx=12,pady=10,highlightthickness=1,highlightbackground=LINE,
                       highlightcolor=RED,wrap='word',**options)

    def _scroll_page(self,parent):
        scroll=ttk.Scrollbar(parent,orient='vertical');scroll.pack(side='right',fill='y')
        canvas=tk.Canvas(parent,bg=self._ui_colors[1],highlightthickness=0,yscrollcommand=scroll.set)
        canvas.pack(fill='both',expand=True);scroll.configure(command=lambda *args:self.popup_guard.yview(canvas,*args))
        body=ttk.Frame(canvas,padding=22)
        item=canvas.create_window(0,0,window=body,anchor='nw')
        def fit(event=None):
            # Let Tk recompute the natural height after labels wrap at a new
            # width. A forced height can become stale and clip the last button.
            canvas.itemconfigure(item,width=canvas.winfo_width())
            canvas.configure(scrollregion=canvas.bbox('all'))
        body.bind('<Configure>',fit);canvas.bind('<Configure>',fit)
        return canvas,body

    def _scroll_bindings(self,canvas,widget):
        if not isinstance(widget,(tk.Text,ttk.Combobox)):
            widget.bind('<MouseWheel>',lambda e:(self.popup_guard.yview_scroll(canvas,-int(e.delta/120),'units'),'break')[1])
        for child in widget.winfo_children():self._scroll_bindings(canvas,child)

    def _build(self):
        base = ttk.Frame(self.root, padding=(16,8),style='Shell.TFrame')
        base.pack(fill='both', expand=True)
        self.resource_usage = ResourceUsage(base, __version__, self.ui_font, self.tr,
            lambda: self._gpu_warm_busy or self._using_gpu_for_ocr(),
            lambda: self.config.get('cuda_enabled', True) and self.config.get('ocr_mode', 'auto') == 'auto')
        self.resource_usage.pack(fill='x', pady=(0, 8))
        # Reserve footer before the notebook consumes remaining height.
        footer=ttk.Frame(base,style='Shell.TFrame');footer.pack(side='bottom',fill='x',pady=(14,0))
        footer_status = ttk.Frame(footer, style='Shell.TFrame')
        footer_status.pack(side='left', fill='both', expand=True)
        settings_actions = ttk.Frame(footer, style='Shell.TFrame')
        self.footer_text = tk.StringVar()
        self.status.trace_add('write', self._update_footer)
        status=ttk.Label(footer_status,textvariable=self.footer_text,style='Shell.TLabel')
        status.pack(anchor='w')
        footer_status.bind('<Configure>',lambda e:status.configure(wraplength=e.width),add='+')
        ttk.Label(footer_status,textvariable=self.metric,style='Shell.TLabel',font=(self.ui_font,UI_SMALL_SIZE)).pack(anchor='w',pady=(6,3))
        lower=ttk.Frame(footer_status,style='Shell.TFrame');lower.pack(fill='x')
        ttk.Label(lower,textvariable=self.object_metric,style='Shell.TLabel',font=(self.ui_font,UI_SMALL_SIZE)).pack(side='left')
        ttk.Label(lower,text=self.tr(f'{__version__} · Windows x64'),style='Shell.TLabel',font=(self.ui_font,UI_SMALL_SIZE)).pack(side='right')
        self.tabs=ttk.Notebook(base);self.tabs.pack(fill='both',expand=True)
        run_shell=ttk.Frame(self.tabs)
        terms,manual,self.agreement_tab=[ttk.Frame(self.tabs,padding=22) for _ in range(3)]
        for frame,text in zip((run_shell,terms,manual,self.agreement_tab),(ui_source('Game translation'),ui_source('Glossary'),ui_source('Translate text manually'),ui_source('User agreement'))):
            self.tabs.add(frame,text=self.tr(text))
        self.run_action_bar=ttk.Frame(run_shell,padding=(22,12))
        self.run_action_bar.pack(side='bottom',fill='x')
        self.start_button=ttk.Button(self.run_action_bar,text=self.tr(ui_source('Start translation')),style='Start.TButton',command=self.start)
        self.start_button.pack(side='right')
        self.stop_button=ttk.Button(self.run_action_bar,text=self.tr(ui_source('Stop and show original')),command=self.stop)
        self.stop_button.pack(side='right',padx=(10,14))
        ttk.Label(self.run_action_bar,textvariable=self.hotkey_hint,style='Hint.TLabel',font=(self.ui_font,UI_SMALL_SIZE)).pack(side='left')
        self.run_canvas,run=self._scroll_page(run_shell)
        self._run_ui(run);self._term_ui(terms);self._manual_ui(manual);self._agreement_ui(self.agreement_tab)
        self.settings_tab=ttk.Frame(self.tabs);self.tabs.add(self.settings_tab,text=self.tr(ui_source('Settings')))
        self.settings_canvas,settings_body=self._scroll_page(self.settings_tab)
        api_entry=ttk.LabelFrame(settings_body,text=self.tr(ui_source('API settings')),padding=14)
        api_entry.pack(fill='x',pady=(0,16))
        self.api_settings_button=ttk.Button(api_entry,text=self.tr(ui_source('API connections (3 slots)')),style='Accent.TButton',command=self.show_api_settings)
        self.api_settings_button.pack(side='right')
        ttk.Label(api_entry,textvariable=self.api_slot_hint).pack(side='left')
        self.export_button=ttk.Button(self.run_action_bar,text=self.tr(ui_source('Open export folder')),command=self.open_localization_folder)
        self.feature_panel=FeaturePanel(self,settings_body)
        self.settings_panel=SettingsPanel(self,settings_body,settings_actions)
        self._apply_features()
        ttk.Button(settings_body,text=self.tr(ui_source('Open user guide')),command=self.open_manual).pack(anchor='w',pady=(12,0))
        ttk.Button(settings_body, text=self.tr(ui_source('Welcome tour')),
                   command=self.open_greeting).pack(anchor='w', pady=(8, 0))
        self._scroll_bindings(self.settings_canvas,self.settings_canvas)
        # All controls and logs remain reachable at the minimum size.
        self._scroll_bindings(self.run_canvas,self.run_canvas)
        self.popup_guard.register_tree(self.root)
        def tab_changed(_):
            self._refresh_workbench()
            self.popup_guard.close_popups()
            if self.tabs.select() == str(self.settings_tab):
                settings_actions.pack(side='right', anchor='s', padx=(16, 0), before=footer_status)
            else:
                settings_actions.pack_forget()

        self.tabs.bind('<<NotebookTabChanged>>', tab_changed, add='+')
        self._sync_agreement_gate()

    def _run_ui(self,f):
        ttk.Label(f,text=self.tr(ui_source('Game and languages')),style='GameSection.TLabel').pack(anchor='w')
        form = ttk.Frame(f)
        form.pack(fill='x', pady=(8, 12))
        form.columnconfigure(0, weight=2)
        for col in (1, 2):
            form.columnconfigure(col, weight=1)
        def field(parent, col, label, widget):
            ttk.Label(parent, text=self.tr(ui_source(label))).grid(row=0, column=col, sticky='w', pady=(0, 4))
            widget.grid(row=1, column=col, sticky='ew', padx=(0, 8))
        window_field = ttk.Frame(form)
        self.windows_box = ttk.Combobox(window_field, state='readonly', width=17)
        self.windows_box.pack(side='left', fill='x', expand=True)
        ttk.Button(window_field, text=self.tr(ui_source('Refresh windows')), command=self.refresh_windows).pack(side='left', padx=(4, 0))
        field(form, 0, 'Game window', window_field)
        for col, (label, var) in enumerate([('Source language', self.source), ('Translate to', self.target)], 1):
            control = ttk.Combobox(form, textvariable=var, values=list(LANGUAGES), state='readonly', width=12)
            field(form, col, label, control)
            self.scope_controls.append((control, 'readonly'))
            control.bind('<<ComboboxSelected>>', self.translation_language_changed)
        context = ttk.Frame(f)
        context.pack(fill='x', pady=(0, 12))
        context.columnconfigure(0, weight=1)
        context.columnconfigure(1, weight=2)
        profile = ttk.Frame(context)
        self.profile_box = ttk.Combobox(profile, textvariable=self.game, width=15, postcommand=self.refresh_profiles)
        self.profile_box.pack(side='left', fill='x', expand=True)
        self.profile_box.bind('<<ComboboxSelected>>', lambda _: self.profile_changed(reopen=True))
        self.profile_box.bind('<FocusOut>', self.profile_changed)
        self.profile_box.bind('<Return>', lambda _: self.profile_changed(reopen=True))
        self.clear_profile_button = ttk.Button(profile, text=self.tr(ui_source('Manage profiles')), command=self.open_profiles)
        self.clear_profile_button.pack(side='left', padx=(4, 0))
        field(context, 0, 'Game profiles', profile)
        notes = ttk.Frame(context)
        context_entry = ttk.Entry(notes, textvariable=self.context, width=14)
        context_entry.pack(side='left', fill='x', expand=True)
        save_context = ttk.Button(notes, text=self.tr(ui_source('Save')), command=self.save_profile_context)
        save_context.pack(side='right', padx=(4, 0))
        field(context, 1, 'Translation notes', notes)
        self.scope_controls.extend(((self.profile_box, 'normal'), (self.clear_profile_button, 'normal'),
                                    (context_entry, 'normal'), (save_context, 'normal')))
        context = ttk.Frame(f)
        context.pack(fill='x')
        self.context_summary_row = ttk.Frame(context)
        ttk.Label(self.context_summary_row, text=self.tr(ui_source('Latest profile summary'))).pack(side='left', padx=(0, 10))
        ttk.Entry(self.context_summary_row, textvariable=self.profile_summary, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Label(f,text=self.tr(ui_source('Translation area')),style='GameSection.TLabel').pack(anchor='w')
        self._hint(f,ui_source('Play in windowed or borderless mode. Switch away from the game to hide the translation.')).pack(anchor='w',pady=(8,10))
        row=ttk.Frame(f);row.pack(fill='x',pady=(0,8))
        self.select_region_button = ttk.Button(row, text=self.tr(ui_source('Select areas')),
                                               style='Region.TButton', command=self.select_region)
        self.full_region_button = ttk.Button(row, text=self.tr(ui_source('Entire game window')),
                                            style='Region.TButton', command=self.full_region)
        self.lightweight_var = tk.BooleanVar(value=False)
        self.lightweight_button = ttk.Button(row, text=self.tr(ui_source('Lightweight mode')),
                                             command=self._toggle_lightweight)
        for col, button in enumerate((self.select_region_button, self.full_region_button, self.lightweight_button)):
            row.columnconfigure(col, weight=1, uniform='scope')
            button.grid(row=0, column=col, sticky='ew', padx=(0, 6))
        self.region_label = ttk.Label(f, style='Hint.TLabel')
        self.region_label.pack(anchor='w')
        self.log=self._text(f,height=3);self.log.pack(fill='both',expand=True,pady=(12,0))
        self.log.insert('end',self.tr(ui_source('Ready. Translation and coverage appear progressively. AI generates new translations using saved terms and context as references.\n')))

    def _term_ui(self,f):
        ttk.Label(f,text=self.tr(ui_source('Glossary')),style='Heading.TLabel').pack(anchor='w')
        self._hint(f,ui_source('Save preferred wording as AI terminology reference. The model translates in context; there is no local substitution or guaranteed exact wording.')).pack(anchor='w',pady=(8,5))
        self._hint(f,ui_source('Use the game and language pair from Screen Translation. Older terms remain as AI references; open the archive for full translations and context.')).pack(anchor='w',pady=(0,16))
        row=ttk.Frame(f);row.pack(fill='x',pady=(0,12))
        self.term_shared=tk.BooleanVar(value=False)
        self.term_shared_toggle=ttk.Checkbutton(row,text=self.tr(ui_source('Show shared dictionary (all games)')),variable=self.term_shared,command=self.refresh_terms)
        self.term_shared_toggle.pack(side='left')
        self.import_button=ttk.Button(row,text=self.tr(ui_source('Import dictionary…')),command=self.open_dictionary_import)
        self.import_button.pack(side='right')
        self.history_button=ttk.Button(row,text=self.tr(ui_source('Translation and context archive')),command=self.open_translation_history)
        self.history_button.pack(side='right',padx=8)
        self.scope_controls.append((self.history_button,'normal'))
        self.scope_controls.extend([(self.term_shared_toggle,'normal'),(self.import_button,'normal')])
        self.term_source,self.term_target=tk.StringVar(),tk.StringVar()
        editor=ttk.Frame(f);editor.pack(fill='x');editor.columnconfigure((0,1),weight=1,uniform='terms')
        for column,(label,var) in enumerate(((ui_source('Original text'),self.term_source),(ui_source('Term translation'),self.term_target))):
            ttk.Label(editor,text=self.tr(label)).grid(row=0,column=column,sticky='w',pady=(0,6))
            ttk.Entry(editor,textvariable=var).grid(row=1,column=column,sticky='ew',padx=(0,12) if column==0 else (0,0))
        row=ttk.Frame(f);row.pack(fill='x',pady=14)
        save=ttk.Button(row,text=self.tr(ui_source('Save terminology reference')),command=self.save_term,style='Accent.TButton');save.pack(side='left')
        refresh=ttk.Button(row,text=self.tr(ui_source('Refresh list')),command=self.refresh_terms);refresh.pack(side='left',padx=8)
        remove=ttk.Button(row,text=self.tr(ui_source('Delete selected term')),command=self.delete_term);remove.pack(side='left')
        self.scope_controls.extend([(save,'normal'),(refresh,'normal'),(remove,'normal')])
        self.term_scope_status=tk.StringVar()
        self._term_view_scope=None
        ttk.Label(f,textvariable=self.term_scope_status,style='Hint.TLabel',wraplength=700).pack(anchor='w',pady=(0,6))
        table=ttk.Frame(f);table.pack(fill='both',expand=True)
        scrollbar=ttk.Scrollbar(table,orient='vertical');scrollbar.pack(side='right',fill='y')
        self.term_tree=ttk.Treeview(table,columns=('source','target'),show='headings',height=5,yscrollcommand=scrollbar.set)
        self.term_tree.heading('source',text=self.tr(ui_source('Original text')));self.term_tree.heading('target',text=self.tr(ui_source('Term translation')))
        self.term_tree.column('source',width=260,anchor='w');self.term_tree.column('target',width=320,anchor='w')
        self.term_tree.pack(fill='both',expand=True);scrollbar.configure(command=self.term_tree.yview)
        self.term_tree.bind('<<TreeviewSelect>>',self._load_selected_term)
        self._hint(f,ui_source('Shows up to 200 shared terms. Game terms take priority. Changes apply to later AI requests; complete translations are in the profile history.')).pack(anchor='w',pady=(12,0))

    def _manual_ui(self,f):
        ttk.Label(f,text=self.tr(ui_source('Translate text manually')),style='Heading.TLabel').pack(anchor='w')
        self._hint(f,ui_source('Uses the game profile and source/target languages from Screen translation, including the same translation dictionary.')).pack(anchor='w',pady=(8,16))
        ttk.Label(f,text=self.tr(ui_source('Original text'))).pack(anchor='w')
        self.manual_input=self._text(f,height=5);self.manual_input.pack(fill='x',pady=(6,6))
        self.manual_count=tk.StringVar()
        ttk.Label(f,textvariable=self.manual_count,style='Hint.TLabel').pack(anchor='w',pady=(0,8))
        row=ttk.Frame(f);row.pack(fill='x')
        self.manual_button=ttk.Button(row,text=self.tr(ui_source('Translate text')),command=self.manual_translate,style='Accent.TButton')
        self.manual_button.pack(side='left')
        ttk.Label(row,textvariable=self.manual_mode_text,style='Hint.TLabel').pack(side='left',padx=14)
        ttk.Label(f,text=self.tr(ui_source('Translation (select to copy)'))).pack(anchor='w',pady=(16,6))
        self.manual_output=self._text(f,height=3);self.manual_output.pack(fill='both',expand=True)
        self.manual_output.configure(state='disabled')
        self.manual_input.bind('<Control-Return>',lambda e:(self.manual_translate(),'break')[1])
        self.manual_input.bind('<<Modified>>',self._update_manual_count)
        self._update_manual_count()


    def _agreement_ui(self, parent):
        ttk.Label(parent,text=self.tr(AGREEMENT_TITLE),style='Heading.TLabel').pack(anchor='w')
        ttk.Label(parent,text=self.tr(f'\u534f\u8bae\u7248\u672c\uff1a{AGREEMENT_VERSION}'),style='Hint.TLabel').pack(anchor='w',pady=(6,10))
        footer=ttk.Frame(parent);footer.pack(side='bottom',fill='x',pady=(12,0))
        self.agreement_status=tk.StringVar(value=self.tr(ui_source('Accepted · the current agreement is already accepted.') if self.agreement_accepted else ui_source('Read the agreement. Accept to use the application, or decline and exit.')))
        ttk.Label(footer,textvariable=self.agreement_status,style='Hint.TLabel',wraplength=700).pack(anchor='w',pady=(0,8))
        self.agreement_checkbox=ttk.Checkbutton(footer,text=self.tr(ui_source('I have read and agree to the terms above')),variable=self.agreement_checked,
                                              command=self._refresh_agreement_button)
        self.agreement_checkbox.pack(anchor='w')
        row=ttk.Frame(footer);row.pack(fill='x',pady=(10,0))
        self.accept_agreement_button=ttk.Button(row,text=self.tr(ui_source('Agree and continue')),command=self.accept_agreement,style='Accent.TButton')
        self.accept_agreement_button.pack(side='left')
        self.decline_agreement_button=ttk.Button(row,text=self.tr(ui_source('Exit') if self.agreement_accepted else ui_source('Decline and exit')),command=self.close)
        self.decline_agreement_button.pack(side='right')
        content=ttk.Frame(parent);content.pack(fill='both',expand=True)
        scroll=ttk.Scrollbar(content,orient='vertical');scroll.pack(side='right',fill='y')
        self.agreement_text=self._text(content,height=10,yscrollcommand=scroll.set)
        self.agreement_text.pack(fill='both',expand=True);scroll.configure(command=self.agreement_text.yview)
        self.agreement_text.insert('1.0',AGREEMENT_TEXT);self.agreement_text.configure(state='disabled')
        self._refresh_agreement_button()

    def _refresh_agreement_button(self):
        accepted=bool(self.agreement_accepted)
        if accepted:self.agreement_checked.set(True)
        self.agreement_checkbox.configure(state='disabled' if accepted else 'normal')
        self.accept_agreement_button.configure(text=self.tr(ui_source('Accepted') if accepted else ui_source('Agree and continue')),
            state='normal' if not accepted and self.agreement_checked.get() and not self._mode_busy() else 'disabled')

    def _sync_agreement_gate(self):
        """An accepted agreement stays accepted; new users can only agree or exit."""
        for tab in self.tabs.tabs():
            is_agreement=tab==str(self.agreement_tab)
            self.tabs.tab(tab,state='normal' if self.agreement_accepted or is_agreement else 'disabled')
        self.tabs.tab(self.agreement_tab,text=self.tr(ui_source('Agreement · accepted') if self.agreement_accepted else ui_source('User agreement')))
        self.agreement_status.set(self.tr(ui_source('Accepted · the current agreement is already accepted.') if self.agreement_accepted else ui_source('Read the agreement. Accept to use the application, or decline and exit.')))
        self.decline_agreement_button.configure(text=self.tr(ui_source('Exit') if self.agreement_accepted else ui_source('Decline and exit')))
        if not self.agreement_accepted:self.tabs.select(self.agreement_tab)
        self._refresh_agreement_button()

    def _require_agreement(self):
        if self.show_setup and (self.setup_dialog or not self.agreement_accepted
                                or self.config.get('app_language_selected') is not True):
            self.show_initial_setup()
            return False
        if self.agreement_accepted:return True
        self.tabs.select(self.agreement_tab)
        self.status.set(self.tr(ui_source('Read and accept the user agreement first.')))
        return False

    def show_initial_setup(self):
        if self.setup_dialog:
            self.setup_dialog.activate()
            return self.setup_dialog
        if self.show_setup and (self.config.get('app_language_selected') is not True
                                or not self.agreement_accepted
                                or 'interface_theme' not in self.config
                                or self.config.get('localization_setup_complete') is not True):
            self.setup_dialog = InitializationDialog(self)
            return self.setup_dialog
        if not self._require_agreement():return
        if not self.config.get('api_setup_complete') or not self.backend_ready:
            self.show_api_settings()
        elif self.show_setup:self._prepare_cuda()
        if getattr(self,'_initial_vision_note',''):
            self.status.set(self.tr(self._initial_vision_note))

    def accept_agreement(self, *, continue_setup=True):
        if self.agreement_accepted:
            self._sync_agreement_gate();return True
        if not self.agreement_checked.get():
            self.agreement_status.set(self.tr(ui_source('Check the agreement box first.')));return False
        if self._mode_busy():
            self.agreement_status.set(self.tr(ui_source('Stop translation and wait for pending requests to finish.')));return False
        updated={**self.config,'agreement_version':AGREEMENT_VERSION,
                 'agreement_accepted_at':datetime.now(timezone.utc).isoformat()}
        try:self.config=self.config_store.save(updated)
        except Exception as error:
            self.agreement_status.set(self.tr(self.settings_error_message(error)));return False
        self.agreement_accepted=True
        self.agreement_checked.set(True)
        self._sync_agreement_gate();self._refresh_mode_control()
        if self.show_setup:self._configure_hotkey()
        self.tabs.select(0)
        self.status.set(self.tr(ui_source('Agreement accepted.')))
        if self.show_setup and continue_setup:self.show_initial_setup()
        return True

    def show_api_settings(self):
        if not self._require_agreement():return None
        if self._mode_busy():
            self.status.set(self.tr(ui_source('Stop translation and wait for pending requests before changing API settings.')));return None
        if self.api_dialog and self.api_dialog.window.winfo_exists():
            return self.api_dialog
        self.api_dialog=ApiSettingsDialog(self)
        return self.api_dialog

    @staticmethod
    def settings_error_message(error):
        if isinstance(error,(ConfigStoreError,UIValidationError,TuningValidationError,SecurityValidationError,TranslationError)):
            return str(error)[:500]
        return ui_source('Could not complete the operation. Check your settings and write access to the data folder, then try again.')

    @property
    def backend_ready(self):
        return self.has_api_key or local_endpoint(self.config.get('base_url'))

    def save_api_settings(self, base_url, model, *, api_key=None, offline_only=False, slot=None, local_provider=None):
        if not self.agreement_accepted:raise UIValidationError(ui_source('Read and accept the user agreement first.'))
        if self._mode_busy():raise UIValidationError(ui_source('Stop translation and wait for pending requests to finish.'))
        slot = self.config.get('active_api_slot',0) if slot is None else slot
        if type(slot) is not int or not 0 <= slot < 3:
            raise UIValidationError(ui_source('Select API slot 1, 2, or 3.'))
        base_url=validate_api_url(base_url.strip(' ') if isinstance(base_url,str) else base_url)
        model=validate_model(model)
        if api_key is not None:api_key=normalize_api_key(api_key)
        saved_slot=self.config['api_slots'][slot]
        if (api_key is None and saved_slot['has_api_key']
                and base_url != validate_api_url(saved_slot['base_url'])):
            if local_endpoint(base_url):
                api_key = ''
            else:
                raise UIValidationError(ui_source('The API address changed. Enter a key for the new address before saving. Leaving it blank only preserves a key for the same address.'))
        selected_has_key=bool(api_key) if api_key is not None else bool(self.config['api_slots'][slot]['has_api_key'])
        if not offline_only and not (selected_has_key or local_endpoint(base_url)):
            raise UIValidationError(ui_source('Enter an API key, or configure it later and browse saved records.'))
        saved=self.config_store.save_api_slot(slot,base_url,model,api_key=api_key,
            activate=True,offline_only=bool(offline_only),local_provider=local_provider)
        if saved.get('vision_ocr_mode') in (None, 'hardware'):
            saved['vision_ocr_mode'] = self.config['vision_ocr_mode']
        if self.engine:self.engine.close();self.engine=None
        self.config=saved
        self.has_api_key=bool(str(saved.get('api_key') or '').strip())
        self.offline_only.set(bool(saved.get('offline_only')) or not self.backend_ready)
        self._sync_mode_labels();self._refresh_mode_control()
        self.status.set(self.tr(f'\u69fd\u4f4d {slot+1} \u5df2\u542f\u7528 · {self._mode_name()}'))
        if self.show_setup:self.root.after(250,self._prepare_cuda)
        return saved

    def _mode_name(self):
        if self.offline_only.get():
            return ui_source('API not configured · Browse archives')
        return self.tr(ui_source('Translation backend: LLM ({model})')).format(model=self.config['model'])

    def _update_footer(self, *_):
        message = self.status.get()
        mode = self._mode_name()
        if not self.offline_only.get() and mode not in message:
            message = f'{message} · {mode}' if message else mode
        self.footer_text.set(message)

    def current_warmup_scope(self):
        return warmup_identity(self.game.get(),(self.target_window or {}).get('process_path',''))

    def _sync_mode_labels(self):
        self.manual_mode_text.set(self.tr(self._mode_name()))
        self.api_slot_hint.set(self.tr(f'\u5f53\u524d\u69fd\u4f4d {self.config.get("active_api_slot",0)+1} · '+
                               (ui_source('Reconfiguration required') if self.config_store.credential_error else ui_source('Configured') if self.backend_ready else ui_source('Key not set'))))

    def _mode_busy(self,stats=None):
        if getattr(self,'_gpu_warm_busy',False):return True
        if self.pipeline or self.manual_busy or self.import_busy:
            return True
        if self.core and getattr(self.core,'pending',False) is True:return True
        if self.engine:
            if stats is None:stats=self.engine.get_stats()
            return bool(stats.get('in_flight',0))
        return False

    def _refresh_mode_control(self,stats=None):
        busy=self._mode_busy(stats) or (self.profile_dialog is not None and self.profile_dialog.winfo_exists())
        if hasattr(self,'offline_toggle'):
            self.offline_toggle.configure(state='disabled' if busy or not self.agreement_accepted else 'normal')
        if hasattr(self,'api_settings_button'):
            self.api_settings_button.configure(state='disabled' if busy or not self.agreement_accepted else 'normal')
        if self.api_dialog:self.api_dialog.refresh_busy()
        if hasattr(self,"feature_panel"):self.feature_panel.refresh(busy or not self.agreement_accepted)
        if hasattr(self,'settings_panel'):self.settings_panel.refresh(busy or not self.agreement_accepted)
        if hasattr(self,'start_button'):
            self.start_button.configure(state='disabled' if busy or not self.agreement_accepted else 'normal')
        if hasattr(self,'manual_input'):
            self.manual_input.configure(state='disabled' if self.manual_busy or not self.agreement_accepted else 'normal')
        if hasattr(self,'manual_button'):
            self.manual_button.configure(state='disabled' if busy or not self.agreement_accepted else 'normal')
        if hasattr(self,'accept_agreement_button'):self._refresh_agreement_button()
        for control,idle_state in self.scope_controls:
            control.configure(state='disabled' if busy or not self.agreement_accepted else idle_state)

    def change_translation_mode(self):
        previous=bool(self.config.get('offline_only',False))
        if not self._require_agreement():
            self.offline_only.set(previous);return
        if self._mode_busy():
            self.offline_only.set(previous)
            self.status.set(self.tr(ui_source('Stop translation and wait for pending requests before switching modes.')))
            self._refresh_mode_control()
            return
        if not self.backend_ready and not self.offline_only.get():
            self.offline_only.set(True)
            self.show_api_settings()
            return
        selected=bool(self.offline_only.get())
        if selected!=previous and self.engine:
            self.engine.close()
            self.engine=None
        self.config['offline_only']=selected
        self._sync_mode_labels()
        self._refresh_mode_control()
        self.status.set(self.tr(f'\u5c31\u7eea · {self._mode_name()} · '+(ui_source('Keep unmatched original text') if selected else ui_source('Translate new text online'))))

    def get_engine(self):
        if self.engine is None:
            config={**self.config,'offline_only':bool(self.offline_only.get()) or not self.backend_ready}
            self.engine=TranslationEngine(config,ROOT/'data/codebook.sqlite3')
            self.engine.on_backend_failure = lambda engine, code: self.events.put(('backend_failure', 0, (engine, code)))
        return self.engine

    def _show_backend_failure(self, engine, code):
        if self._closing or engine is not self.engine:
            return
        now = time.monotonic()
        key = (engine.base_url, engine.model, code)
        self._backend_alerts = {k:t for k,t in self._backend_alerts.items() if now - t < 60}
        if self._backend_dialog_open or key in self._backend_alerts:
            return
        self._backend_dialog_open = True
        title = self.tr(ui_source('Translation service unavailable'))
        detail = self.tr(ui_source('Model: {model}\nError code: {code}')).format(model=engine.model, code=code)
        try:
            messagebox.showerror(title, detail, parent=self.root)
        finally:
            self._backend_dialog_open = False
            self._backend_alerts[key] = time.monotonic()

    def save_settings(self, values=None):
        hotkey_changed=False
        try:
            if not self.agreement_accepted:raise UIValidationError(ui_source('Read and accept the user agreement first.'))
            if self._mode_busy():raise UIValidationError(ui_source('Stop translation or wait for the dictionary operation before saving settings.'))
            edited={**self.settings_panel.values(),**self.feature_panel.values()} if values is None else values
            requested={**self.config,**edited}
            updated=validate_tuning(requested)
            features={**validate_theme(requested),**export_preferences(requested)}
            if 'localization_enabled' in edited:features['localization_setup_complete']=True
            if self.show_setup and not self._configure_hotkey(updated):
                self.settings_panel.message.set(self.tr(ui_source('Shortcut not saved. Change the combination or disable it.')));return False
            hotkey_changed=self.show_setup
            before=dict(self.config)
            saved=self.config_store.save({**self.config,**updated,**features,'app_language_selected':True,'offline_only':bool(self.offline_only.get()),
                'source_lang':LANGUAGES[self.source.get()], 'target_lang':LANGUAGES[self.target.get()]})
        except Exception as error:
            if hotkey_changed:self._configure_hotkey(self.config)
            self.settings_panel.message.set(self.tr(self.settings_error_message(error)));return False
        self.config=saved
        if self.exporter and any(before.get(key)!=saved[key] for key in export_preferences(saved)):
            self.exporter.close()
            self.exporter=None
        self.feature_panel.apply_export_config(saved)
        self.feature_panel.theme_fields.apply_config(saved)
        self._apply_features()
        engine_changed = any(before.get(name, TUNING_DEFAULTS.get(name)) != value
                             for name, value in updated.items() if name not in APPEARANCE_FIELDS)
        if self.engine and engine_changed:self.engine.close();self.engine=None
        if self.core and any(before.get(name,TUNING_DEFAULTS.get(name))!=saved[name]
                             for name in ('ocr_min_confidence','ocr_mode','vision_ocr_mode','vision_interval_ms','ocr_refine_workers',
                                          'cuda_enabled','cuda_memory_mb','cuda_quality')):
            self.core.close();self.core=None
        if getattr(self,'_gpu_warm_core',None) is not None and any(before.get(name,TUNING_DEFAULTS.get(name))!=saved[name]
                        for name in ('cuda_enabled','cuda_memory_mb','cuda_quality','ocr_mode')):
            self._gpu_warm_core.close();self._gpu_warm_core=None
        for name,value in updated.items():
            if name in self.settings_panel.vars:self.settings_panel.vars[name].set(value)
        self.settings_panel.app_language_var.set(next(label for label, code in INTERFACE_LANGUAGE_LABELS.items()
                                                     if code == updated['app_language']))
        self.settings_panel.ocr_mode_var.set(next(self.tr(label) for label,code in OCR_MODE_LABELS.items() if code==updated['ocr_mode']))
        self.settings_panel.sampling_mode_var.set(next(self.tr(label) for label,code in SAMPLING_MODE_LABELS.items()
                                                       if code==updated['sampling_mode']))
        self.settings_panel.vision_mode_var.set(next(
            self.tr(label) for label, code in VISION_MODE_LABELS.items() if code == updated['vision_ocr_mode']))
        self.apply_ui_language(updated['app_language'])
        self._sync_mode_labels();self._refresh_mode_control();self._update_manual_count()
        self.settings_panel.message.set(self.tr(ui_source('Saved. Interface language applies now; overlay appearance applies when translation restarts.')))
        self.status.set(self.tr(f'\u8bbe\u7f6e\u5df2\u4fdd\u5b58 · {self._mode_name()}'))
        if self.show_setup:self.root.after(250,self._prepare_cuda)
        return True

    def _configure_hotkey(self,config=None):
        updating=config is not None
        config=self.config if config is None else config
        if self.hotkey is None:
            self.hotkey=GlobalHotkey(lambda:self.events.put(('retranslate',0,None)))
        try:
            previous=self.hotkey.status
            state=self.hotkey.update(bool(config.get('retranslate_hotkey_enabled',True)) and self.agreement_accepted,
                                     config.get('retranslate_hotkey','Ctrl+Alt+R'))
            if state.error and updating:
                self.settings_panel.hotkey_status.set(self.tr(ui_source('Shortcut unavailable: {error}')).format(error=self.tr(state.error)));return False
            if self.toggle_hotkey is None:
                self.toggle_hotkey=GlobalHotkey(lambda:self.events.put(('toggle_translation',0,None)))
            toggle=self.toggle_hotkey.update(bool(config.get('toggle_hotkey_enabled',True)) and self.agreement_accepted,
                                             config.get('toggle_hotkey',DEFAULT_TOGGLE_HOTKEY))
            if toggle.error and updating:
                self.hotkey.update(previous.enabled,previous.shortcut)
                self.settings_panel.hotkey_status.set(self.tr(ui_source('Translation toggle unavailable: {error}')).format(error=self.tr(toggle.error)))
                return False
            if getattr(self,'lens_hotkey',None) is None:
                self.lens_hotkey=GlobalHotkey(lambda:self.events.put(('toggle_lightweight',0,None)))
            lens=self.lens_hotkey.update(self.agreement_accepted,'Ctrl+Alt+L')
            hints=[self.tr(ui_source('Ctrl+Alt+L · Lightweight'))] if lens.registered else []
            if state.registered:
                hints.append(self.tr(ui_source('{key} · Retranslate current screen')).format(key=state.shortcut))
            if toggle.registered:
                hints.append(self.tr(ui_source('{key} · Toggle translation')).format(key=toggle.shortcut))
            self.hotkey_hint.set('  /  '.join(hints) or self.tr(ui_source('Shortcut inactive; check Settings')))
            if state.error:
                message=self.tr(ui_source('Shortcut unavailable: {error}')).format(error=self.tr(state.error))
            elif toggle.error:
                message=self.tr(ui_source('Translation toggle unavailable: {error}')).format(error=self.tr(toggle.error))
            else:
                message='  /  '.join(hints)
            self.settings_panel.hotkey_status.set(message)
            return not (state.error or toggle.error)
        except Exception:
            self.hotkey_hint.set(self.tr(ui_source('Shortcut inactive; check Settings')))
            self.settings_panel.hotkey_status.set(self.tr(ui_source('Shortcut registration failed. Change the combination and save again.')));return False

    def _toggle_translation(self):
        if self._closing or not self._require_agreement():
            return
        if self.pipeline and not self.pipeline.stop_event.is_set():
            self.stop()
        elif not self.pipeline and not getattr(self,'_choosing_start_window',False):
            self._shortcut_popup_shown=False
            self._hotkey_starting=True
            try:
                self.start()
            finally:
                self._hotkey_starting=False
            if not self._shortcut_popup_shown or self.pipeline:
                shortcut_popup(self,self.tr(ui_source('Game translation')),self.tr(ui_source('Translation started')) if self.pipeline else self.status.get())

    def retranslate_current(self):
        if self._closing or not self._require_agreement():return False
        if self.profile_dialog is not None and self.profile_dialog.winfo_exists():
            self.status.set(self.tr(ui_source('Close profile management first.')));return False
        if self.manual_busy or self.import_busy or self._gpu_warm_busy:
            self.status.set(self.tr(ui_source('Wait for the current operation before retranslating.')));return False
        if self.pipeline:
            if self.pipeline.request_retranslation():
                self.status.set(self.tr(ui_source('Recognizing and translating the current game area again…')));return True
            return False
        self.start()
        return self.pipeline is not None

    def open_dictionary_import(self):
        if self._mode_busy():
            self.status.set(self.tr(ui_source('Stop translation and wait for the current operation to finish.')));return None
        if self.import_dialog:return self.import_dialog
        self.import_dialog=DictionaryImportDialog(self);return self.import_dialog

    def open_translation_history(self):
        if self._mode_busy():
            self.status.set(self.tr(ui_source('Stop translation and wait for the current operation to finish.')));return None
        try:
            scope=self.term_scope(); identity=self.current_warmup_scope()
            engine=self.get_engine()
            records=engine.list_translation_history(*scope,warmup_scope=identity,limit=24)
            info=engine.get_context_status(*scope,warmup_scope=identity)
        except Exception as error:
            self.status.set(self.tr(self.settings_error_message(error)));return None
        window=tk.Toplevel(self.root);window.title(self.tr(ui_source('Translation and context archive')))
        window.geometry('850x600');window.transient(self.root)
        body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
        heading=self.tr(ui_source('Latest 24 records · Compressed storage · No extra API requests'))
        ttk.Label(body,text=heading,style='Heading.TLabel').pack(anchor='w')
        ttk.Label(body,text=f"{scope[0] or self.tr(ui_source('(Unspecified)'))} · {scope[1]} → {scope[2]}",style='Hint.TLabel').pack(anchor='w',pady=8)
        scroll=ttk.Scrollbar(body);scroll.pack(side='right',fill='y')
        view=self._text(body,height=18,yscrollcommand=scroll.set)
        view.pack(fill='both',expand=True);scroll.configure(command=view.yview)
        content=[self.tr(ui_source('Updated: '))+str(info['updated_at'] or '—'), self.tr(ui_source('Archive directory: '))+info['directory'], '']
        for item in records:
            content.extend([item['created_at'],self.tr(ui_source('Source: '))+item['source'],self.tr(ui_source('Translation: '))+item['translation'],self.tr(ui_source('Context: '))+item['context'],''])
        if not records:content.append(self.tr(ui_source('No new-version translations in this profile yet. Older terms remain on the dictionary page.')))
        view.insert('1.0','\n'.join(content));view.configure(state='disabled')
        return window

    def refresh_profiles(self):
        try:
            names=self.get_engine().list_profiles() if self.engine or (ROOT/'data/codebook.sqlite3').exists() else []
            names.extend(value.strip() for value in (self.game.get(),str(self.config.get('game') or '')) if value.strip())
            self.profile_box['values']=('',*sorted(set(names),key=lambda name:(name.casefold(),name)))
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)))

    def clear_profile(self):
        if self._mode_busy():return
        self._persist_profile()
        self._apply_profile({'name':'','notes':'','source_lang':LANGUAGES[self.source.get()],
                             'target_lang':LANGUAGES[self.target.get()]})

    def remember_profile(self):
        self.profile_changed()
        self._persist_profile(raise_errors=True)
        self.refresh_profiles()

    def _queue_profile_save(self,*_):
        if self._profile_loading or self._closing or not self.agreement_accepted:return
        if self._profile_save_after is not None:self.root.after_cancel(self._profile_save_after)
        self._profile_save_after=self.root.after(600,self._persist_profile)

    def _persist_profile(self,*,raise_errors=False):
        if self._profile_save_after is not None:
            self.root.after_cancel(self._profile_save_after)
            self._profile_save_after = None
        if self._profile_loading or not self.agreement_accepted:return True
        try:
            name=self._selected_profile_name
            notes=self.context.get().strip()
            if len(notes)>16384:raise UIValidationError(ui_source('Context notes may contain up to 16,384 characters.'))
            source,target=LANGUAGES[self.source.get()],LANGUAGES[self.target.get()]
            changed = notes != self._saved_profile_notes
            if name and (changed or (source, target) != self._saved_profile_languages):
                self.get_engine().save_profile(name, notes=notes if changed else None,
                                               source_lang=source, target_lang=target)
            self._saved_profile_notes = notes
            self._saved_profile_languages = (source, target)
            update={'game':name,'last_profile':name,'context_note':notes,'source_lang':source,'target_lang':target}
            if any(self.config.get(key)!=value for key,value in update.items()):
                self.config=self.config_store.save({**self.config,**update})
            return True
        except Exception as error:
            if raise_errors:raise
            self.status.set(self.tr(self.settings_error_message(error)));return False

    def _apply_profile(self,profile,*,persist=True):
        self._profile_loading=True
        try:
            name=profile.get('name',profile.get('game',''))
            self.game.set(name);self._selected_profile_name=name
            self._saved_profile_notes = profile.get('notes','').strip()
            self.context.set(self._saved_profile_notes)
            summary = profile.get('summary_note') or profile.get('bounded_summary') or ''
            self.profile_summary.set(' '.join(summary.split()))
            if summary:
                self.context_summary_row.pack(fill='x', pady=(6, 0))
            else:
                self.context_summary_row.pack_forget()
            for variable,key,default in ((self.source,'source_lang',ui_source('Japanese')),(self.target,'target_lang',ui_source('Simplified Chinese'))):
                variable.set(self.tr(translation_language_name(profile.get(key),default)))
            self._saved_profile_languages = (LANGUAGES[self.source.get()], LANGUAGES[self.target.get()])
        finally:self._profile_loading=False
        if persist:self._persist_profile()
        self.refresh_terms()

    def restore_profile(self):
        if not self._selected_profile_name or not (ROOT/'data/codebook.sqlite3').exists():return
        try:
            profile=self.get_engine().get_profile(self._selected_profile_name)
            if profile:self._apply_profile(profile,persist=False)
        except Exception as error:self.status.set(self.tr(self.settings_error_message(error)))

    def save_profile_context(self):
        if not self._require_agreement() or not self.profile_changed() or not self._persist_profile():
            return
        self.status.set(self.tr(ui_source('Profile saved')))

    def profile_changed(self,event=None,*,reopen=False):
        if self._profile_loading or self._mode_busy() or not self.agreement_accepted:return False
        name=self.game.get().strip()
        if name==self._selected_profile_name and (not reopen or not name):return True
        if not self._persist_profile():return False
        try:
            if name:
                profile=self.get_engine().get_profile(name)
                if profile is None:profile=self.get_engine().save_profile(name,notes='',
                    source_lang=LANGUAGES[self.source.get()],target_lang=LANGUAGES[self.target.get()])
            else:profile={'name':'','notes':'','source_lang':LANGUAGES[self.source.get()],'target_lang':LANGUAGES[self.target.get()]}
            self._apply_profile(profile);self.refresh_profiles()
            return True
        except Exception as error:
            self.game.set(self._selected_profile_name)
            self.status.set(self.tr(self.settings_error_message(error)))
            return False

    def resume_profile(self,profile):
        if self._mode_busy():
            self.status.set(self.tr(ui_source('Stop translation and wait for the current operation to finish.')));return False
        if profile.get('name')!=self._selected_profile_name and not self._persist_profile():return False
        current = self.get_engine().get_profile(profile['name']) if profile.get('name') else None
        self._apply_profile(current or profile);self.refresh_profiles();self.tabs.select(0)
        self.status.set(self.tr(ui_source('Profile restored. Select the game window and start translation.')))
        return True

    def _profiles_changed(self):
        name=self._selected_profile_name
        if name:
            current=self.get_engine().get_profile(name)
            if current:self._apply_profile(current)
            else:self._apply_profile({'name':'','notes':'','source_lang':LANGUAGES[self.source.get()],'target_lang':LANGUAGES[self.target.get()]})
        self.refresh_profiles();self.refresh_terms()

    def open_profiles(self):
        if not self._require_agreement():return None
        if self._mode_busy():
            self.status.set(self.tr(ui_source('Stop translation and wait for the current operation to finish.')));return None
        self.popup_guard.close_popups()
        if self.profile_dialog is not None and self.profile_dialog.winfo_exists():
            self.profile_dialog.lift();return self.profile_dialog
        if not self.profile_changed(reopen=True) or not self._persist_profile():return None
        initial={'name':self._selected_profile_name,'source_lang':LANGUAGES[self.source.get()],
                 'target_lang':LANGUAGES[self.target.get()],'notes':self.context.get()}
        self.profile_dialog=ProfileManagerDialog(self.root,self.get_engine(),tr=self.tr,initial=initial,font_family=self.ui_font,
            on_resume=self.resume_profile,on_changed=self._profiles_changed)
        self.popup_guard.register_tree(self.profile_dialog)
        self.profile_dialog.bind('<Destroy>',self._profile_dialog_closed,add='+')
        self._refresh_mode_control()
        return self.profile_dialog

    def _profile_dialog_closed(self,event):
        if event.widget is self.profile_dialog:
            self.profile_dialog=None
            if not self._closing:self._refresh_mode_control()

    def remember_translation_languages(self):
        source, target = LANGUAGES[self.source.get()], LANGUAGES[self.target.get()]
        if self.config.get('source_lang') != source or self.config.get('target_lang') != target:
            self.config = self.config_store.save({**self.config, 'source_lang':source, 'target_lang':target})
        return source, target

    def translation_language_changed(self, event=None):
        try:
            self.remember_translation_languages()
            self._persist_profile()
            self.refresh_terms()
        except Exception as error:
            self.status.set(self.tr(self.settings_error_message(error)))

    def _scan_windows_periodically(self):
        if self._closing:
            return
        if not self._window_scan_pending:
            self._window_scan_pending=True
            generation=self._window_refresh_id
            def scan():
                try:rows=window_list()
                except Exception:rows=None
                self.events.put(('window_list',generation,rows))
            threading.Thread(target=scan,name='game-windows',daemon=True).start()
        self.root.after(2000,self._scan_windows_periodically)

    def refresh_windows(self, rows=None):
        periodic=rows is not None
        previous=None
        selected=self.windows_box.current()
        if 0<=selected<len(getattr(self,'window_rows',[])):
            item=self.window_rows[selected];previous=(item['hwnd'],item['pid'])
        if rows is None:
            self._window_refresh_id=getattr(self,'_window_refresh_id',0)+1
            rows=window_list()
        available=[dict(row) for row in rows if translation_target(row)]
        if periodic and available==getattr(self,'window_rows',None):
            return
        self.window_rows=available
        self.windows_box['values']=[self.window_label(r) for r in self.window_rows]
        selected=next((i for i,r in enumerate(self.window_rows) if (r['hwnd'],r['pid'])==previous),None)
        if selected is not None:self.windows_box.current(selected)
        else:self.windows_box.set(self.tr(ui_source('Choose a game window')))

    def chosen_window(self):
        i=self.windows_box.current()
        if not 0<=i<len(self.window_rows):raise UIValidationError(ui_source('Select a game window first.'))
        selected=self.window_rows[i]
        if not translation_target(selected):
            raise UIValidationError(ui_source('The selected window is a folder or system helper. Select the actual game application window.'))
        current=window_metadata(selected['hwnd'])
        if not current or current['pid']!=selected['pid']:
            raise UIValidationError(ui_source('The selected window has closed or its process has changed. Refresh the list and select it again.'))
        if not translation_target(current):
            raise UIValidationError(ui_source('The selected window is a folder or system helper. Select the actual game application window.'))
        return current

    def _window_for_start(self):
        try:
            return self.chosen_window()
        except UIValidationError:
            if 0<=self.windows_box.current()<len(self.window_rows):
                raise
        profile=self.game.get().strip()
        if not profile:
            App._target_prompt(self,self.tr(ui_source('Start translation')),self.tr(ui_source('No game profile is selected.')))
            return None
        self.refresh_windows()
        stored=self.config.get('profile_windows')
        previous=stored.get(profile) if isinstance(stored,dict) else None
        candidate=matching_window(self.window_rows,profile,previous)
        if candidate is None:
            App._target_prompt(self,self.tr(ui_source('Start translation')),self.tr(ui_source('No matching game window was found. Select a window manually.')))
            return None
        old_pid=previous.get('pid') if isinstance(previous,dict) else None
        if candidate['pid']!=old_pid:
            prompt=self.tr(ui_source('Found a matching window: {window}. Previous PID: {pid}. Translate this window?'))
            if not App._target_prompt(self,self.tr(ui_source('Confirm game window')),prompt.format(
                    window=self.window_label(candidate),pid=old_pid if old_pid is not None else '—'),confirm=True):
                return None
        identity=candidate['hwnd'],candidate['pid']
        index=next((i for i,row in enumerate(self.window_rows)
                    if (row['hwnd'],row['pid'])==identity),None)
        if index is None:
            raise UIValidationError(ui_source('The selected window has closed or its process has changed. Refresh the list and select it again.'))
        self.windows_box.current(index)
        return self.chosen_window()

    def _remember_window(self,window):
        profile=self.game.get().strip()
        if not profile:
            return
        stored=self.config.get('profile_windows')
        entries=dict(stored) if isinstance(stored,dict) else {}
        entry={name:window.get(name,'') for name in ('pid','title','process_path','exe_name')}
        if entries.get(profile)==entry:
            return
        entries.pop(profile,None)
        entries[profile]=entry
        self.config=self.config_store.save({**self.config,'profile_windows':dict(list(entries.items())[-24:])})

    def window_label(self,row):
        # Compact titles avoid multiline shell-controlled text in the UI. Keep
        # the actual executable and PID visible even for identically named windows.
        title=' '.join(str(row.get('title') or self.tr(ui_source('Untitled window'))).split())[:120]
        exe=row.get('exe_name') or PureWindowsPath(str(row.get('process_path') or '')).name
        exe=exe or self.tr(ui_source('Unknown process'))
        return f"{title} · {exe} · PID {row['pid']}"

    def _refresh_running_status(self,stats=None,*,now=None):
        """UI-thread status only, at most once per second; errors stay visible."""
        if not self.pipeline or not self.target_window:return
        if self.pipeline.stop_event.is_set() or getattr(self,'_run_status_error',False):return
        now=time.monotonic() if now is None else now
        if now<getattr(self,'_next_target_status',0):return
        self._next_target_status=now+1
        row=self.target_window;label=self.window_label(row)
        state=window_state(row['hwnd'],row['pid'])
        messages={
            'closed':ui_source('Target window closed: {window}. Refresh and select again.'),
            'replaced':ui_source('Target process changed: {window}. Refresh and select again.'),
            'minimized':ui_source('Target minimized: {window}. Restore it to resume recognition.'),
            'hidden':ui_source('Target is not visible: {window}. Show it to resume recognition.'),
            'background':ui_source('Waiting for target: {window}. Switch to this window to start recognition.'),
        }
        if state in messages:message=messages[state]
        elif getattr(self,'_capture_region_unavailable',False):
            message=ui_source('Selected area is outside the visible client area: {window}. Move the window or select regions again.')
        elif (stats or {}).get('in_flight',0)>0 or (stats or {}).get('context_agent_status')=='searching':
            message=ui_source('Waiting for AI recognition or translation: {window}.')
        elif getattr(self,'_last_ocr_line_count',None)==0:
            message=ui_source('Recognizing: {window}. No translatable text found yet.')
        elif self.regions:
            message=ui_source('Translation shown; tracking new text: {window}.')
        else:message=ui_source('Recognizing target: {window}.')
        self.status.set(self.tr(message).format(window=label))

    def _refresh_workbench(self):
        selected = self.tabs.select()
        for index, tab in enumerate(self.tabs.tabs()):
            state = 'active' if tab == selected else 'idle'
            self.tabs.tab(tab, image=self.workbench_icons[index, state], compound='left')
        light = self.lightweight_var.get()
        current = 2 if light else (0 if self.capture_region else 1)
        for index, button in enumerate((self.select_region_button, self.full_region_button, self.lightweight_button)):
            active = index == current
            state = 'active' if active else ('disabled' if light else 'idle')
            button.configure(style='Chosen.Region.TButton' if active else 'Region.TButton',
                             compound='left', image=self.workbench_icons[index + 5, state])

        if light:
            hint = self.tr(ui_source('Translate only the text near your pointer.'))
        elif self.capture_region:
            hint = self.tr(ui_source('{count} regions selected; follow the game window')).format(count=len(self.capture_region))
        else:
            hint = self.tr(ui_source('Entire game window'))
        self.region_label.configure(text=hint)

    def _toggle_lightweight(self):
        self.lightweight_var.set(not self.lightweight_var.get())
        self._apply_lightweight()

    def _apply_lightweight(self):
        enabled = self.lightweight_var.get()
        for button in (self.select_region_button, self.full_region_button):
            button.configure(state='disabled' if enabled else 'normal')
        self._refresh_workbench()
        if self.pipeline:
            self.pipeline.set_lightweight(enabled)

    def full_region(self):
        if self.lightweight_var.get():
            return
        try:
            if not self.pipeline:self.target_window=self.chosen_window()
            self.capture_region=None
            self._refresh_workbench()
            self.region_label.config(text=self.tr(ui_source('Recognizing the full client area. A dialogue-only region uses fewer resources and API requests.')))
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)))

    def select_region(self):
        if self.lightweight_var.get():
            return
        self.stop()
        try:self.target_window=self.chosen_window()
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)));return
        self.root.withdraw()
        top=tk.Toplevel(self.root);top.overrideredirect(True);top.attributes('-topmost',True);top.attributes('-alpha',.35)
        x,y,w,h=virtual_screen();top.geometry(f'{w}x{h}{x:+d}{y:+d}')
        canvas=tk.Canvas(top,bg='black',cursor='crosshair',highlightthickness=0);canvas.pack(fill='both',expand=True)
        hint=canvas.create_text(30,30,text='',anchor='nw',fill='white',font=(self.ui_font,21))
        anchor=[0,0];rectangle=[None];selected=[];drawings=[]
        def refresh_hint():
            canvas.itemconfig(hint,text=self.tr(ui_source('Drag to add regions (up to 8) · Enter to confirm · Backspace/right-click to undo · Esc to cancel'))+'\n'+self.tr(ui_source('Selected regions: {count}')).format(count=len(selected)))
        def down(e):
            if len(selected)>=MAX_REGIONS:return
            anchor[:]=[e.x,e.y];rectangle[0]=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline='#E2584C',width=3)
        def move(e):
            if rectangle[0]:canvas.coords(rectangle[0],anchor[0],anchor[1],e.x,e.y)
        def done(e):
            if rectangle[0] is None:return
            box=client_rect(self.target_window['hwnd'])
            if box:
                sx,sy=min(anchor[0],e.x)+x,min(anchor[1],e.y)+y
                rw,rh=abs(e.x-anchor[0]),abs(e.y-anchor[1])
                clipped=client_selections(((sx-box[0],sy-box[1],rw,rh),),box)
                if clipped:
                    cx,cy,cw,ch=clipped[0]
                    relative=(cx-box[0],cy-box[1],cw,ch)
                    if cw>=20 and ch>=20 and not any(overlaps(relative,r) for r in selected):
                        try:capture_plan([*selected,relative])
                        except ValueError:pass
                        else:
                            selected.append(relative)
                            canvas.coords(rectangle[0],cx-x,cy-y,cx+cw-x,cy+ch-y)
                            number=canvas.create_text(cx-x+6,cy-y+6,text=str(len(selected)),anchor='nw',fill='white',font=('Segoe UI',19,'bold'))
                            drawings.append((rectangle[0],number));rectangle[0]=None
            if rectangle[0]:canvas.delete(rectangle[0]);rectangle[0]=None
            refresh_hint()
        def close():
            top.destroy();self.root.deiconify()
        def accept(e=None):
            if not selected:return
            self.capture_region=tuple(selected)
            self._refresh_workbench()
            self.capture_region_target=(self.target_window['hwnd'],self.target_window['pid'])
            self.region_label.config(text=self.tr(ui_source('{count} regions selected; follow the game window')).format(count=len(selected)))
            close()
        def undo(e=None):
            if drawings:
                for drawing in drawings.pop():canvas.delete(drawing)
                selected.pop();refresh_hint()
        canvas.bind('<Button-1>',down);canvas.bind('<B1-Motion>',move);canvas.bind('<ButtonRelease-1>',done)
        canvas.bind('<Button-3>',undo);top.bind('<BackSpace>',undo);top.bind('<Return>',accept)
        top.bind('<Escape>',lambda e:close());top.focus_force();refresh_hint()

    def start(self):
        if getattr(self,'_choosing_start_window',False):return
        if not self._require_agreement():return
        if self.profile_dialog is not None and self.profile_dialog.winfo_exists():
            self.status.set(self.tr(ui_source('Close profile management first.')));return
        if getattr(self,'_gpu_warm_busy',False):
            self.status.set(self.tr(ui_source('Warming up CUDA OCR. Translation will be ready shortly.')));return
        self.stop()
        if self.pipeline:
            self.status.set(self.tr(ui_source('Recognition is stopping. Wait a moment before restarting.')))
            return
        try:
            self._choosing_start_window=True
            try:self.target_window=self._window_for_start()
            finally:self._choosing_start_window=False
            if self.target_window is None:
                return
            source,target=LANGUAGES[self.source.get()],LANGUAGES[self.target.get()]
            if source==target:raise UIValidationError(ui_source('Source and target languages must be different.'))
            display = validate_tuning(self.config)
            self.remember_translation_languages()
            if self.core is None:
                try:
                    from .ocr import OcrCore
                    self.core=self._new_ocr_core()
                except ImportError:self.core=NativeCore()
            from .vision_core import VisionCore
            vision_mode = display['vision_ocr_mode']
            wants_vision = vision_mode != 'off' and not self.offline_only.get() and self.backend_ready
            # Frame recognition uses the active slot and its provider's image protocol.
            if isinstance(self.core,VisionCore) and (not wants_vision or self.core.recognizer.engine is not self.get_engine()):
                self.core.close()
                from .ocr import OcrCore
                self.core=self._new_ocr_core()
            if wants_vision and not isinstance(self.core,VisionCore):
                self.core=VisionCore(self.core,self.get_engine(),interval=self.config.get('vision_interval_ms',3000)/1000,
                                     settle=self.config.get('settle_ms',80)/1000, frame_mode=vision_mode)
            if hasattr(self.core,'enable_live_capture'):
                self.core.enable_live_capture(cursor_attention=display['cursor_attention'],
                                              supersample=display['sampling_mode']=='supersample',
                                              scene_change_sensitivity=display['scene_change_sensitivity'],
                                              translation_hold_ms=display['translation_hold_ms'])
            self.core.set_overlay_font(display['overlay_font_family'])
            if hasattr(self.core,'set_auto_font_style'):
                self.core.set_auto_font_style(display['auto_font_style'],target)
            elif display['auto_font_style']:
                raise UIValidationError('\u539f\u751f\u6838\u5fc3\u7248\u672c\u4e0d\u5339\u914d\uff0c\u8bf7\u4f7f\u7528\u672c\u7248\u672c\u9644\u5e26\u7684 DLL \u6216\u91cd\u65b0\u8fd0\u884c native/build.ps1\u3002')
            self.core.set_overlay_options(**{name:display[name] for name in (
                'auto_font_size','overlay_font_size','overlay_font_min','overlay_font_max','capture_translations')})
            langs=self.core.languages()
            if not wants_vision and not any(v.lower().startswith(source.lower()) for v in langs):raise UIValidationError(f'\u672c\u673a\u7f3a\u5c11 {source} OCR\u3002\u5df2\u5b89\u88c5\uff1a{langs}\u3002\u6587\u672c\u7ffb\u8bd1\u4ecd\u53ef\u4f7f\u7528\u3002')
            self.remember_profile()
            hwnd=self.target_window['hwnd'];relative=self.capture_region
            pid=self.target_window['pid']
            if relative and getattr(self,'capture_region_target',(hwnd,pid))!=(hwnd,pid):
                relative=None;self.capture_region=None
                self._refresh_workbench()
                self.region_label.config(text=self.tr(ui_source('Recognizing the full client area. A dialogue-only region uses fewer resources and API requests.')))
            executable=self.target_window.get('exe_name') or PureWindowsPath(self.target_window.get('process_path','')).name
            if hasattr(self.core,'set_game_executable'):self.core.set_game_executable(executable)
            if hasattr(self.core,'set_target'):self.core.set_target(hwnd,pid)
            self._remember_window(self.target_window)
            self._run_status_error=False;self._next_target_status=0
            self._capture_region_unavailable=False;self._last_ocr_line_count=None
            def provider():
                rect=client_rect(hwnd)
                if not foreground(hwnd,pid):return None
                if not rect:
                    self._capture_region_unavailable=True
                    return None
                regions = None if pipeline.lightweight else self.capture_region
                result=visible_client_selections(regions,rect)
                self._capture_region_unavailable=not bool(result)
                return result
            pipeline=self.pipeline=Pipeline(self.core,self.get_engine(),self.events.put,
                interval=self.config.get('capture_interval_ms',50)/1000,
                settle=self.config.get('settle_ms',80)/1000,
                merge_lines=self.config.get('merge_dialogue_lines',True),
                tracking_workers=self.config.get('tracking_workers',2),
                translation_workers=self.config.get('translation_workers',8),
                max_objects=self.config.get('max_tracked_objects',32),
                max_missing=self.config.get('track_missing_frames',10),
                show_source_label=display['show_source_label'], label_language=self.ui_language,
                source_label_mixed_only=display['source_label_mixed_only'],
                show_translation_brackets=display['show_translation_brackets'],warmup_scope=self.current_warmup_scope(),
                cursor_attention=display['cursor_attention'],sampling_mode=display['sampling_mode'],
                fast_capture_ms=getattr(self,'fast_capture_ms',50),persist_results=True,
                game_executable=executable)
            self.pipeline.lightweight=self.lightweight_var.get()
            self.overlay_state.hold_seconds=display['translation_hold_ms']/1000
            self._game_process=GameProcess(pid)
            if self._check_game_process():return
            self.pipeline.start(provider,self.game.get().strip(),source,target,self.context.get().strip())
            if self.config.get("localization_enabled") is True:
                self._begin_localization_export(hwnd,pid,executable or self.target_window.get("title","Game"))
            self.start_button.config(state='disabled');self._refresh_mode_control()
            self.status.set(self.tr(ui_source('Waiting for target: {window}. Switch to this window to start recognition.')).format(window=self.window_label(self.target_window)))
        except Exception as e:
            if self.pipeline:self.stop()
            self._run_status_error=True
            self.status.set(self.tr(self.settings_error_message(e)))

    def _new_ocr_core(self):
        from .ocr import OcrCore
        core=OcrCore(min_confidence=self.config.get('ocr_min_confidence',55),
                       mode=self.config.get('ocr_mode','auto'),
                       refine_workers=self.config.get('ocr_refine_workers',4),
                       cuda_enabled=self.config.get('cuda_enabled',True),
                       cuda_memory_mb=self.config.get('cuda_memory_mb',1024),
                       cuda_quality=self.config.get('cuda_quality',75),cuda_instance=getattr(self,'_gpu_warm_core',None))
        self._gpu_warm_core=None
        return core

    def _using_gpu_for_ocr(self):
        if not self.config.get('cuda_enabled', True) or self.config.get('ocr_mode', 'auto') != 'auto':
            return False
        status = getattr(self.core, 'cuda_status', None)
        if status == 'active':
            return True
        worker = self._gpu_warm_core or getattr(self.core, 'cuda', None)
        return status in (None, 'ready') and getattr(worker, 'last_status', {}).get('state') == 'cuda'

    def _prepare_cuda(self):
        """Warm only already-configured installations, off the Tk thread, without capture/network."""
        if (self._closing or self.core or self._gpu_warm_core is not None or self._mode_busy() or
            not self.agreement_accepted or not self.backend_ready or
            self.config.get('app_language_selected') is not True or
            not self.config.get('cuda_enabled',True) or self.config.get('ocr_mode','auto')!='auto'):
            return
        from .cuda_ocr import CudaOcr
        try:cuda=CudaOcr(ROOT,memory_mb=self.config.get('cuda_memory_mb',1024),quality=self.config.get('cuda_quality',75))
        except ValueError:return
        if not cuda.available():return
        self._gpu_warm_core=cuda;self._gpu_warm_busy=True
        self.status.set(self.tr(ui_source('Warming up CUDA OCR. Translation will be ready shortly.')))
        self._refresh_mode_control()
        def prepare():
            ready=False
            try:cuda.warmup();ready=True
            except Exception:
                cuda.last_status={'state':'unavailable','reason':'warmup_failed'}
            finally:self.events.put(('cuda_warm_done',0,ready))
        threading.Thread(target=prepare,daemon=True,name='cuda-prewarm').start()

    def stop(self):
        if getattr(self,'_game_process',None) is not None:
            self._game_process.close()
            self._game_process=None
        self._next_process_check=0.
        self._run_status_error=False;self._next_target_status=0
        if self.pipeline:
            self.pipeline.stop();self.pipeline.join(.1)
            if self.pipeline.alive:
                self.root.after(100,self._finish_stop)
            else:self.pipeline=None
        self.overlay_state.clear();self.active_generation=-1
        self.object_metric.set(self.tr(ui_source('Tracked 0 · Translations shown 0')))
        if self.core:self.core.hide_overlay()
        if hasattr(self,'start_button'):self.start_button.config(state='normal')
        self._refresh_mode_control()
        self.status.set(self.tr(f'\u5df2\u505c\u6b62 · {self._mode_name()} · \u539f\u753b\u9762\u6062\u590d'))

    def _finish_stop(self):
        if self.pipeline and self.pipeline.stop_event.is_set():
            if self.pipeline.alive:
                self.root.after(100,self._finish_stop)
            else:
                self.pipeline=None
                self.start_button.config(state='normal')
                self._refresh_mode_control()

    def _check_game_process(self):
        process = getattr(self, '_game_process', None)
        if process is None:
            return
        now = time.monotonic()
        if now < self._next_process_check:
            return
        self._next_process_check = now + .1
        if process.exited():
            label = self.window_label(self.target_window)
            self.stop()
            self.target_window = None
            self.status.set(self.tr(ui_source('The game exited and translation stopped. {window}')).format(window=label))
            return True

    def drain(self):
        self._check_game_process()
        redraw=self.overlay_state.expire_held()
        for _ in range(256):
            try:kind,gen,payload=self.events.get_nowait()
            except queue.Empty:break
            if kind=='retranslate':
                self.retranslate_current();continue
            if kind=='toggle_lightweight':
                self.lightweight_var.set(not self.lightweight_var.get());self._apply_lightweight();continue
            if kind=='toggle_translation':
                self._toggle_translation();continue
            if kind=='export_error':
                self.status.set(self.tr('\u6c49\u5316\u6587\u672c\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u4fdd\u5b58\u76ee\u5f55\u3002'));continue
            if kind=='window_list':
                self._window_scan_pending=False
                if not self._closing and gen==self._window_refresh_id and payload is not None:
                    self.refresh_windows(payload)
                continue
            if kind=='late_translation':
                owner,identity,line,original,show=payload
                if self.pipeline is owner and not owner.stop_event.is_set():
                    if show and gen==owner.generation:
                        redraw=self.overlay_state.apply_late(identity,line) or redraw
                    self._log_translation(original,line['text'])
                continue
            if kind=='backend_failure':
                self._show_backend_failure(*payload)
                continue
            if kind=='cuda_warm_done':
                self._gpu_warm_busy=False
                self.status.set(self.tr(ui_source('CUDA OCR is warmed up and ready.') if payload else ui_source('CUDA unavailable; using local OCR')))
                self._refresh_mode_control()
                continue
            if kind=='dictionary_result':
                dialog,result=payload
                if self.import_dialog is dialog:dialog.receive(result)
                else:self.import_busy=False
                continue
            if kind=='manual':
                self._set_manual_output(self._take_manual() if payload is None else payload);continue
            if kind=='manual_status':self.status.set(self.tr(payload));continue
            if kind=='manual_done':
                self.manual_busy=False;self._refresh_mode_control();continue
            if kind=='error':
                if gen == 0 or (self.pipeline and gen == self.pipeline.generation):
                    self._run_status_error=True
                    self.status.set(self.tr(str(payload)[:500]))
                    if gen != 0:self.start_button.config(state='normal')
                continue
            if not self.pipeline or gen!=self.pipeline.generation:continue
            if kind=='clear':self.active_generation=gen;self.overlay_state.clear();redraw=True
            elif kind=='background':
                if gen==self.active_generation and self.regions:redraw=True
            elif kind=='hold':self.active_generation=gen;redraw=self.overlay_state.apply_objects([],manual_refresh=True) or redraw
            elif kind=='source_changed':
                redraw=self.overlay_state.discard_changed_sources(payload) or redraw
            elif kind=='objects':
                redraw=self.overlay_state.apply_objects(payload) or redraw
            elif kind=='translation':
                i,line,original,done=payload
                accepted=self.overlay_state.apply_translation(i,line)
                redraw=accepted or redraw
                if done and accepted and not line.get('_translation_unchanged'):
                    self._log_translation(original,line['text'])
            elif kind=='line_error':
                i,revision,msg=payload
                current=self.overlay_state.objects.get(i)
                if current and current['revision']==revision:
                    redraw=self.overlay_state.remove_error(i,revision) or redraw
                    self._run_status_error=True
                    self.status.set(self.tr(f'{self._mode_name()} · {msg}'))
            elif kind=='timing':
                self._last_ocr_line_count=len(payload['lines'])
                cuda_labels={'active':ui_source('CUDA OCR active'),'failed':ui_source('CUDA unavailable; using local OCR'),
                             'not_installed':ui_source('CUDA components missing; using local OCR'),
                             'pixel_priority':ui_source('Pixel scenes use the pixel-text OCR path'),
                             'cpu_mode':ui_source('Using the selected local OCR mode'),'unsupported_language':ui_source('Using local OCR for this language')}
                backend=(ui_source('Image recognition via the LLM backend') if payload.get('engine') in ('llm-screenshot','deepseek-screenshot')
                         else cuda_labels.get(payload.get('cuda_status'),''))
                self.metric.set(self.tr(f"\u622a\u56fe {payload.get('capture_ms',0):.1f} ms  · OCR {payload.get('ocr_ms',0):.1f} ms  · {len(payload['lines'])} \u884c")+
                                (' · '+self.tr(backend) if backend else ''))
                if payload.get('vision_error'):
                    self._run_status_error=True
                    self.status.set(self.tr(payload['vision_error']))
        target_active = bool(self.target_window and foreground(self.target_window['hwnd'],self.target_window['pid']))
        if self.core and not target_active:
            self.core.hide_overlay()
        if redraw and self.core and target_active:
            try:self.core.show_overlay(limit_two_layers(sorted(self.overlay_state.display_regions(),
                    key=lambda row:bool(row.get('_hold_previous')))))
            except Exception as e:
                self._run_status_error=True
                self.status.set(self.tr(self.settings_error_message(e)))
        if target_active and getattr(self,'exporter',None) is not None:
            self._poll_localization_page()
        if time.monotonic() >= self.next_stats_update:
            self.next_stats_update = time.monotonic()+1
            stats=self.engine.get_stats() if self.engine else {}
            self._refresh_running_status(stats,now=self.next_stats_update-1)
            self._refresh_mode_control(stats)
        metric=self.tr(f'\u8ffd\u8e2a\u5bf9\u8c61 {len(self.overlay_state.objects)} · \u5df2\u663e\u793a\u8bd1\u6587 {len(self.regions)} · \u7ffb\u8bd1\u5e76\u53d1\u4e0a\u9650 {self.config.get("translation_workers",4)}')
        preserved=sum(bool(item['line'].get('_preserve_source')) for item in self.overlay_state.objects.values())
        if preserved:metric+=self.tr(ui_source(' · Original text kept in {count} boxes')).format(count=preserved)
        if self.object_metric.get()!=metric:self.object_metric.set(metric)
        self.root.after(8 if self.pipeline or self.manual_busy else 80,self.drain)

    def term_scope(self):return self.game.get().strip(),LANGUAGES[self.source.get()],LANGUAGES[self.target.get()]
    def save_term(self):
        if self._mode_busy():self.status.set(self.tr(ui_source('Stop translation or wait for the dictionary operation to finish.')));return
        try:
            if not self.term_shared.get() and not self.term_scope()[0]:
                raise UIValidationError(ui_source('Select a game profile or the shared dictionary. Unassigned legacy terms are for browsing only.'))
            if self.term_shared.get():
                self.get_engine().import_terms([{'source':self.term_source.get(),'target':self.term_target.get()}],
                    *self.term_scope(),shared=True,replace=True)
            else:self.get_engine().set_term(*self.term_scope(),self.term_source.get(),self.term_target.get())
            self.remember_profile();self.refresh_terms();self.status.set(self.tr(ui_source('Term saved')))
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)))
    def refresh_terms(self):
        if self.import_busy:return
        try:
            scope=(*self.term_scope(),bool(self.term_shared.get()))
            terms=(self.get_engine().list_shared_terms(*self.term_scope()[1:],limit=200) if self.term_shared.get()
                   else self.get_engine().list_terms(*self.term_scope()))
            # Do not erase a usable list when reading the database fails.
            for i in self.term_tree.get_children():self.term_tree.delete(i)
            for term in terms:self.term_tree.insert('', 'end', values=(term['source'],term['target']))
            self._term_view_scope=scope
            category=self.tr(ui_source('Shared dictionary')) if scope[3] else scope[0] or self.tr(ui_source('Unassigned legacy terms (browse only)'))
            self.term_scope_status.set(self.tr(ui_source('{scope} · {source} → {target} · {count} entries shown')).format(
                scope=category,source=scope[1],target=scope[2],count=len(terms)))
            if not terms:self.term_scope_status.set(self.term_scope_status.get()+' · '+self.tr(ui_source('No terminology reference in this scope; generated translations are in the profile history.')))
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)))
    def _load_selected_term(self,event=None):
        selected=self.term_tree.selection()
        if not self._mode_busy() and len(selected)==1:
            values=self.term_tree.item(selected[0],'values')
            if len(values)==2:
                self.term_source.set(values[0]);self.term_target.set(values[1])

    def delete_term(self):
        if self._mode_busy():self.status.set(self.tr(ui_source('Stop translation or wait for the dictionary operation to finish.')));return
        try:
            if getattr(self,'_term_view_scope',None)!=(*self.term_scope(),bool(self.term_shared.get())):
                self.refresh_terms();self.status.set(self.tr(ui_source('The dictionary scope changed. Select the entries to delete again.')));return
            for i in self.term_tree.selection():
                source=self.term_tree.item(i,'values')[0]
                if self.term_shared.get():self.get_engine().delete_shared_term(*self.term_scope()[1:],source)
                else:self.get_engine().delete_term(*self.term_scope(),source)
            self.refresh_terms()
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)))
    def _manual_limit(self):
        try:return min(16000,max(64,int(self.config.get('max_input_chars',4000))))
        except (ValueError,TypeError,OverflowError):return 4000

    def _update_manual_count(self,event=None):
        count=self.manual_input.count('1.0','end-1c','chars')
        count=int(count[0]) if count else 0
        limit=self._manual_limit()
        self.manual_count.set(self.tr(f'{count} / {limit} \u5b57\u7b26 · Ctrl+Enter \u7ffb\u8bd1'+(ui_source(' · Split into smaller parts') if count>limit else '')))
        if self.manual_input.edit_modified():self.manual_input.edit_modified(False)

    def _post_manual(self,text):
        # Cumulative streams can otherwise enqueue O(n²) text while Tk is busy.
        # Hold one latest value and one queue marker, not every partial response.
        with self._manual_lock:
            self._manual_pending=str(text)[:64000]
            if not self._manual_event_queued:
                self._manual_event_queued=True
                self.events.put(('manual',0,None))

    def _take_manual(self):
        with self._manual_lock:
            text=self._manual_pending or ''
            self._manual_pending=None;self._manual_event_queued=False
            return text

    def _set_manual_output(self,text):
        self.manual_output.configure(state='normal')
        self.manual_output.delete('1.0','end');self.manual_output.insert('end',str(text)[:64000])
        self.manual_output.configure(state='disabled')

    def manual_translate(self):
        if not self._require_agreement():return
        if self._mode_busy():
            self.status.set(self.tr(ui_source('A translation or dictionary operation is already running.')));return
        limit=self._manual_limit()
        text=self.manual_input.get('1.0',f'1.0 + {limit+1} chars').strip()
        if len(text)>limit or int((self.manual_input.count('1.0','end-1c','chars') or (0,))[0])>limit:
            self.status.set(self.tr(f'\u539f\u6587\u8d85\u8fc7 {limit} \u5b57\u7b26\uff0c\u8bf7\u5206\u6bb5\u7ffb\u8bd1\u6216\u5728\u8bbe\u7f6e\u4e2d\u8c03\u6574\u4e0a\u9650\u3002'));return
        scope=self.term_scope();context=self.context.get()
        if scope[1]==scope[2]:
            self.status.set(self.tr(ui_source('Source and target languages must be different.')));return
        if len(context)>16384:
            self.status.set(self.tr(ui_source('Game context is limited to 16,384 characters. Shorten it and try again.')));return
        if not text:
            self.status.set(self.tr(ui_source('Enter text to translate.')));return
        try:
            self.remember_translation_languages()
            engine=self.get_engine()
            self.remember_profile()
        except Exception as e:self.status.set(self.tr(self.settings_error_message(e)));return
        self._set_manual_output('')
        self.manual_busy=True
        self._refresh_mode_control()
        mode=self._mode_name()
        self.status.set(self.tr(f'{mode} · \u6b63\u5728\u67e5\u8be2\u6216\u7ffb\u8bd1'))
        def work():
            from .translation import LocalTranslationMiss
            try:
                identity=warmup_identity(scope[0])
                options={'warmup_scope':identity} if identity else {}
                result=engine.translate(*scope,text,self._post_manual,context,**options)
                self._post_manual(result)
                self.events.put(('manual_status',0,f'{mode} · \u7ffb\u8bd1\u5b8c\u6210 · \u8bed\u5883\u5df2\u4fdd\u5b58'))
            except LocalTranslationMiss:
                self._post_manual(text)
                self.events.put(('manual_status',0,ui_source('AI unavailable; original text preserved')))
            except Exception as e:self.events.put(('error',0,self.settings_error_message(e)))
            finally:self.events.put(('manual_done',0,None))
        threading.Thread(target=work,daemon=True).start()
    def _log_translation(self,original,translated):
        self.log.insert('end',f'{original}  →  {translated}\n')
        self.log.see('end')
        if int(self.log.index('end-1c').split('.')[0])>300:self.log.delete('1.0','100.0')

    def close(self):
        if getattr(self,'_gpu_warm_busy',False):
            self._closing=True
            if self._gpu_warm_core is not None:self._gpu_warm_core.cancel()
            self.root.after(50,self.close);return
        if getattr(self,'_gpu_warm_core',None) is not None:
            self._gpu_warm_core.close();self._gpu_warm_core=None
        if self.setup_dialog:self.setup_dialog.close()
        if self.import_busy:
            if not self._closing:
                self._closing=True
                self.status.set(self.tr(ui_source('Finishing the dictionary operation before closing.')))
            self.root.after(100,self.close);return
        if self.import_dialog:self.import_dialog.close()
        if self.api_dialog:self.api_dialog.close()
        if self.hotkey is not None:self.hotkey.close();self.hotkey=None
        if self.toggle_hotkey is not None:self.toggle_hotkey.close();self.toggle_hotkey=None
        if getattr(self,'lens_hotkey',None):self.lens_hotkey.close();self.lens_hotkey=None
        if self._profile_save_after is not None:
            self.root.after_cancel(self._profile_save_after);self._profile_save_after=None
        self.profile_changed()
        self._persist_profile()
        self.popup_guard.close_popups()
        if self.profile_dialog is not None and self.profile_dialog.winfo_exists():self.profile_dialog.close()
        self.popup_guard.close()
        if self._system_palette_watch is not None:
            self.root.after_cancel(self._system_palette_watch)
            self._system_palette_watch = None
        if self.welcome_session:
            self.welcome_session.close()
            self.welcome_session = None
        self.stop()
        if self.exporter:self.exporter.close();self.exporter=None
        if self.engine:self.engine.close()
        if self.core:self.core.close()
        self.root.destroy()
    def run(self):self.root.mainloop()

def main():App().run()
