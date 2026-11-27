# SPDX-License-Identifier: MIT
"""Three API configuration slots; keys stay masked and drafts stay in memory."""

from .i18n import ui_source
import tkinter as tk
from tkinter import ttk
from .security import validate_api_url, SecurityValidationError
from .api_providers import PRESETS, provider_for, local_endpoint


class ApiSettingsDialog:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.tr(ui_source('API settings · NKC_Galgame_Translator')))
        self.window.geometry('700x720')
        self.window.minsize(660, 700)
        self.window.configure(bg='#F7F3EE')
        self.window.transient(app.root)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.slot = tk.IntVar(value=int(app.config.get('active_api_slot',0)))
        self.base_url, self.model = tk.StringVar(), tk.StringVar()
        # Existing credentials are never copied into visible/editable fields.
        self.key = tk.StringVar(value='')
        self.clear_key = tk.BooleanVar(value=False)
        self.error = tk.StringVar(value=self.app.tr(app.config_store.credential_error or ''))
        self.key_hint, self.editing_hint = tk.StringVar(), tk.StringVar()
        self.drafts = {}
        self.provider_names=tuple(app.tr(label) for label in (ui_source('DeepSeek (recommended)'),'ChatGPT',ui_source('Other (custom)'),'Ollama',ui_source('Local')))
        self._local_provider=None
        self._display_provider=None
        self._last_endpoint=''
        self._closed = False

        body = ttk.Frame(self.window, padding=24)
        body.pack(fill='both', expand=True)
        buttons=ttk.Frame(body)
        buttons.pack(side='bottom',fill='x',pady=(6,0))
        ttk.Label(body, text=self.app.tr(ui_source('API settings')), style='Heading.TLabel').pack(anchor='w')
        ttk.Label(body, text=self.app.tr(ui_source('Default API format: OpenAI-compatible (Chat Completions)')),
                  style='Hint.TLabel', wraplength=600).pack(anchor='w', pady=(8, 14))
        if getattr(app,'_initial_vision_note',''):
            ttk.Label(body,text=app.tr(app._initial_vision_note),style='Hint.TLabel',wraplength=600).pack(anchor='w',pady=(0,10))
        slots = ttk.Frame(body); slots.pack(fill='x')
        self.slot_buttons = []
        for index in range(3):
            slots.columnconfigure(index, weight=1, uniform='api-slots')
            button = ttk.Button(slots, command=lambda index=index:self.select_slot(index))
            button.grid(row=0,column=index,sticky='ew',padx=(0 if index==0 else 6,0))
            self.slot_buttons.append(button)
        ttk.Label(body,textvariable=self.editing_hint,foreground='#B6332D').pack(anchor='w',pady=(12,4))
        ttk.Label(body,text=self.app.tr(ui_source('Switching slots keeps unsaved edits in this window. Save applies only to the selected slot; closing discards unsaved edits.')),
                  style='Hint.TLabel',wraplength=600).pack(anchor='w',pady=(0,14))
        service_row=ttk.Frame(body)
        service_row.pack(fill='x',pady=(0,7))
        ttk.Label(service_row,text=app.tr(ui_source('API provider'))).pack(side='left',padx=(0,9))
        self.provider=ttk.Combobox(service_row,values=self.provider_names,state='readonly',width=26)
        self.provider.pack(side='left')
        self.provider.bind('<<ComboboxSelected>>',self._choose_provider)
        self.provider_hint=tk.StringVar()
        ttk.Label(service_row,textvariable=self.provider_hint,style='Hint.TLabel').pack(side='left',padx=10)
        fields=ttk.Frame(body)
        fields.pack(fill='x',pady=(4,8))
        fields.columnconfigure(1,weight=1)
        for i,(label, variable, attribute) in enumerate((
                (ui_source('API address'), self.base_url, 'base_url_entry'),
                (ui_source('Model'), self.model, 'model_entry'),
                (ui_source('API key'), self.key, 'key_entry'))):
            ttk.Label(fields,text=self.app.tr(label)).grid(row=i,column=0,sticky='w',padx=(0,12))
            entry=ttk.Entry(fields,textvariable=variable,show='●' if variable is self.key else '')
            entry.grid(row=i,column=1,sticky='ew',pady=4)
            setattr(self, attribute, entry)
        # Purely visual: neither the stored key nor a sentinel enters StringVar.
        # A constant length also avoids disclosing the credential's length.
        self.key_placeholder = tk.Label(self.key_entry, text='●' * 12,
            background='#FFFFFF', foreground='#756D65', font='TkTextFont',
            borderwidth=0, takefocus=False)
        self.key_placeholder.bind('<Button-1>', self._focus_key_entry)
        self.key.trace_add('write', self._refresh_key_placeholder)
        self.clear_key.trace_add('write', self._refresh_key_placeholder)
        ttk.Label(body,textvariable=self.key_hint,style='Hint.TLabel',wraplength=600).pack(anchor='w')
        ttk.Label(body,text=self.app.tr(ui_source('Saving makes no API request. Keys are encrypted for the current Windows account.')),
                  style='Hint.TLabel',wraplength=600).pack(anchor='w',pady=(5,5))
        self.clear_check=ttk.Checkbutton(body,text=self.app.tr(ui_source('Clear the saved key for this slot')),variable=self.clear_key)
        self.clear_check.pack(anchor='w',pady=(0,4))
        self.error_label=ttk.Label(body,textvariable=self.error,foreground='#B6332D',wraplength=600)
        self.error_label.pack(anchor='w',pady=(0,8))
        self.save_button=ttk.Button(buttons,style='Accent.TButton',command=self.save_online)
        self.save_button.pack(side='left')
        self.offline_button=ttk.Button(buttons,text=self.app.tr(ui_source('Set up later · Browse records')),command=self.use_offline)
        self.offline_button.pack(side='left',padx=8)
        self.close_button=ttk.Button(buttons,text=self.app.tr(ui_source('Close')),command=self.close)
        self.close_button.pack(side='right')
        self._load_slot(self.slot.get())
        self.base_url.trace_add('write',self._endpoint_edited)
        self.refresh_busy()
        self._modal_after=self.window.after_idle(self._make_modal)

    def _make_modal(self):
        self._modal_after=None
        if self.window.winfo_exists() and self.window.winfo_viewable():
            self.window.grab_set()

    def _choose_provider(self,_event=None):
        if self.app._mode_busy():
            return
        key=tuple(PRESETS)[self.provider.current()]
        if self._display_provider!=key:
            self._local_provider=key if key in ('ollama','local') else None
            endpoint,model=PRESETS[key]
            self.base_url.set(endpoint)
            self.model.set(model)
            if key=='custom':
                self.base_url_entry.focus_set()
            elif self._local_provider:
                self.model_entry.focus_set()

    def _endpoint_edited(self,*_):
        endpoint=self.base_url.get().strip()
        try:
            identity=validate_api_url(endpoint)
        except SecurityValidationError:
            identity=endpoint
        if identity!=self._last_endpoint:
            self.key.set('')
            self.clear_key.set(False)
        self._last_endpoint=identity
        provider=provider_for(endpoint,self._local_provider)
        self._display_provider=provider
        self.provider.current(tuple(PRESETS).index(provider))
        hint={'deepseek':'deepseek-flash','openai':ui_source('Use an OpenAI API key.'),
              'ollama':ui_source('Enter an installed Ollama model name.'),'local':ui_source('Enter the model name loaded by your local server.'),
              'custom':ui_source('Enter the provider’s API URL and model name.')}
        self.provider_hint.set(self.app.tr(hint[provider]))
        self._refresh_endpoint_hint()

    def _default_draft(self, index):
        saved=self.app.config['api_slots'][index]
        return (saved['base_url'],saved['model'],'',False,saved.get('local_provider'))

    def _stash(self):
        self.drafts[self.slot.get()]=(self.base_url.get(),self.model.get(),self.key.get(),self.clear_key.get(),self._local_provider)

    def _load_slot(self,index):
        self.slot.set(index)
        endpoint,model,key,clear,self._local_provider=self.drafts.get(index,self._default_draft(index))
        self.base_url.set(endpoint);self.model.set(model)
        self._endpoint_edited()
        self.key.set(key);self.clear_key.set(clear)
        self._refresh_slot_labels()

    def _refresh_slot_labels(self):
        selected=self.slot.get();active=self.app.config.get('active_api_slot',0)
        for index,button in enumerate(self.slot_buttons):
            saved=self.app.config['api_slots'][index]
            configured=saved['has_api_key'] or local_endpoint(saved['base_url'])
            status=ui_source('Configured') if configured else ui_source('Not set')
            if index==active:status=ui_source('Active · ')+status
            button.configure(text=self.app.tr(f'\u69fd\u4f4d {index+1}\n{status}'),style='Accent.TButton' if index==selected else 'TButton')
        self.editing_hint.set(self.app.tr(f'\u6b63\u5728\u7f16\u8f91\uff1a\u69fd\u4f4d {selected+1}'+(ui_source(' (active)') if selected==active else '')))
        self._refresh_endpoint_hint()
        self.save_button.configure(text=self.app.tr(f'\u4fdd\u5b58\u5e76\u4f7f\u7528\u69fd\u4f4d {selected+1}'))

    def _refresh_endpoint_hint(self):
        saved=self.app.config['api_slots'][self.slot.get()]
        try:changed=validate_api_url(self.base_url.get().strip(' '))!=validate_api_url(saved['base_url'])
        except SecurityValidationError:changed=True
        self.key_hint.set(self.app.tr(ui_source('Leave the key blank if your local server uses no authentication.') if local_endpoint(self.base_url.get()) and (changed or not saved['has_api_key']) else
            ui_source('The API address changed. Re-enter a key for this address; the previous key will not transfer.')
            if saved['has_api_key'] and changed else
            ui_source('A key is saved. Leave blank to keep it for the same address, or enter a new key to replace it.') if saved['has_api_key'] else
            ui_source('This slot has no key. Enter a key or set it up later and browse records.')))
        self._refresh_key_placeholder()

    def _refresh_key_placeholder(self, *_):
        if self._closed:
            return
        saved = self.app.config['api_slots'][self.slot.get()]
        try:
            same_endpoint = validate_api_url(self.base_url.get().strip(' ')) == validate_api_url(saved['base_url'])
        except SecurityValidationError:
            same_endpoint = False
        visible = saved['has_api_key'] and same_endpoint and not self.key.get() and not self.clear_key.get()
        if visible:
            self.key_placeholder.place(x=7, rely=.5, anchor='w')
        else:
            self.key_placeholder.place_forget()

    def _focus_key_entry(self, _event=None):
        if str(self.key_entry['state']) != 'disabled':
            self.key_entry.focus_set()
        return 'break'

    def refresh_busy(self):
        state='disabled' if self.app._mode_busy() else 'normal'
        self.provider.configure(state='disabled' if state=='disabled' else 'readonly')
        for control in (*self.slot_buttons,self.base_url_entry,self.model_entry,self.key_entry,
                        self.clear_check,self.save_button,self.offline_button):
            control.configure(state=state)

    def select_slot(self,index):
        if self.app._mode_busy():
            self.error.set(self.app.tr(ui_source('Stop translation and wait for pending requests to finish.')));return False
        if type(index) is not int or not 0<=index<3:
            self.error.set(self.app.tr(ui_source('Select slot 1, 2, or 3.')));return False
        self._stash();self._load_slot(index);self.error.set(self.app.tr(''))
        return True

    def _replacement_key(self):
        if self.clear_key.get():return ''
        return self.key.get().strip() or None

    def _after_save(self):
        selected=self.slot.get()
        self.drafts.pop(selected,None)
        self.key.set('');self.clear_key.set(False)
        # Saving one slot must not silently discard another slot's typed key.
        pending=any(value!=self._default_draft(index) for index,value in self.drafts.items())
        if pending:
            self._load_slot(selected)
            self.error.set(self.app.tr(f'\u69fd\u4f4d {selected+1} \u5df2\u4fdd\u5b58\uff1b\u5176\u4ed6\u69fd\u4f4d\u8fd8\u6709\u672a\u4fdd\u5b58\u5185\u5bb9\u3002'))
        else:self.close()

    def save_online(self):
        try:
            self.app.save_api_settings(self.base_url.get(),self.model.get(),
                api_key=self._replacement_key(),offline_only=False,slot=self.slot.get(),local_provider=self._local_provider)
        except Exception as error:
            self.error.set(self.app.tr(self.app.settings_error_message(error)));return False
        self._after_save();return True

    def use_offline(self):
        try:
            # No online form is required. Discard its unsubmitted fields/key;
            # explicit clearing applies only to the currently selected slot.
            saved=self.app.config['api_slots'][self.slot.get()]
            self.app.save_api_settings(saved['base_url'],saved['model'],
                api_key='' if self.clear_key.get() else None,offline_only=True,slot=self.slot.get())
        except Exception as error:
            self.error.set(self.app.tr(self.app.settings_error_message(error)));return False
        self._after_save();return True

    def close(self):
        if self._closed:return
        self._closed=True
        self.key.set('');self.drafts.clear()
        if self._modal_after is not None:
            self.window.after_cancel(self._modal_after);self._modal_after=None
        if self.window.winfo_exists():
            if self.window.grab_current()==self.window:self.window.grab_release()
            self.window.destroy()
        if self.app.api_dialog is self:self.app.api_dialog=None
