# SPDX-License-Identifier: MIT
"""Compatibility entry for the current 0.01.25 evidence report.

The historical 0.01.24 implementation has been replaced. This entry delegates
only to build_quality_report25.py and cannot generate a 0.01.24 current report.
Original private fixtures are intentionally absent from public source bundles;
supply reviewed evidence paths explicitly when rebuilding outside development.
"""
from pathlib import Path
import sys
from build_quality_report25 import ROOT, main


def run():
    if not any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        if not any(arg == "--game-before" or arg.startswith("--game-before=") or
                   arg == "--game-after" or arg.startswith("--game-after=")
                   for arg in sys.argv[1:]):
            before = ROOT / "reports/ocr-private/needy-window-original25.png"
            after = ROOT / "reports/needy-live-translated25.png"
            if not before.is_file() or not after.is_file():
                print("Live-game evidence is not bundled with public source. Supply verified "
                      "--game-before and --game-after PNGs, --live-measurement JSON, and the "
                      "OCR/latency evidence required by --help. No report was written.", file=sys.stderr)
                return 2
            sys.argv.extend(("--game-before", str(before), "--game-after", str(after)))
    try:
        main()
    except FileNotFoundError as error:
        print("Required recorded evidence is missing: " + str(error.filename) + ". "
              "Supply original fixtures and reviewed JSON paths using --help. "
              "This offline generator does not download evidence or call an API. "
              "No current report was written.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
