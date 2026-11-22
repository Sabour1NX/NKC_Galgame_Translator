# SPDX-License-Identifier: MIT
"""Windows identity and actual window icons, independent of the header artwork."""
import ctypes
from pathlib import Path
import sys

APP_USER_MODEL_ID = 'NKC_Galgame_Translator'


def configure_process_identity():
    """Set Windows taskbar identity before creating Tk's first window."""
    if sys.platform != 'win32':
        return False
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    configure = shell.SetCurrentProcessExplicitAppUserModelID
    configure.argtypes = [ctypes.c_wchar_p]
    configure.restype = ctypes.c_long
    result = configure(APP_USER_MODEL_ID)
    if result < 0:
        raise OSError(f'Could not configure application identity: HRESULT 0x{result & 0xffffffff:08X}')
    return True


def install_window_icon(window, root):
    """Apply the multi-size ICO to this window and later Tk top-level windows."""
    icon = Path(root) / 'assets' / 'taiji.ico'
    if not icon.is_file():
        raise FileNotFoundError(f'Application icon missing: {icon}')
    window.iconbitmap(default=str(icon))
    window.iconbitmap(str(icon))
    return icon


def window_icon_handles(window):
    """Inspect native small/large icons; Tk's ICO getter returns an empty name."""
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = user.GetAncestor(window.winfo_id(), 2)
    return {name: int(user.SendMessageW(hwnd, 0x007f, kind, 0))
            for name, kind in (('small', 0), ('large', 1))}
