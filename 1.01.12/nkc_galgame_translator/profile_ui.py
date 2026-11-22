# SPDX-License-Identifier: MIT
"""Local context-profile management. No API calls or permission popups."""
from __future__ import annotations

from .i18n import ui_source

from datetime import datetime
import tkinter as tk
from tkinter import ttk
from .scrolling import ComboboxPopupGuard
from .ui_font import UI_BODY_SIZE


LANGUAGES = ((ui_source('Japanese'),'ja'),(ui_source('English'),'en'),(ui_source('Simplified Chinese'),'zh-Hans'),(ui_source('Traditional Chinese'),'zh-Hant'),
             (ui_source('Korean'),'ko'),(ui_source('French'),'fr'),(ui_source('German'),'de'),(ui_source('Spanish'),'es'))
UI_STRINGS = (
    ui_source('Manage game profiles'),ui_source('Resume a saved profile or create a new one. Save after editing.'),ui_source('New profile'),ui_source('Refresh'),
    ui_source('Profile name'),ui_source('Languages'),ui_source('Completed segments'),ui_source('Updated'),ui_source('Source text is in'),ui_source('Translation language'),ui_source('Profile notes'),
    ui_source('Notes guide later translations (up to 16384 characters). They are never displayed in the overlay.'),
    ui_source('Translation progress'),ui_source('Total active time'),ui_source('Saved contexts'),ui_source('Latest translation'),ui_source('Context excerpt (local)'),
    ui_source('Last source text (preview)'),ui_source('Last translation (preview)'),ui_source('Compressed storage'),ui_source('No translations yet'),ui_source('Save profile'),
    ui_source('Resume translation'),ui_source('Save and resume translation'),ui_source('Delete profile'),ui_source('Click again to delete'),ui_source('Cancel deletion'),ui_source('Close'),
    ui_source('Click Delete again to remove this profile and its local translation history. This cannot be undone.'),
    ui_source('New profile has not been saved'),ui_source('Unsaved changes'),ui_source('Profile saved'),ui_source('Profile deleted'),ui_source('Select a saved profile'),
    ui_source('Enter a profile name'),ui_source('Notes must be 16384 characters or fewer'),ui_source('Profile no longer exists'),ui_source('Saved profile names cannot be changed. Create a new profile instead.'),
    ui_source('That name already exists. Select the saved profile.'),
    ui_source('Stop translation before switching profiles.'),ui_source('No profiles yet. Create your first profile.'),ui_source('Operation failed'),
)


def profile_values(profile):
    profile = profile or {}
    return {'name':str(profile.get('name',profile.get('game','')) or ''),
            'source_lang':str(profile.get('source_lang') or 'en'),
            'target_lang':str(profile.get('target_lang') or 'zh-Hans'),
            'notes':str(profile.get('notes') or '')}


class ProfileManagerModel:
    """Small UI controller; backend owns transactions and busy protection."""
    def __init__(self, backend):
        self.backend = backend
        self.selected = None
        self.delete_target = None

    def select(self, name):
        record = self.backend.get_profile(name)
        if record is None:
            raise ValueError(ui_source('Profile no longer exists'))
        self.selected = record
        self.delete_target = None
        return record

    def new(self):
        self.selected = None
        self.delete_target = None

    def save(self, values):
        name = str(values.get('name') or '').strip()
        notes = str(values.get('notes') or '')
        if not name:
            raise ValueError(ui_source('Enter a profile name'))
        if len(notes) > 16384:
            raise ValueError(ui_source('Notes must be 16384 characters or fewer'))
        if self.selected and name != self.selected['name']:
            raise ValueError(ui_source('Saved profile names cannot be changed. Create a new profile instead.'))
        if not self.selected and self.backend.get_profile(name) is not None:
            raise ValueError(ui_source('That name already exists. Select the saved profile.'))
        self.selected = self.backend.save_profile(name, notes=notes,
            source_lang=values['source_lang'], target_lang=values['target_lang'])
        self.delete_target = None
        return self.selected

    def arm_delete(self):
        if not self.selected:
            raise ValueError(ui_source('Select a saved profile'))
        self.delete_target = (self.selected['name'],self.selected.get('profile_id'))

    def cancel_delete(self):
        self.delete_target = None

    def confirm_delete(self):
        target = self.delete_target
        if not target or not self.selected or target != (self.selected['name'],self.selected.get('profile_id')):
            raise ValueError(ui_source('Select a saved profile'))
        fresh = self.backend.get_profile(target[0])
        if not fresh or fresh.get('profile_id') != target[1]:
            self.cancel_delete()
            raise ValueError(ui_source('Profile no longer exists'))
        result = self.backend.delete_profile(target[0])
        # Busy/backend errors leave the current draft intact and are displayed
        # inline by the view; a successful delete returns to a new draft.
        self.new()
        return result


