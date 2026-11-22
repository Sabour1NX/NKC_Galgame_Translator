# SPDX-License-Identifier: MIT
"""Read the screen pointer and derive a bounded crop from an existing frame."""
import ctypes
from ctypes import wintypes


def cursor_position():
    point=wintypes.POINT()
    get_cursor=ctypes.windll.user32.GetCursorPos
    get_cursor.argtypes=[ctypes.POINTER(wintypes.POINT)]
    get_cursor.restype=wintypes.BOOL
    return (point.x,point.y) if get_cursor(ctypes.byref(point)) else None


def attention_crop(pointer, selections):
    if pointer is None:
        return None
    px,py=pointer
    for index,(x,y,w,h) in enumerate(selections):
        if x<=px<x+w and y<=py<y+h:
            cw,ch=min(w,512),min(h,200)
            left=max(x,min(x+w-cw,(px//32)*32-cw//2))
            top=max(y,min(y+h-ch,(py//24)*24-ch//2))
            return index,left,top,cw,ch
    return None


def nearby(row,pointer):
    if pointer is None:
        return False
    px,py=pointer
    return (row['x']-64<=px<row['x']+row['w']+64
            and row['y']-34<=py<row['y']+row['h']+34)


class CursorLens:
    def __init__(self):
        self.anchor=None
        self.bounds=None
        self.crop=None

    def region(self,pointer,bounds):
        if not bounds or not pointer:
            self.anchor=self.crop=self.bounds=None
            return None
        boxes=(bounds,) if len(bounds)==4 and isinstance(bounds[0],int) else bounds
        chosen=next((b for b in boxes if b[0]<=pointer[0]<b[0]+b[2] and b[1]<=pointer[1]<b[1]+b[3]),None)
        if chosen is None:
            self.anchor=self.crop=self.bounds=None
            return None
        if (self.bounds==chosen and self.anchor and abs(pointer[0]-self.anchor[0])<=40
                and abs(pointer[1]-self.anchor[1])<=24):
            return self.crop
        self.bounds=chosen;self.anchor=pointer
        self.crop=attention_crop(pointer,[chosen])[1:]
        return self.crop
