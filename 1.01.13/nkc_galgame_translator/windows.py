# SPDX-License-Identifier: MIT
"""Window metadata only; no hooks or injected input."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import PureWindowsPath

user32 = C.WinDLL('user32', use_last_error=True)
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
user32.IsWindow.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
user32.EnumWindows.argtypes = [CALLBACK, W.LPARAM]
kernel32 = C.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
kernel32.WaitForSingleObject.restype = W.DWORD
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]

class GameProcess:
    """Track one process instance, even if it recreates its top-level window."""

    def __init__(self, pid):
        self.pid = pid
        self._handle = None
        self._exited = False
        self._open()

    def _open(self):
        self._handle = kernel32.OpenProcess(0x00100000, False, self.pid)  # SYNCHRONIZE
        self._exited = not self._handle and C.get_last_error() == 87  # No such PID

    def exited(self):
        if not self._handle and not self._exited:
            self._open()
        return self._exited or bool(self._handle and kernel32.WaitForSingleObject(self._handle, 0) == 0)

    def close(self):
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None


def process_path(pid):
    handle=kernel32.OpenProcess(0x1000,False,pid)
    if not handle:return ''
    try:
        buf=C.create_unicode_buffer(32768);size=W.DWORD(len(buf))
        return buf.value if kernel32.QueryFullProcessImageNameW(handle,0,buf,C.byref(size)) else ''
    finally:kernel32.CloseHandle(handle)

def enable_dpi():
    try:
        user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except (AttributeError, OSError):
        pass


# Exclude known shell/input/our helper surfaces, never arbitrary title keywords
# or a whitelist of game engines. Ordinary English applications remain eligible.
_SHELL_PROCESSES = frozenset({'explorer.exe','dwm.exe','shellexperiencehost.exe',
    'startmenuexperiencehost.exe','searchhost.exe','searchapp.exe','sihost.exe'})
_INPUT_PROCESSES = frozenset({'textinputhost.exe','ctfmon.exe','tabtip.exe','osk.exe'})
_OVERLAY_PROCESSES = frozenset({'gamebar.exe','gamebarftserver.exe','gamebarpresencewriter.exe'})
_EXCLUDED_CLASSES = frozenset({'cabinetwclass','explorewclass','progman','workerw',
    'shell_traywnd','shell_secondarytraywnd','multitaskingviewframe',
    'msctfime ui','ime','cicmarshalwndclass','tooltips_class32','sysshadow',
    'nkc_galgame_translatorreplacement','xaml_windowedpopupclass'})


def translation_target(row):
    """Metadata-based eligibility; unknown executables are allowed, not guessed."""
    exe=PureWindowsPath(str(row.get('process_path') or row.get('exe_name') or '')).name.casefold()
    cls=str(row.get('class_name') or '').casefold()
    return (exe not in _SHELL_PROCESSES | _INPUT_PROCESSES | _OVERLAY_PROCESSES and
            cls not in _EXCLUDED_CLASSES and row.get('pid') != os.getpid())


def window_metadata(hwnd, *, paths=None):
    """Read a fresh identity snapshot; process paths are queried only on selection/listing."""
    if not user32.IsWindow(hwnd):return None
    pid=W.DWORD();user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
    if not pid.value:return None
    n=min(4096,max(0,user32.GetWindowTextLengthW(hwnd)))
    title=C.create_unicode_buffer(n+1);user32.GetWindowTextW(hwnd,title,n+1)
    cls=C.create_unicode_buffer(256);user32.GetClassNameW(hwnd,cls,len(cls))
    if paths is not None and pid.value in paths:path=paths[pid.value]
    else:
        path=process_path(pid.value)
        if paths is not None:paths[pid.value]=path
    # A closing window or handle reused by another process is not a valid snapshot.
    verify=W.DWORD();user32.GetWindowThreadProcessId(hwnd,C.byref(verify))
    if not user32.IsWindow(hwnd) or verify.value!=pid.value:return None
    return {'hwnd':hwnd,'pid':pid.value,'title':title.value,'process_path':path,
            'exe_name':PureWindowsPath(path).name,'class_name':cls.value}


def window_state(hwnd, expected_pid):
    """Cheap state probe for the UI's one-second timer; never opens a process."""
    if not user32.IsWindow(hwnd):return 'closed'
    pid=W.DWORD();user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
    if pid.value!=expected_pid:return 'replaced'
    if user32.IsIconic(hwnd):return 'minimized'
    if not user32.IsWindowVisible(hwnd):return 'hidden'
    return 'active' if user32.GetForegroundWindow()==hwnd else 'background'

def window_list():
    rows, paths = [], {}
    @CALLBACK
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                row=window_metadata(hwnd,paths=paths)
                if row and translation_target(row):rows.append(row)
        return True
    user32.EnumWindows(visit, 0)
    return rows

def client_rect(hwnd):
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    rect, point = W.RECT(), W.POINT()
    if not user32.GetClientRect(hwnd, C.byref(rect)) or not user32.ClientToScreen(hwnd, C.byref(point)):
        return None
    return point.x, point.y, rect.right, rect.bottom

def foreground(hwnd, expected_pid=None):
    if expected_pid is not None:
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value != expected_pid:
            return False
    return user32.GetForegroundWindow() == hwnd

def virtual_screen():
    return tuple(user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def intersect_rectangles(rect, bounds):
    """Intersect (x, y, width, height) rectangles without changing origins.

    Negative desktop coordinates are valid. Empty/minimized client rectangles
    and edge-only contact have no capturable pixels.
    """
    if rect is None or bounds is None:
        return None
    x,y,w,h=rect;bx,by,bw,bh=bounds
    if w<=0 or h<=0 or bw<=0 or bh<=0:
        return None
    left,top=max(x,bx),max(y,by)
    right,bottom=min(x+w,bx+bw),min(y+h,by+bh)
    return (left,top,right-left,bottom-top) if right>left and bottom>top else None


def visible_client_rect(hwnd):
    """Desktop-bounded client rectangle for capture; no foreground activation.

    This is clipping geometry, not an occlusion or foreground check. Production
    callers retain their window/PID binding and foreground validation.
    """
    return intersect_rectangles(client_rect(hwnd),virtual_screen())


def visible_client_selections(relative, client, desktop=None):
    """Place saved selections against the FULL client, then clip to desktop.

    Never rebase saved offsets onto a clipped client origin: doing that shifts
    selected text when a game moves across a screen edge or a negative monitor.
    The resulting screen rectangles remain subsets of the selected game client.
    """
    from .selection_regions import client_selections
    if client is None:
        return None
    desktop=virtual_screen() if desktop is None else desktop
    selections=client_selections(relative,client)
    if not relative:
        return intersect_rectangles(selections,desktop)
    return tuple(clipped for box in selections or ()
                 if (clipped:=intersect_rectangles(box,desktop)) is not None) or None
