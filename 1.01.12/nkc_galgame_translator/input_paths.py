# SPDX-License-Identifier: MIT
"""Reject special/remote paths before opening explicitly selected local input."""
import ctypes
import os
from pathlib import Path, PureWindowsPath
import re
import stat


def local_file_path(value):
    """Return an absolute regular-file path; no shell expansion or URI fetching.

    Reparse points are not supported at this boundary. This is not a sandbox
    against a hostile process already able to replace files as this Windows user.
    """
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or len(raw) > 32700 or any(ord(c)<32 for c in raw):
        raise ValueError('Invalid local file path')
    normalized=raw.replace('/', '\\')
    if normalized.startswith(('\\\\','\\??\\','\\Device\\')):
        raise ValueError('Only ordinary local files are supported')
    windows=PureWindowsPath(normalized)
    for part in windows.parts:
        if part == windows.anchor:continue
        if ':' in part or part.endswith((' ','.')) or re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)',part,re.I):
            if part not in ('.','..'):
                raise ValueError('Special device/stream paths are unsupported')
    path=Path(os.path.abspath(raw))
    if os.name=='nt':
        drive_type=ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(path.anchor))
        if drive_type not in (2,3,5,6):
            raise ValueError('Remote or unavailable drives are unsupported')
    # Check components before stat/open follows a junction or symbolic link.
    for component in (*reversed(path.parents),path):
        info=component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('Reparse-point input paths are unsupported')
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Input must be a regular file')
    return path
