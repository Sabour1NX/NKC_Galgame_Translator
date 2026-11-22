# SPDX-License-Identifier: MIT
"""Minimal startup diagnostics: no exception messages, locals or source lines."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import traceback


def _identifier(value):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(value))[:100]


def startup_record(error: BaseException) -> dict:
    """Return bounded structural evidence, never user text or credential values."""
    frames = traceback.extract_tb(error.__traceback__)[-8:]
    return {
        'schema': 1,
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'message': '\u542f\u52a8\u672a\u5b8c\u6210\u3002\u8bf7\u68c0\u67e5\u5b8c\u6574\u53d1\u884c\u76ee\u5f55\u3001\u5199\u5165\u6743\u9650\u548c\u914d\u5957\u4f9d\u8d56\u3002',
        'error_type': _identifier(type(error).__name__),
        'frames': [{'file': _identifier(Path(f.filename).name),
                    'line': f.lineno, 'function': _identifier(f.name)} for f in frames],
        'privacy': '\u4e0d\u8bb0\u5f55\u5f02\u5e38\u6b63\u6587\u3001\u6e90\u7801\u884c\u3001\u5c40\u90e8\u53d8\u91cf\u3001\u5b8c\u6574\u8def\u5f84\u6216\u73af\u5883\u53d8\u91cf\u3002',
    }


def write_startup_report(root: Path, error: BaseException) -> Path | None:
    """Atomically replace a bounded report; an unwritable folder cannot recurse."""
    temporary = None
    try:
        target = Path(root) / 'startup-error.log'
        data = json.dumps(startup_record(error), ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.startup-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data + '\n')
        os.replace(temporary, target)
        return target
    except OSError:
        return None
    finally:
        if temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
