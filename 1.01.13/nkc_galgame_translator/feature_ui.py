# SPDX-License-Identifier: MIT
"""Theme and export preferences and independent shortcut notifications."""

import ctypes
from ctypes import wintypes
import re
import time
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
from PIL import Image

from .chart_backdrop import load_picture
from .i18n import ui_source
from .localization_export import FORMATS, DEFAULT_WAIT
from .themes import LABELS, COLOR_FIELDS, validate_theme

EXPORT_TITLE=ui_source('Localization Toolkit (Beta)')
EXPORT_WARNING=ui_source('Saves screenshots and translations locally and may affect performance. The selection delay defaults to 15 seconds.')


class ThemeFields:
    def __init__(self, app, theme):
        self.app = app
        self.controls = []
        prefs = validate_theme({})
        self.labels = {code: app.tr(label) for code, label in LABELS.items()}
        self.theme=tk.StringVar(value=self.labels[prefs['interface_theme']])
        self.box=ttk.Combobox(theme,state='readonly',values=tuple(self.labels.values()),textvariable=self.theme,width=27)
        self.box.pack(anchor='w')
        self.box.bind('<<ComboboxSelected>>',lambda _: self.refresh())
        self.controls.append((self.box,'readonly'))
        self.picture = tk.StringVar()
        row = ttk.Frame(theme)
        row.pack(fill='x', pady=(6, 0))
        chooser = ttk.Button(row, text=app.tr(ui_source('Choose chart image')), command=self.choose_picture)
        chooser.pack(side='left')
        reset = ttk.Button(row, text=app.tr(ui_source('Use theme background')), command=lambda: self.picture.set(''))
        reset.pack(side='left', padx=6)
        ttk.Entry(row, textvariable=self.picture, state='readonly').pack(side='left', fill='x', expand=True)
        self.controls.extend(((chooser, 'normal'), (reset, 'normal')))
        self.custom=ttk.Frame(theme)
        style_row = ttk.Frame(theme)
        style_row.pack(fill='x', pady=(4, 0))
        ttk.Label(style_row, text=app.tr(ui_source('Graph style')), width=14).pack(side='left')
        self.chart_style = tk.StringVar()
        for value, label in (('mountains', 'Mountain ridges (beta)'), ('line', 'Line graph')):
            option = ttk.Radiobutton(style_row, text=app.tr(ui_source(label)), value=value,
                                     variable=self.chart_style)
            option.pack(side='left', padx=(0, 8))
            self.controls.append((option, 'normal'))
        self.line_colors = []
        for label in ('Usage line color', 'Memory line color'):
            row = ttk.Frame(theme)
            row.pack(fill='x', pady=(4, 0))
            ttk.Label(row, text=app.tr(ui_source(label)), width=20).pack(side='left')
            var = tk.StringVar()
            self.line_colors.append(var)
            entry = ttk.Entry(row, textvariable=var, width=11)
            entry.pack(side='left')
            picker = ttk.Button(row, text=app.tr(ui_source('Color picker')),
                                command=lambda v=var: self.pick_color(v))
            picker.pack(side='left', padx=8)
            reset = ttk.Button(row, text=app.tr(ui_source('Use theme color')), command=lambda v=var: v.set(''))
            reset.pack(side='left')
            self.controls.extend(((entry, 'normal'), (picker, 'normal'), (reset, 'normal')))
        self.colors={}
        for key,label in COLOR_FIELDS.items():
            row=ttk.Frame(self.custom)
            row.pack(fill='x',pady=(4,0))
            ttk.Label(row,text=app.tr(label),width=14).pack(side='left')
            color=tk.StringVar(value=prefs['interface_colors'][key])
            self.colors[key]=color
            entry=ttk.Entry(row,textvariable=color,width=11)
            entry.pack(side='left')
            chooser=ttk.Button(row,text=app.tr(ui_source('Color picker')),command=lambda v=color:self.pick_color(v))
            chooser.pack(side='left',padx=8)
            self.controls.extend(((entry,'normal'),(chooser,'normal')))
        self.apply_config(app.config)

    def pick_color(self, var):
        initial = var.get() if re.fullmatch(r'#[0-9A-Fa-f]{6}', var.get()) else '#FFFFFF'
        value = colorchooser.askcolor(color=initial, parent=self.box.winfo_toplevel())[1]
        if value:
            var.set(value.upper())

    def choose_picture(self):
        path = filedialog.askopenfilename(parent=self.box.winfo_toplevel(),
                                          filetypes=[('PNG, JPEG, BMP', '*.png *.jpg *.jpeg *.bmp')])
        if path:
            try:
                load_picture(path).close()
            except (OSError, ValueError, Image.DecompressionBombError):
                messagebox.showerror(parent=self.box.winfo_toplevel(), message=self.app.tr(
                    ui_source('Choose a local PNG, JPEG or BMP image of up to 24 megapixels.')))
                return
            self.picture.set(path)

    def apply_config(self, config):
        try:
            prefs = validate_theme(config)
        except ValueError:
            prefs = validate_theme({})
        self.theme.set(self.labels[prefs['interface_theme']])
        self.picture.set(prefs['chart_picture'])
        self.chart_themes = dict(prefs['chart_styles'])
        self.chart_themes['custom'] = prefs['custom_chart_style']
        self.chart_overrides = dict(prefs['chart_colors'])
        self.editing_theme = None
        for key, value in prefs['interface_colors'].items():
            self.colors[key].set(value)
        self.refresh()

    def values(self):
        self.sync_chart()
        return dict(interface_theme=self.editing_theme, chart_picture=self.picture.get(),
                    custom_chart_style=self.chart_themes.get('custom', 'line'),
                    chart_styles={k:v for k,v in self.chart_themes.items() if k != 'custom'},
                    chart_colors=dict(self.chart_overrides),
                    interface_colors={key: value.get() for key, value in self.colors.items()})

    def localize(self):
        selected = self.values()['interface_theme']
        self.labels = {code: self.app.tr(label) for code, label in LABELS.items()}
        self.box.configure(values=tuple(self.labels.values()))
        if selected:
            self.theme.set(self.labels[selected])

    def refresh(self, busy=False):
        self.sync_chart()
        if self.theme.get() == self.labels['custom']:
            self.custom.pack(fill='x', pady=(4, 0))
        else:
            self.custom.pack_forget()
        for widget, state in self.controls:
            widget.configure(state='disabled' if busy else state)

    def sync_chart(self):
        name = next((k for k, label in self.labels.items() if label == self.theme.get()), None)
        if self.editing_theme is not None:
            self.chart_themes[self.editing_theme] = self.chart_style.get()
            self.chart_overrides[self.editing_theme] = [v.get().strip() for v in self.line_colors]
        if name != self.editing_theme:
            self.editing_theme = name
            self.chart_style.set(self.chart_themes.get(name, 'line'))
            for var, color in zip(self.line_colors, self.chart_overrides.get(name, ('', ''))):
                var.set(color)


