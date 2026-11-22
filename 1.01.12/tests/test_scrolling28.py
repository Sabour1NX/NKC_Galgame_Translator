# SPDX-License-Identifier: MIT
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import pytest
from nkc_galgame_translator.scrolling import ComboboxPopupGuard


class Tcl:
    def __init__(self):self.posted=set();self.calls=[]
    def getboolean(self,value):return bool(value)
    def call(self,*args):
        self.calls.append(args)
        if args[:2] in [('winfo','exists'),('winfo','ismapped')]:return args[2] in self.posted
        if args[0]=='winfo':return {'rootx':100,'rooty':100,'width':200,'height':100}[args[1]]
        if args[0]=='ttk::combobox::Unpost':self.posted.discard(args[1]+'.popdown')


class Widget:
    def __init__(self,name,tcl,master=None):self.name=name;self.tk=tcl;self.master=master;self.bindings={};self.serial=0
    def __str__(self):return self.name
    def bind(self,event,callback,add=None):
        self.serial+=1;token=str(self.serial);self.bindings.setdefault(event,{})[token]=callback;return token
    def unbind(self,event,token):self.bindings[event].pop(token,None)
    def fire(self,event):
        for callback in tuple(self.bindings.get(event,{}).values()):callback(None)


class Canvas:
    def __init__(self,tcl):self.tk=tcl
    def yview(self,*args):self.tk.calls.append(('scroll',*args));return (0,1)
    def yview_scroll(self,*args):self.tk.calls.append(('scroll_units',*args))
    def yview_moveto(self,*args):self.tk.calls.append(('scroll_to',*args))


@pytest.mark.parametrize('event',['<Configure>','<Unmap>','<<NotebookTabChanged>>'])
def test_ancestor_layout_and_tab_changes_close_only_posted_list(event):
    tcl=Tcl();owner=Widget('.',tcl);parent=Widget('.frame',tcl,owner);combo=Widget('.frame.combo',tcl,parent)
    guard=ComboboxPopupGuard(owner);guard.register(combo)
    tcl.posted.add('.frame.combo.popdown');parent.fire(event)
    assert not tcl.posted
    assert ('ttk::combobox::Unpost','.frame.combo') in tcl.calls


@pytest.mark.parametrize('method,args',[('yview',('moveto',.5)),('yview_scroll',(2,'units')),('yview_moveto',(.5,))])
def test_scroll_closes_before_movement(method,args):
    tcl=Tcl();owner=Widget('.',tcl);combo=Widget('.c',tcl,owner);guard=ComboboxPopupGuard(owner);guard.register(combo)
    tcl.posted.add('.c.popdown');getattr(guard,method)(Canvas(tcl),*args)
    commands=[call[0] for call in tcl.calls]
    assert commands.index('ttk::combobox::Unpost')<next(i for i,c in enumerate(commands) if c.startswith('scroll'))


def test_query_is_non_mutating_and_unposted_does_not_create_popup():
    tcl=Tcl();owner=Widget('.',tcl);combo=Widget('.c',tcl,owner);guard=ComboboxPopupGuard(owner);guard.register(combo)
    assert guard.yview(Canvas(tcl))==(0,1)
    assert guard.close_popups()==0
    assert all(call[0] not in ('ttk::combobox::PopdownWindow','ttk::combobox::Unpost') for call in tcl.calls)


def test_cleanup_preserves_other_callbacks_and_is_idempotent():
    tcl=Tcl();owner=Widget('.',tcl);external=owner.bind('<Configure>',lambda _:None)
    guard=ComboboxPopupGuard(owner);combo=Widget('.c',tcl,owner);guard.register(combo)
    tcl.posted.add('.c.popdown');guard.close();guard.close()
    assert not tcl.posted
    assert list(owner.bindings['<Configure>'])==[external]
    assert guard.close_popups()==0


def test_popup_grab_outside_wheel_closes_but_inside_wheel_preserves_options():
    tcl=Tcl();owner=Widget('.',tcl);combo=Widget('.c',tcl,owner);guard=ComboboxPopupGuard(owner);guard.register(combo)
    tcl.posted.add('.c.popdown')
    inside=SimpleNamespace(widget='.c.popdown.f.l',x_root=150,y_root=120,delta=-120)
    assert guard._popup_wheel(inside) is None and tcl.posted
    outside=SimpleNamespace(widget='.c.popdown',x_root=20,y_root=20,delta=-120)
    assert guard._popup_wheel(outside)=='break' and not tcl.posted


