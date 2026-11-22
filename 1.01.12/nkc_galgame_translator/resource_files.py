# SPDX-License-Identifier: MIT
"""Load bundled UTF-8 application resources."""

from pathlib import Path

_RESOURCE_DIR = Path(__file__).with_name('resources')


def read_resource(name: str) -> str:
    return (_RESOURCE_DIR / name).read_text(encoding='utf-8')