def _timestamp(value):
    if value in (None,'',0):
        return '—'
    try:
        parsed = datetime.fromtimestamp(value).astimezone() if isinstance(value,(int,float)) else datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone()
        return parsed.strftime('%Y-%m-%d %H:%M')
    except (ValueError,TypeError,OverflowError,OSError):
        return str(value)[:64]


class ProfileManagerDialog(tk.Toplevel):
    """parent, backend, tr; callbacks return to App without starting translation.

    on_resume receives a freshly loaded full profile. False keeps this dialog
    open (for example while the app is busy); any other return value closes it.
    on_changed refreshes the main profile list. show=False supports hidden tests.
    """
    def __init__(self, parent, backend, *, tr=lambda value:value, initial=None,
                 on_resume=None, on_changed=None, show=True, font_family='Microsoft YaHei UI'):
        super().__init__(parent)
        self.withdraw()
        self.font_family = font_family
        self.tr = tr; self.model = ProfileManagerModel(backend)
        self.on_resume = on_resume; self.on_changed = on_changed
        self.initial = profile_values(initial); self._loading=False
        self._drafts={}; self._rows={}; self._selected_name=None
        self._closed=False;self.result=None
        self.title(tr(ui_source('Manage game profiles'))); self.geometry('940x700'); self.minsize(760,560)
        self.transient(parent.winfo_toplevel())
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.guard = ComboboxPopupGuard(self)
        self.name = tk.StringVar(self); self.source = tk.StringVar(self); self.target = tk.StringVar(self)
        self.status = tk.StringVar(self); self.progress = tk.StringVar(self); self.compression = tk.StringVar(self)
        self.delete_label = tk.StringVar(self,value=tr(ui_source('Delete profile')))
        self.resume_label = tk.StringVar(self,value=tr(ui_source('Resume translation')))
        self._language_codes={tr(label):code for label,code in LANGUAGES}
        self._choice_codes=[code for label,code in LANGUAGES]
        self._build()
        for variable in (self.name,self.source,self.target):variable.trace_add('write',self._form_changed)
        self.notes.bind('<<Modified>>',self._notes_changed,add='+')
        self.guard.register_tree(self)
        self.refresh(select_name=self.initial['name'] or None, keep_draft=False)
        if show:
            self.deiconify()

    def _build(self):
        outer=ttk.Frame(self,padding=16);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text=self.tr(ui_source('Resume a saved profile or create a new one. Save after editing.')),wraplength=860).pack(anchor='w',pady=(0,12))
        tools=ttk.Frame(outer);tools.pack(fill='x',pady=(0,8))
        ttk.Button(tools,text=self.tr(ui_source('New profile')),command=self.new_profile).pack(side='left')
        ttk.Button(tools,text=self.tr(ui_source('Refresh')),command=self.refresh).pack(side='left',padx=8)
        panes=ttk.Panedwindow(outer,orient='horizontal');panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes);right=ttk.Frame(panes);panes.add(left,weight=2);panes.add(right,weight=3)
        self.tree=ttk.Treeview(left,columns=('language','completed'),show='tree headings',selectmode='browse')
        self.tree.heading('#0',text=self.tr(ui_source('Profile name')));self.tree.column('#0',width=145,minwidth=90)
        self.tree.heading('language',text=self.tr(ui_source('Languages')));self.tree.column('language',width=110,minwidth=70)
        self.tree.heading('completed',text=self.tr(ui_source('Completed segments')));self.tree.column('completed',width=75,minwidth=50,anchor='e')
        listing_scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=listing_scroll.set);listing_scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self._tree_selected)
        self.tree.bind('<Double-1>',lambda event:self.resume_selected())
        self.canvas=tk.Canvas(right,highlightthickness=0)
        scroll=ttk.Scrollbar(right,orient='vertical',command=lambda *args:self.guard.yview(self.canvas,*args))
        self.canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');self.canvas.pack(fill='both',expand=True)
        form=ttk.Frame(self.canvas,padding=(12,0,12,8));window=self.canvas.create_window(0,0,window=form,anchor='nw')
        def fit(event=None):
            self.canvas.itemconfigure(window,width=max(1,self.canvas.winfo_width()))
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        form.bind('<Configure>',fit,add='+');self.canvas.bind('<Configure>',fit,add='+')
        ttk.Label(form,text=self.tr(ui_source('Profile name'))).pack(anchor='w')
        self.name_entry=ttk.Entry(form,textvariable=self.name);self.name_entry.pack(fill='x',pady=(2,8))
        row=ttk.Frame(form);row.pack(fill='x',pady=(0,8))
        for label,variable in ((ui_source('Source text is in'),self.source),(ui_source('Translation language'),self.target)):
            group=ttk.Frame(row);group.pack(side='left',fill='x',expand=True,padx=(0,8))
            ttk.Label(group,text=self.tr(label)).pack(anchor='w')
            combo=ttk.Combobox(group,textvariable=variable,values=tuple(self._language_codes),state='readonly',width=15);combo.pack(fill='x')
            if variable is self.source:self.source_box=combo
            else:self.target_box=combo
        ttk.Label(form,text=self.tr(ui_source('Profile notes'))).pack(anchor='w')
        self.notes=tk.Text(form,height=5,wrap='word',undo=True,font=(self.font_family,UI_BODY_SIZE));self.notes.pack(fill='x',pady=(2,4))
        self.summary_note=self._readonly_text(form,ui_source('Translation context'),3)
        self.notes_hint=ttk.Label(form,text=self.tr(ui_source('Notes guide later translations (up to 16384 characters). They are never displayed in the overlay.')),wraplength=420);self.notes_hint.pack(anchor='w',fill='x',pady=(0,10))
        ttk.Label(form,text=self.tr(ui_source('Translation progress'))).pack(anchor='w')
        ttk.Label(form,textvariable=self.progress,wraplength=420).pack(anchor='w',fill='x',pady=(2,10))
        self.summary=self._readonly_text(form,ui_source('Context excerpt (local)'),5)
        self.latest_source=self._readonly_text(form,ui_source('Last source text (preview)'),3)
        self.latest_translation=self._readonly_text(form,ui_source('Last translation (preview)'),4)
        ttk.Label(form,textvariable=self.compression,wraplength=420).pack(anchor='w',fill='x',pady=(0,8))
        form.bind('<Configure>',lambda event:self.notes_hint.configure(wraplength=max(150,event.width-28)),add='+')
        self._bind_wheel(form)
        self.status_label=ttk.Label(outer,textvariable=self.status,wraplength=880);self.status_label.pack(anchor='w',fill='x',pady=(12,8))
        bottom=ttk.Frame(outer);bottom.pack(fill='x')
        self.save_button=ttk.Button(bottom,text=self.tr(ui_source('Save profile')),command=self.save_selected);self.save_button.pack(side='left')
        self.resume_button=ttk.Button(bottom,textvariable=self.resume_label,command=self.resume_selected);self.resume_button.pack(side='left',padx=8)
        self.delete_button=ttk.Button(bottom,textvariable=self.delete_label,command=self.request_delete);self.delete_button.pack(side='left')
        self.cancel_delete_button=ttk.Button(bottom,text=self.tr(ui_source('Cancel deletion')),command=self.cancel_delete)
        ttk.Button(bottom,text=self.tr(ui_source('Close')),command=self.close).pack(side='right')

    def _readonly_text(self,parent,label,height):
        ttk.Label(parent,text=self.tr(label)).pack(anchor='w')
        widget=tk.Text(parent,height=height,wrap='word',font=(self.font_family,UI_BODY_SIZE),state='disabled');widget.pack(fill='x',pady=(2,10));return widget

    def _bind_wheel(self,widget):
        if not isinstance(widget,(tk.Text,ttk.Combobox)):
            widget.bind('<MouseWheel>',lambda event:(self.guard.yview_scroll(self.canvas,-int(event.delta/120),'units'),'break')[1],add='+')
        for child in widget.winfo_children():self._bind_wheel(child)

    def _values(self):
        def language(box,variable):
            index=box.current()
            return self._choice_codes[index] if 0<=index<len(self._choice_codes) else self._language_codes.get(variable.get(),variable.get())
        return {'name':self.name.get().strip(),'source_lang':language(self.source_box,self.source),
                'target_lang':language(self.target_box,self.target),'notes':self.notes.get('1.0','end-1c')}

    def _dirty(self):
        return self._values()!=profile_values(self.model.selected) if self.model.selected else bool(self.name.get().strip() or self.notes.get('1.0','end-1c'))

    def _remember_draft(self):
        if not self._loading:
            if self._dirty():self._drafts[self._selected_name]=self._values()
            else:self._drafts.pop(self._selected_name,None)

    def _language_label(self,code):
        label=next((label for label,value in self._language_codes.items() if value==code),None)
        if label is None:
            label=code;self._language_codes[label]=code
            self._choice_codes.append(code)
            for box in (self.source_box,self.target_box):box.configure(values=tuple(self._language_codes))
        return label

    @staticmethod
    def _put(widget,value):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',str(value));widget.configure(state='disabled')

    def _show(self,record,values=None):
        self._loading=True
        try:
            values=values or profile_values(record)
            self.name.set(values['name']);self.source.set(self._language_label(values['source_lang']));self.target.set(self._language_label(values['target_lang']))
            self.name_entry.configure(state='readonly' if record else 'normal')
            self.notes.delete('1.0','end');self.notes.insert('1.0',values['notes']);self.notes.edit_modified(False)
            record=record or {};progress=record.get('progress') or {}
            elapsed=max(0,int(progress.get('active_elapsed_ms') or 0))//1000
            scopes=progress.get('scopes',[])
            scope_text=(str(len(scopes))+' · '+', '.join(str(scope.get('source_lang',''))+' → '+str(scope.get('target_lang',''))+' ('+str(scope.get('records',0))+')' for scope in scopes[:8])) if isinstance(scopes,list) else str(scopes)
            self.progress.set('\n'.join((self.tr(ui_source('Completed segments'))+': '+str(progress.get('completed',0)),
                self.tr(ui_source('Total active time'))+f': {elapsed//3600:02d}:{elapsed//60%60:02d}:{elapsed%60:02d}',
                self.tr(ui_source('Saved contexts'))+': '+scope_text,self.tr(ui_source('Updated'))+': '+_timestamp(record.get('updated_at')),
                self.tr(ui_source('Latest translation'))+': '+_timestamp(record.get('latest_translation_at')))))
            empty=self.tr(ui_source('No translations yet'))
            self._put(self.summary_note,str(record.get('summary_note') or ''))
            self._put(self.summary,str(record.get('bounded_summary') or empty)[:6000])
            self._put(self.latest_source,str(record.get('latest_source') or empty)[:4000])
            self._put(self.latest_translation,str(record.get('latest_translation') or empty)[:6000])
            compression=record.get('compression') or {}
            method=str(compression.get('method','—'))
            self.compression.set(self.tr(ui_source('Compressed storage'))+': '+str(compression.get('raw_bytes',0))+' → '+str(compression.get('compressed_bytes',0))+' B · '+('zlib' if 'zlib' in method else method[:60]))
            self.canvas.yview_moveto(0)
        finally:self._loading=False
        self.cancel_delete(clear_status=False);self._update_actions()

    def _update_actions(self):
        saved=self.model.selected is not None
        self.delete_button.configure(state='normal' if saved else 'disabled')
        self.resume_button.configure(state='normal' if saved or self.name.get().strip() else 'disabled')
        self.resume_label.set(self.tr(ui_source('Save and resume translation') if self._dirty() or not saved else ui_source('Resume translation')))

    def _form_changed(self,*args):
        if self._loading:return
        self.cancel_delete(clear_status=False);self._update_actions()
        self.status.set(self.tr(ui_source('Unsaved changes')) if self._dirty() else '')

    def _notes_changed(self,event=None):
        if not self.notes.edit_modified():return
        self.notes.edit_modified(False);self._form_changed()

    def _error(self,error):
        self.status.set(self.tr(str(error)) or self.tr(ui_source('Operation failed')))

    def refresh(self,select_name=None,keep_draft=True):
        if keep_draft:self._remember_draft()
        wanted=select_name if select_name is not None else self._selected_name
        try:records=self.model.backend.list_profile_details()
        except Exception as error:self._error(error);return
        self._loading=True
        try:
            self.tree.delete(*self.tree.get_children());self._rows={}
            for index,record in enumerate(records):
                key=f'p{index}';self._rows[key]=record['name']
                self.tree.insert('', 'end',iid=key,text=record['name'],values=(str(record.get('source_lang',''))+' → '+str(record.get('target_lang','')),(record.get('progress') or {}).get('completed',0)))
            selected=next((key for key,name in self._rows.items() if name==wanted),None)
            if selected:self.tree.selection_set(selected);self.tree.see(selected)
        finally:self._loading=False
        if selected:self._select(wanted,remember=False)
        else:
            self.model.new();self._selected_name=None
            self._show(None,self._drafts.get(None,self.initial));self.status.set(self.tr(ui_source('New profile has not been saved') if self.name.get() else ui_source('No profiles yet. Create your first profile.')))

    def _select(self,name,remember=True):
        if remember:self._remember_draft()
        try:record=self.model.select(name)
        except Exception as error:self._error(error);return
        self._selected_name=name;self._show(record,self._drafts.get(name));self.status.set(self.tr(ui_source('Unsaved changes')) if self._dirty() else '')

    def _tree_selected(self,event=None):
        if self._loading:return
        selection=self.tree.selection()
        if selection and self._rows.get(selection[0])!=self._selected_name:self._select(self._rows[selection[0]])

    def new_profile(self):
        self._remember_draft();self.model.new();self._selected_name=None
        self.tree.selection_remove(*self.tree.selection())
        values=self._drafts.get(None,{**self.initial,'name':''})
        self._show(None,values);self.status.set(self.tr(ui_source('New profile has not been saved')));self.name_entry.focus_set()

    def save_selected(self):
        try:record=self.model.save(self._values())
        except Exception as error:self._error(error);return None
        self._drafts.pop(self._selected_name,None);self._selected_name=record['name'];self._drafts.pop(record['name'],None)
        self.refresh(select_name=record['name'],keep_draft=False)
        self.status.set(self.tr(ui_source('Profile saved')))
        self._notify_changed()
        return record

    def resume_selected(self):
        record=self.save_selected() if not self.model.selected or self._dirty() else self.model.selected
        if not record:return
        try:
            record=self.model.select(record['name'])
            if self.on_resume and self.on_resume(dict(record)) is False:
                self.status.set(self.tr(ui_source('Stop translation before switching profiles.')));return
        except Exception as error:self._error(error);return
        self.result=dict(record)
        self.close()

    def request_delete(self):
        try:
            if self.model.delete_target is None:
                self.model.arm_delete();self.delete_label.set(self.tr(ui_source('Click again to delete')))
                self.cancel_delete_button.pack(side='left',padx=8)
                self.status.set(self.tr(ui_source('Click Delete again to remove this profile and its local translation history. This cannot be undone.')));return
            name=self._selected_name;self.model.confirm_delete();self._drafts.pop(name,None);self._selected_name=None
            self.initial={**self.initial,'name':'','notes':''};self._drafts.pop(None,None)
            self.refresh(keep_draft=False);self.status.set(self.tr(ui_source('Profile deleted')))
            self._notify_changed()
        except Exception as error:
            self.cancel_delete(clear_status=False);self._error(error)

    def cancel_delete(self,clear_status=True):
        self.model.cancel_delete();self.delete_label.set(self.tr(ui_source('Delete profile')));self.cancel_delete_button.pack_forget()
        if clear_status:self.status.set('')

    def close(self):
        if self._closed:return
        self._closed=True;self.guard.close()
        try:self.destroy()
        except tk.TclError:pass

    def _notify_changed(self):
        try:
            if self.on_changed:self.on_changed()
        except Exception as error:self._error(error)
