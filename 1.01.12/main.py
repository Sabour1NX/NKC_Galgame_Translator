# SPDX-License-Identifier: MIT
import sys
from pathlib import Path
if __name__ == '__main__':
    try:
        if '--self-test' in sys.argv:
            from nkc_galgame_translator.selfcheck import run
            run()
        else:
            launch = True
            if len(sys.argv) == 3 and sys.argv[1] == '--welcome':
                from nkc_galgame_translator.welcome import show_before_start
                root = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
                try:
                    launch = show_before_start(root, sys.argv[2])
                except OSError:
                    pass
            if launch:
                from nkc_galgame_translator.app import main
                main()
    except Exception as error:
        root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
        from nkc_galgame_translator.diagnostics import write_startup_report
        write_startup_report(root, error)
        sys.exit(1)