def test_popup_event_of_another_owner_is_untouched():
    tcl=Tcl();owner=Widget('.',tcl);combo=Widget('.c',tcl,owner);guard=ComboboxPopupGuard(owner);guard.register(combo)
    tcl.posted.add('.other.popdown')
    assert guard._popup_wheel(SimpleNamespace(widget='.other.popdown',x_root=0,y_root=0,delta=-120)) is None
    assert tcl.posted=={'.other.popdown'}


def test_hidden_real_tk_registration_has_no_popdown_side_effect():
    try:root=tk.Tk();root.withdraw()
    except tk.TclError as error:pytest.skip('Tk desktop unavailable: '+str(error))
    try:
        frame=ttk.Frame(root);combo=ttk.Combobox(frame,values=('a','b'))
        guard=ComboboxPopupGuard(root);guard.register_tree(root)
        assert combo in guard._boxes
        assert not root.tk.getboolean(root.tk.call('winfo','exists',str(combo)+'.popdown'))
        guard.close_popups()
        assert not root.tk.getboolean(root.tk.call('winfo','exists',str(combo)+'.popdown'))
        guard.close()
        assert not root.tk.call('bind','ComboboxListbox','<MouseWheel>')
    finally:root.destroy()


def test_real_tcl_popup_with_local_grab_closes_on_outside_wheel():
    """Transparent off-screen Tcl popup; no focus change or visible test UI."""
    try:root=tk.Tk();root.withdraw()
    except tk.TclError as error:pytest.skip('Tk desktop unavailable: '+str(error))
    guard=None
    try:
        canvas=tk.Canvas(root,width=200,height=100,scrollregion=(0,0,200,2000),yscrollincrement=10);canvas.pack()
        frame=ttk.Frame(canvas);canvas.create_window(0,0,window=frame,anchor='nw')
        combo=ttk.Combobox(frame,values=('a','b'));combo.pack();root.update_idletasks()
        guard=ComboboxPopupGuard(root);guard.register_tree(root)
        popup=root.tk.call('ttk::combobox::PopdownWindow',str(combo))
        # Skip Tk's MapPopdown focus/global-grab path. Use a local grab only,
        # preserving the actual popup event target and Tcl class bindings.
        root.tk.call('bind',popup,'<Map>','break')
        root.tk.call('wm','attributes',popup,'-alpha',0)
        root.tk.call('wm','geometry',popup,'200x100+-30000+-30000')
        root.tk.call('wm','deiconify',popup);root.update_idletasks()
        assert int(root.tk.call('winfo','rootx',popup)) < -10000
        assert root.tk.getboolean(root.tk.call('winfo','ismapped',popup))
        root.tk.call('grab','set',popup)
        before=canvas.yview()[0]
        root.tk.call('event','generate',popup,'<MouseWheel>','-delta',-120,'-rootx',20,'-rooty',20,'-when','now')
        assert not root.tk.getboolean(root.tk.call('winfo','ismapped',popup))
        assert not root.tk.call('grab','current')
        assert canvas.yview()[0]>before
    finally:
        if guard:guard.close()
        root.destroy()


def test_nested_guard_cleanup_keeps_other_owner_class_listener():
    try:root=tk.Tk();root.withdraw()
    except tk.TclError as error:pytest.skip('Tk desktop unavailable: '+str(error))
    outer=inner=None
    try:
        outer=ComboboxPopupGuard(root);first=root.tk.call('bind','ComboboxPopdown','<MouseWheel>')
        window=tk.Toplevel(root);window.withdraw();inner=ComboboxPopupGuard(window)
        assert root.tk.call('bind','ComboboxPopdown','<MouseWheel>')!=first
        inner.close();window.destroy()
        assert root.tk.call('bind','ComboboxPopdown','<MouseWheel>').strip()==first.strip()
    finally:
        if inner:inner.close()
        if outer:outer.close()
        root.destroy()


def test_destroyed_toplevel_automatically_removes_scoped_class_hook():
    try:root=tk.Tk();root.withdraw()
    except tk.TclError as error:pytest.skip('Tk desktop unavailable: '+str(error))
    try:
        before=root.tk.call('bind','ComboboxPopdown','<MouseWheel>')
        window=tk.Toplevel(root);window.withdraw();guard=ComboboxPopupGuard(window)
        window.destroy()
        assert guard._closed
        assert root.tk.call('bind','ComboboxPopdown','<MouseWheel>').strip()==before.strip()
    finally:root.destroy()
