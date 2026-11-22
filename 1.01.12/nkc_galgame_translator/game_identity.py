# SPDX-License-Identifier: MIT
"""Local learning identity, separate from the shared translation dictionary."""
import hashlib
import ntpath
import unicodedata


def warmup_identity(game, process_path=''):
    if isinstance(game,str) and game.strip():
        return 'profile:'+unicodedata.normalize('NFC',game).strip()
    if isinstance(process_path,str) and ntpath.isabs(process_path) and process_path.lower().endswith('.exe'):
        path=ntpath.normcase(ntpath.normpath(process_path))
        return 'exe:'+hashlib.sha256(path.encode('utf-8')).hexdigest()
    return None