class FeaturePanel:
    def __init__(self, app, parent):
        self.app = app
        self.controls = []
        theme = ttk.LabelFrame(parent, text=app.tr(ui_source('Interface theme')), padding=12)
        theme.pack(fill='x', pady=(0, 14))
        self.theme_fields = ThemeFields(app, theme)
        export=ttk.LabelFrame(parent,text=app.tr(EXPORT_TITLE),padding=12)
        export.pack(fill='x',pady=(0,14))
        self.enabled=tk.BooleanVar(value=app.config.get('localization_enabled',False))
        self.folder=tk.StringVar(value=app.config.get('localization_folder',''))
        self.format=tk.StringVar(value=app.config.get('localization_format','txt'))
        self.wait=tk.StringVar(value=str(app.config.get('localization_wait',DEFAULT_WAIT)))
        check=ttk.Checkbutton(export,text=app.tr(ui_source('Enable the localization toolkit')),variable=self.enabled)
        check.pack(anchor='w')
        self.controls.append((check,'normal'))
        app._hint(export,EXPORT_WARNING).pack(anchor='w',pady=(4,8))
        row=ttk.Frame(export);row.pack(fill='x')
        ttk.Label(row,text=app.tr(ui_source('Save folder'))).pack(side='left')
        folder=ttk.Entry(row,textvariable=self.folder)
        folder.pack(side='left',fill='x',expand=True,padx=8)
        choose=ttk.Button(row,text=app.tr(ui_source('Choose folder')),command=self.choose_directory)
        choose.pack(side='left')
        self.controls.extend(((folder,'normal'),(choose,'normal')))
        app._hint(export,ui_source('Leave blank to use the application folder.')).pack(anchor='w',pady=(3,6))
        row=ttk.Frame(export);row.pack(fill='x')
        ttk.Label(row,text=app.tr(ui_source('Export format'))).pack(side='left')
        format_box=ttk.Combobox(row,textvariable=self.format,values=FORMATS,width=7,state='readonly')
        format_box.pack(side='left',padx=(8,20))
        ttk.Label(row,text=app.tr(ui_source('Wait before exporting (s)'))).pack(side='left')
        wait_box=ttk.Spinbox(row,from_=1,to=120,textvariable=self.wait,width=7)
        wait_box.pack(side='left',padx=8)
        self.controls.extend(((format_box,'readonly'),(wait_box,'normal')))
        self.refresh()

    def choose_directory(self):
        folder=choose_directory(self.app,self.folder.get())
        if folder:self.folder.set(folder)

    def apply_export_config(self,config):
        self.enabled.set(config.get('localization_enabled',False))
        self.folder.set(config.get('localization_folder',''))
        self.format.set(config.get('localization_format','txt'))
        self.wait.set(str(config.get('localization_wait',DEFAULT_WAIT)))

    def values(self):
        return dict(**self.theme_fields.values(), localization_enabled=self.enabled.get(),
                    localization_folder=self.folder.get().strip(),
                    localization_format=self.format.get(), localization_wait=self.wait.get())

    def refresh(self, busy=False):
        self.theme_fields.refresh(busy)
        for widget, state in self.controls:
            widget.configure(state='disabled' if busy else state)


