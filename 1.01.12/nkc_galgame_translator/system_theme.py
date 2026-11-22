# SPDX-License-Identifier: MIT
"""Read Windows app colors through the WinRT UISettings ABI."""

import ctypes
from ctypes import wintypes
from functools import lru_cache
from uuid import UUID


class Color(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint8) for name in ("alpha", "red", "green", "blue")]

    @property
    def rgb(self):
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"


RUNTIME_CLASS = "Windows.UI.ViewManagement.UISettings"
IID_UI_SETTINGS3 = (ctypes.c_ubyte * 16).from_buffer_copy(
    UUID("03021be4-5254-4781-8194-5168f7d06d7b").bytes_le)
UI_BACKGROUND, UI_FOREGROUND, UI_ACCENT = 0, 1, 5
RPC_E_CHANGED_MODE = -2147417850


@lru_cache(maxsize=1)
def _runtime():
    api = ctypes.WinDLL("combase")
    ptr = ctypes.c_void_p
    api.RoInitialize.argtypes = [ctypes.c_int]
    api.RoUninitialize.argtypes = []
    api.RoUninitialize.restype = None
    api.WindowsCreateString.argtypes = [wintypes.LPCWSTR, wintypes.UINT, ctypes.POINTER(ptr)]
    api.WindowsDeleteString.argtypes = [ptr]
    api.RoActivateInstance.argtypes = [ptr, ctypes.POINTER(ptr)]
    return api


def _method(instance, index, result, *args):
    vtable = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *args)(vtable[index])


def _modern_colors():
    api = _runtime()
    initialized = api.RoInitialize(0)
    if initialized < 0 and initialized != RPC_E_CHANGED_MODE:
        return None

    class_name = ctypes.c_void_p()
    instance = ctypes.c_void_p()
    settings = ctypes.c_void_p()
    try:
        if api.WindowsCreateString(RUNTIME_CLASS, len(RUNTIME_CLASS), ctypes.byref(class_name)) < 0:
            return None
        if api.RoActivateInstance(class_name, ctypes.byref(instance)) < 0:
            return None
        # IUnknown::QueryInterface and IUISettings3::GetColorValue.
        query = _method(instance, 0, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        if query(instance, ctypes.byref(IID_UI_SETTINGS3), ctypes.byref(settings)) < 0:
            return None
        value = _method(settings, 6, ctypes.c_long, ctypes.c_int, ctypes.POINTER(Color))
        colors = []
        for kind in (UI_BACKGROUND, UI_FOREGROUND, UI_ACCENT):
            color = Color()
            if value(settings, kind, ctypes.byref(color)) < 0:
                return None
            colors.append(color.rgb)
        return tuple(colors)
    finally:
        for pointer in (settings, instance):
            if pointer:
                _method(pointer, 2, wintypes.ULONG)(pointer)
        if class_name:
            api.WindowsDeleteString(class_name)
        if initialized >= 0:
            api.RoUninitialize()


def windows_colors():
    """Return background, foreground and accent as RGB strings."""
    try:
        colors = _modern_colors()
        if colors is not None:
            return colors
        get_color = ctypes.windll.user32.GetSysColor
        get_color.argtypes = [ctypes.c_int]
        get_color.restype = wintypes.DWORD
        colors = [get_color(index) for index in (5, 8, 13)]
        return tuple(Color(255, value & 255, value >> 8 & 255, value >> 16 & 255).rgb for value in colors)
    except (AttributeError, OSError):
        return "#FFFFFF", "#171717", "#0078D4"
