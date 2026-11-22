# SPDX-License-Identifier: MIT
"""Inspect a built x64 overlay DLL with pefile. Print results as JSON."""
import argparse
import hashlib
import json
from pathlib import Path

import pefile


def inspect(path: Path) -> dict:
    required = {"gl_ocr_bgra", "gl_overlay_fixed", "gl_overlay_options",
                "gl_overlay_anchored", "gl_overlay_styled", "gl_font_supports"}
    with pefile.PE(str(path)) as pe:
        flags = pe.OPTIONAL_HEADER.DllCharacteristics
        exports = {entry.name.decode("ascii") for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}
        config = pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct
        checks = {"x64": pe.FILE_HEADER.Machine == 0x8664, "aslr": bool(flags & 0x40),
                  "nx": bool(flags & 0x100), "high_entropy_va": bool(flags & 0x20),
                  "guard_cf": bool(flags & 0x4000), "cf_instrumented": bool(config.GuardFlags & 0x100),
                  "security_cookie": bool(config.SecurityCookie)}
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checks": checks, "missing_exports": sorted(required - exports)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dll", type=Path)
    result = inspect(parser.parse_args().dll)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if all(result["checks"].values()) and not result["missing_exports"] else 1)