def choose_directory(app,existing='',*,parent=None):
    return filedialog.askdirectory(parent=parent or app.root,title=app.tr(ui_source('Choose the localization export folder')),
                                   initialdir=existing or str(app.project_root),mustexist=True)


def shortcut_popup(app,title,message,*,confirm=False):
    """Use an independent window so an iconic or hidden main window stays there."""
    root=app.root
    win=tk.Toplevel(root)
    win.withdraw()
    win.overrideredirect(True)
    win.attributes('-topmost',True)
    panel=ttk.Frame(win,padding=16,relief='solid',borderwidth=1)
    panel.pack(fill='both',expand=True)
    ttk.Label(panel,text=title,style='Heading.TLabel').pack(anchor='w')
    ttk.Label(panel,text=message,wraplength=360).pack(anchor='w',pady=(6,0))
    response=False
    if confirm:
        actions=ttk.Frame(panel)
        actions.pack(anchor='e',pady=(10,0))
        def choose(value):
            nonlocal response
            response=value
            win.destroy()
        ttk.Button(actions,text=app.tr('\u53d6\u6d88'),command=lambda:choose(False)).pack(side='left',padx=6)
        ttk.Button(actions,text=app.tr(ui_source('Start translation')),style='Accent.TButton',command=lambda:choose(True)).pack(side='left')
        win.bind('<Escape>',lambda _:choose(False))
        win.after(30000,win.destroy)
    win.update_idletasks()
    width,height=win.winfo_reqwidth(),win.winfo_reqheight()
    win.geometry(f'{width}x{height}+{max(12,root.winfo_screenwidth()-width-32)}+46')
    if not confirm:
        user32=ctypes.windll.user32
        owner=user32.GetAncestor
        owner.argtypes=(wintypes.HWND,wintypes.UINT);owner.restype=wintypes.HWND
        handle=owner(win.winfo_id(),2)
        get_style=user32.GetWindowLongW
        get_style.argtypes=(wintypes.HWND,ctypes.c_int)
        set_style=user32.SetWindowLongW
        set_style.argtypes=(wintypes.HWND,ctypes.c_int,ctypes.c_long)
        set_style(handle,-20,get_style(handle,-20)|0x08000000)
        app._shortcut_notice_until=time.monotonic()+1.65
    win.deiconify()
    if confirm:
        win.focus_force()
        root.wait_window(win)
    else:
        win.after(1650,win.destroy)
    return response

