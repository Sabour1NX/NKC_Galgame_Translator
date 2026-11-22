# SPDX-License-Identifier: MIT
"""Register the bundled interface font for this process."""

import ctypes
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path

UI_BODY_SIZE = 11
UI_SMALL_SIZE = 10


@lru_cache(maxsize=4)
def load_ui_font(root: Path) -> str:
    add_font = ctypes.windll.gdi32.AddFontResourceExW
    add_font.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
    add_font.restype = ctypes.c_int
    for name, family in (('Medium', 'Source Han Sans SC Medium'), ('Regular', 'Source Han Sans SC')):
        font = root / 'assets' / 'fonts' / f'SourceHanSansSC-{name}.otf'
        if font.is_file() and add_font(str(font), 0x10, None):
            return family
    return 'Microsoft YaHei UI'
