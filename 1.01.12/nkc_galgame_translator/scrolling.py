# SPDX-License-Identifier: MIT
"""Close Tk combobox popdowns before their owner moves out from under them."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import weakref


class ComboboxPopupGuard:
    """One guard per top-level; no global grabs, polling or bind_all hooks.

    Register newly built subtrees. Route canvas scroll commands through yview /
    yview_scroll, including the scrollbar command, so even programmatic scrolling
    closes a posted list before moving the canvas window. Ancestor Configure,
    Unmap and notebook changes cover movement, resize and tab switches.
    """
    def __init__(self, owner):
        self.owner = owner
        self._boxes = weakref.WeakSet()
        self._bindings = {}
        self._closing = False
        self._closed = False
        self._class_bindings = []
        self._class_owner = owner._root() if hasattr(owner,'_root') else owner
        self._watch(owner)
        self._destroy_token=owner.bind('<Destroy>',self._owner_destroyed,add='+')
        # A posted ttk list owns the grab; outside wheel events can reach the
        # Tcl-created popdown rather than the canvas under the pointer. Scope
        # these class listeners to registered boxes, leaving option-list wheel
        # scrolling inside the popup unchanged.
        if hasattr(owner, 'bind_class'):
            for tag in ('ComboboxListbox','ComboboxPopdown'):
                token=self._class_owner.bind_class(tag,'<MouseWheel>',self._popup_wheel,add='+')
                self._class_bindings.append((tag,'<MouseWheel>',token))

    def _watch(self, widget):
        key = str(widget)
        if self._closed or (key in self._bindings and self._bindings[key][0]() is widget):
            return
        bindings = []
        for event in ('<Configure>', '<Unmap>', '<<NotebookTabChanged>>'):
            bindings.append((event, widget.bind(event, self.close_popups, add='+')))
        self._bindings[key] = (weakref.ref(widget), bindings)

    def _owner_destroyed(self,event):
        if getattr(event,'widget',None) is self.owner:
            self.close()

    def register(self, combobox):
        if self._closed:
            return combobox
        self._boxes.add(combobox)
        # Popdown/listbox widgets are deliberately never watched: their own
        # mapping must not immediately dismiss a freshly posted list.
        ancestor = combobox
        while ancestor is not None:
            self._watch(ancestor)
            if ancestor is self.owner:
                break
            ancestor = getattr(ancestor, 'master', None)
        return combobox

    def register_tree(self, widget):
        if isinstance(widget, ttk.Combobox):
            self.register(widget)
        for child in widget.winfo_children():
            self.register_tree(child)
        return widget

    def close_popups(self, event=None):
        """Unpost only visible lists. Looking up a popup must not create one."""
        if self._closed or self._closing:
            return 0
        self._closing = True
        count = 0
        try:
            for box in tuple(self._boxes):
                try:
                    popup = str(box) + '.popdown'
                    if box.tk.getboolean(box.tk.call('winfo', 'exists', popup)) and \
                            box.tk.getboolean(box.tk.call('winfo', 'ismapped', popup)):
                        box.tk.call('ttk::combobox::Unpost', str(box))
                        count += 1
                except tk.TclError:
                    # Destroyed children can remain weakly referenced until
                    # their controller lets go of them.
                    self._boxes.discard(box)
        finally:
            self._closing = False
        return count

    def yview(self, canvas, *args):
        if args:
            self.close_popups()
        return canvas.yview(*args)

    def yview_scroll(self, canvas, number, what='units'):
        self.close_popups()
        return canvas.yview_scroll(number, what)

    def yview_moveto(self, canvas, fraction):
        self.close_popups()
        return canvas.yview_moveto(fraction)

    def _popup_wheel(self, event):
        if self._closed:
            return
        path=str(event.widget)
        for box in tuple(self._boxes):
            popup=str(box)+'.popdown'
            if path!=popup and not path.startswith(popup+'.'):
                continue
            try:
                x=int(box.tk.call('winfo','rootx',popup));y=int(box.tk.call('winfo','rooty',popup))
                width=int(box.tk.call('winfo','width',popup));height=int(box.tk.call('winfo','height',popup))
                if x<=event.x_root<x+width and y<=event.y_root<y+height:
                    return  # Wheel within the list continues normal scrolling.
                self.close_popups()
                ancestor=box.master
                while ancestor is not None:
                    if isinstance(ancestor,tk.Canvas):
                        delta=int(event.delta)
                        steps=-int(delta/120) or (-1 if delta>0 else 1 if delta<0 else 0)
                        if steps:ancestor.yview_scroll(steps,'units')
                        break
                    ancestor=getattr(ancestor,'master',None)
                return 'break'
            except (tk.TclError,TypeError,ValueError):
                self.close_popups()
                return 'break'

    def close(self):
        if self._closed:
            return
        self.close_popups()
        self._closed = True
        for tag,event,token in self._class_bindings:
            try:
                # tkinter's unbind_class has no funcid parameter. _unbind is
                # the same selective implementation used by widget.unbind.
                self._class_owner._unbind(('bind',tag,event),token)
            except tk.TclError:
                pass
        self._class_bindings.clear()
        if self._destroy_token:
            try:self.owner.unbind('<Destroy>',self._destroy_token)
            except tk.TclError:pass
            self._destroy_token=None
        for reference, bindings in self._bindings.values():
            widget = reference()
            if widget is None:
                continue
            for event, token in bindings:
                try:
                    if token:
                        widget.unbind(event, token)
                except tk.TclError:
                    pass
        self._bindings.clear()
        self._boxes.clear()
