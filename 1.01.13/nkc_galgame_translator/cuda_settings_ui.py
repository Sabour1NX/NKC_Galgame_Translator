# SPDX-License-Identifier: MIT
"""Shared first-run/settings controls; no GPU imports, probing or downloads."""

from .i18n import ui_source
import tkinter as tk
from tkinter import ttk


class CudaControls:
    def __init__(self, app, parent, variables=None):
        self.app=app
        self.vars={} if variables is None else variables
        self.box=ttk.LabelFrame(parent,text=app.tr(ui_source('CUDA text recognition')),padding=12)
        self.box.pack(fill='x',pady=(0,12))
        self.vars['cuda_enabled']=tk.BooleanVar(value=app.config.get('cuda_enabled',True))
        self.vars['cuda_quality']=tk.DoubleVar(value=app.config.get('cuda_quality',75))
        self.vars['cuda_memory_mb']=tk.StringVar(value=str(app.config.get('cuda_memory_mb',1024)))
        self.toggle=ttk.Checkbutton(self.box,text=app.tr(ui_source('Enable CUDA OCR (automatic fallback when unavailable)')),
                                   variable=self.vars['cuda_enabled'],command=self.refresh)
        self.toggle.pack(anchor='w')
        ends=ttk.Frame(self.box);ends.pack(fill='x',pady=(8,0))
        ttk.Label(ends,text=app.tr(ui_source('Performance'))).pack(side='left')
        ttk.Label(ends,text=app.tr(ui_source('Accuracy'))).pack(side='right')
        self.scale=ttk.Scale(self.box,from_=0,to=100,variable=self.vars['cuda_quality'],command=self.update_hint)
        self.scale.pack(fill='x',pady=(2,4))
        self.value=tk.StringVar()
        ttk.Label(self.box,textvariable=self.value,style='Hint.TLabel',wraplength=640).pack(anchor='w')
        row=ttk.Frame(self.box);row.pack(fill='x',pady=(8,4))
        ttk.Label(row,text=app.tr(ui_source('GPU memory budget (MiB)'))).pack(side='left')
        self.memory=ttk.Spinbox(row,from_=256,to=16384,increment=256,
                              textvariable=self.vars['cuda_memory_mb'],width=8)
        self.memory.pack(side='left',padx=12)
        ttk.Label(self.box,text=app.tr(ui_source('Default: 1024 MiB (1 GiB). This is an inference memory budget; runtime overhead is additional. Without a compatible GPU or component pack, local OCR is used.')),
                  style='Hint.TLabel',wraplength=640).pack(anchor='w',pady=(4,0))
        self._busy=False
        self.vars['cuda_quality'].trace_add('write',self.update_hint)
        self.refresh()

    def update_hint(self,*_):
        try:q=max(0,min(100,round(float(self.vars['cuda_quality'].get()))))
        except (ValueError,tk.TclError):return
        self.value.set(self.app.tr(ui_source('Quality coefficient {quality} / 100 · Linearly adjusts recognition resolution; actual speed and accuracy depend on the scene.')).format(quality=q))

    def values(self):
        return {'cuda_enabled':self.vars['cuda_enabled'].get(),
                'cuda_quality':round(float(self.vars['cuda_quality'].get())),
                'cuda_memory_mb':self.vars['cuda_memory_mb'].get()}

    def refresh(self,busy=None):
        if busy is not None:self._busy=bool(busy)
        self.toggle.configure(state='disabled' if self._busy else 'normal')
        enabled=self.vars['cuda_enabled'].get() and not self._busy
        for control in (self.scale,self.memory):control.configure(state='normal' if enabled else 'disabled')
        self.update_hint()
