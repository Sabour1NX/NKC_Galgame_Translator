# SPDX-License-Identifier: MIT
"""Install the verified public Windows build for the current user."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from queue import Empty, SimpleQueue
import re
import shutil
import stat
import subprocess
import struct
import winreg
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import tkinter as tk
from tkinter import filedialog, ttk
import zipfile

VERSION = "1.01.12"
EXE = "NKC_Galgame_Translator.exe"
ARCHIVE_ROOT = "NKC_Galgame_Translator"
ASSETS = Path(__file__).resolve().parent
STRINGS = json.loads((ASSETS / "install_strings.json").read_text(encoding="utf-8"))
GREETINGS = {"zh-CN": "Greeting_cn.html", "en": "Greeting.en.html", "ja": "Greeting.ja.html"}
PAYLOAD = ASSETS / "release.zip"
SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_.+@ -]+")
GREETING_PROTOCOL = "nkc-translater"
TOUR_SCRIPT = "docs/tour.js"


def extract_release(payload: Path, destination: Path) -> None:
    seen = set()
    with zipfile.ZipFile(payload) as archive:
        members = archive.infolist()
        if len(members) > 10_000 or sum(item.file_size for item in members) > 1024**3:
            raise ValueError("The release size is invalid.")
        for item in members:
            parts = PurePosixPath(item.filename).parts
            if (len(parts) < 2 or parts[0] != ARCHIVE_ROOT or item.is_dir()
                    or stat.S_ISLNK(item.external_attr >> 16)
                    or any(not SAFE_SEGMENT.fullmatch(part) or part in (".", "..")
                           or part.endswith((".", " ")) for part in parts)):
                raise ValueError("The release contains an invalid file path.")
            relative = Path(*parts[1:])
            folded = relative.as_posix().lower()
            if folded in seen:
                raise ValueError("The release contains duplicate file paths.")
            seen.add(folded)
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, output.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def verify_layout(target: Path) -> None:
    expected = [target / EXE, target / "assets/fonts/SourceHanSansSC-Regular.otf",
                target / "assets/fonts/SourceHanSansSC-Medium.otf",
                target / TOUR_SCRIPT, target / "docs/tour.css",
                *(target / "docs" / name for name in GREETINGS.values())]
    if not all(path.is_file() for path in expected):
        raise ValueError("The release is incomplete.")


def default_directory(local_app_data: Path) -> Path:
    return local_app_data / "Programs" / ARCHIVE_ROOT / VERSION


def install(payload: Path, target: Path, language: str) -> Path:
    greeting = GREETINGS[language]
    if not target.is_absolute() or target == Path(target.anchor):
        raise ValueError(STRINGS[language]["invalid_path"])
    if target.is_symlink() or target.is_junction():
        raise ValueError("The installation directory cannot be redirected.")
    target.parent.mkdir(parents=True, exist_ok=True)
    empty_folder = target.is_dir() and not any(target.iterdir())
    if target.exists() and not empty_folder:
        if not (target / EXE).is_file():
            raise ValueError(STRINGS[language]["occupied"])
        verify_layout(target)
        script = target / TOUR_SCRIPT
        for directory in (target, script.parent):
            if directory.is_symlink() or directory.is_junction():
                raise ValueError("The installation directory cannot be redirected.")
        with zipfile.ZipFile(payload) as archive:
            updated = archive.read(f"{ARCHIVE_ROOT}/{TOUR_SCRIPT}")
        if not script.is_symlink() and script.read_bytes() != updated:
            with TemporaryDirectory(prefix=".tour-", dir=script.parent) as temporary:
                replacement = Path(temporary) / script.name
                replacement.write_bytes(updated)
                replacement.replace(script)
    else:
        with TemporaryDirectory(prefix=".nishokuchou-", dir=target.parent) as temporary:
            stage = Path(temporary) / VERSION
            extract_release(payload, stage)
            verify_layout(stage)
            local = stage / "config" / "local.json"
            with local.open("x", encoding="utf-8") as settings:
                json.dump({"app_language": language, "app_language_selected": True}, settings)
            if empty_folder:
                target.rmdir()
            try:
                stage.rename(target)
            except OSError:
                if empty_folder:
                    target.mkdir(exist_ok=True)
                raise
    return target / "docs" / greeting


def create_shortcuts(target: Path, language: str, test_root: Path | None = None) -> None:
    label = STRINGS[language]["shortcut_name"]
    other = STRINGS["en" if language == "zh-CN" else "zh-CN"]["shortcut_name"]
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    args = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(ASSETS / "install_shortcuts.ps1"), "-Executable", str(target / EXE),
            "-Label", label, "-AlternateLabel", other]
    if test_root is not None:
        args.extend(["-TestRoot", str(test_root)])
    subprocess.run(args, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


def register_greeting_link(target: Path):
    base = rf"Software\Classes\{GREETING_PROTOCOL}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:NKC_Translater")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as command:
        winreg.SetValueEx(command, "", 0, winreg.REG_SZ, f'"{target / EXE}"')


def open_installed_tour(target: Path, language: str, spawn=subprocess.Popen):
    spawn([str(target / EXE), "--welcome", language], cwd=target)


def self_test(result: Path) -> None:
    checks = {}
    with TemporaryDirectory(prefix="nishokuchou-setup-test-") as directory:
        root = Path(directory)
        for language, name in GREETINGS.items():
            installed = default_directory(root) if language == "en" else root / ("Custom Path " + language)
            if language == "zh-CN":
                installed.mkdir()
            opened = []
            greeting = install(PAYLOAD, installed, language)
            license_digest = hashlib.sha256((installed / "LICENSE").read_bytes()).hexdigest()
            if license_digest != "c944dfb45a6977c03d09c22750b76d1f7004c12c3363b6b17a4851f6409cb84f":
                raise RuntimeError("Installed project license checksum differs from the reviewed MIT text.")
            open_installed_tour(installed, language, lambda args, cwd: opened.append((args, cwd)))
            if (greeting != installed / "docs" / name or
                    opened != [([str(installed / EXE), "--welcome", language], installed)]):
                raise RuntimeError("The wrong tour was selected.")
            local = installed / "config" / "local.json"
            data = json.loads(local.read_text(encoding="utf-8"))
            if data != {"app_language": language, "app_language_selected": True}:
                raise RuntimeError("The installation language was not persisted.")
            if (installed / "config" / "credentials.bin").exists():
                raise RuntimeError("A private credential was found.")
            script = installed / TOUR_SCRIPT
            updated = script.read_bytes()
            if f"{GREETING_PROTOCOL}://open".encode("ascii") not in updated:
                raise RuntimeError("The tour and Windows launcher use different protocols.")
            script.write_text("/* Previous tour release */", encoding="ascii")
            before = local.read_bytes()
            install(PAYLOAD, installed, language)
            if local.read_bytes() != before or script.read_bytes() != updated:
                raise RuntimeError("Reinstall did not update the tour and preserve configuration.")
            shortcut_root = root / "shortcuts"
            create_shortcuts(installed, language, shortcut_root)
            for folder in ("Desktop", "Programs"):
                if not (shortcut_root / folder / (STRINGS[language]["shortcut_name"] + ".lnk")).is_file():
                    raise RuntimeError("Localized shortcut missing.")
            checks[language] = name
        occupied = root / "occupied"
        occupied.mkdir()
        marker = occupied / "user.txt"
        marker.write_text("keep", encoding="utf-8")
        try:
            install(PAYLOAD, occupied, "en")
        except ValueError:
            assert marker.read_text(encoding="utf-8") == "keep"
        else:
            raise RuntimeError("An unrelated installation folder was accepted.")
        bad_payload = root / "unsafe.zip"
        with zipfile.ZipFile(bad_payload, "w") as archive:
            archive.writestr(ARCHIVE_ROOT + "/../../outside.txt", "unexpected")
        try:
            install(bad_payload, root / "unsafe" / VERSION, "en")
        except ValueError:
            if (root / "outside.txt").exists():
                raise RuntimeError("The installer wrote outside its staging folder.")
        else:
            raise RuntimeError("The installer accepted an invalid file path.")
    result.write_text(json.dumps({"passed": True, "version": VERSION,
                                  "installed_mit_sha256": license_digest,
                                  "custom_directory_verified": True, "greetings": checks, "greeting_protocol": GREETING_PROTOCOL,
                                  "existing_tour_updated": True, "existing_config_preserved": True,
                                  "unsafe_archive_rejected": True}, indent=2), encoding="utf-8")


def default_language() -> str:
    language = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff
    return {0x04: "zh-CN", 0x11: "ja"}.get(language, "en")


def show_installer() -> None:
    root = tk.Tk()
    root.resizable(False, False)
    root.option_add("*Font", ("Segoe UI", 10))
    labels = {row["name"]: code for code, row in STRINGS.items()}
    current = tk.StringVar(value=STRINGS[default_language()]["name"])
    settings_root = Path(os.environ["LOCALAPPDATA"])
    target = default_directory(settings_root)
    destination = tk.StringVar(value=str(target))
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill="both", expand=True)
    heading = ttk.Label(frame, font=("Segoe UI", 16, "bold"))
    heading.grid(row=0, columnspan=3, sticky="w")
    language_label = ttk.Label(frame)
    language_label.grid(row=1, column=0, sticky="w", pady=(16, 8))
    language_box = ttk.Combobox(frame, state="readonly", textvariable=current,
                                values=tuple(labels), width=22)
    language_box.grid(row=1, column=1, columnspan=2, sticky="w", padx=(16, 0))
    intro = ttk.Label(frame, wraplength=460)
    intro.grid(row=2, columnspan=3, sticky="w", pady=(4, 0))
    path_label = ttk.Label(frame)
    path_label.grid(row=3, column=0, sticky="w", padx=(0, 8))
    path_entry = ttk.Entry(frame, textvariable=destination, width=46)
    path_entry.grid(row=3, column=1, sticky="ew")

    def browse():
        initial = Path(destination.get()) if destination.get() else settings_root
        initial = next((p for p in (initial, *initial.parents) if p.is_dir()), settings_root)
        selected = filedialog.askdirectory(parent=root, title=STRINGS[labels[current.get()]]["directory"],
                                           initialdir=str(initial), mustexist=False)
        if selected:
            destination.set(selected)

    browse_button = ttk.Button(frame, command=browse)
    browse_button.grid(row=3, column=2, padx=(8, 0))
    status = ttk.Label(frame, wraplength=460)
    status.grid(row=4, columnspan=3, sticky="w", pady=(12, 0))

    def launch():
        os.startfile(str(target / EXE))
        root.destroy()

    action = ttk.Button(frame)
    action.grid(row=5, column=1, sticky="e", pady=(16, 0))
    close = ttk.Button(frame, command=root.destroy)
    close.grid(row=5, column=2, sticky="e", padx=(8, 0), pady=(16, 0))

    def sync(_=None):
        strings = STRINGS[labels[current.get()]]
        root.title(strings["title"])
        path_label.configure(text=strings["directory"])
        browse_button.configure(text=strings["browse"])
        heading.configure(text=strings["title"])
        language_label.configure(text=strings["language"])
        intro.configure(text=strings["intro"])
        action.configure(text=strings["install"])
        close.configure(text=strings["close"])

    def begin():
        nonlocal target
        code = labels[current.get()]
        strings = STRINGS[code]
        if sys.platform != "win32" or struct.calcsize("P") != 8:
            status.configure(text=strings["bad_arch"])
            return
        chosen = Path(destination.get().strip())
        if not chosen.is_absolute():
            status.configure(text=strings["invalid_path"])
            return
        target = Path(os.path.abspath(chosen))
        status.configure(text=strings["progress"])
        for widget in (action, close, language_box, path_entry, browse_button):
            widget.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        results = SimpleQueue()

        def prepare():
            try:
                greeting = install(PAYLOAD, target, code)
                create_shortcuts(target, code)
                results.put((greeting, None))
            except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
                results.put((None, str(error)))

        def finish():
            try:
                greeting, error = results.get_nowait()
            except Empty:
                root.after(60, finish)
                return
            root.protocol("WM_DELETE_WINDOW", root.destroy)
            action.configure(state="normal")
            close.configure(state="normal")
            if error is not None:
                status.configure(text=strings["failed"] + error)
                path_entry.configure(state="normal")
                browse_button.configure(state="normal")
                language_box.configure(state="readonly")
                return
            try:
                try:
                    register_greeting_link(target)
                except OSError:
                    pass
                open_installed_tour(target, code)
            except OSError:
                status.configure(text=strings["no_browser"])
            else:
                root.destroy()
                return
            action.configure(text=strings["launch"], command=launch)

        Thread(target=prepare, daemon=True).start()
        root.after(60, finish)

    action.configure(command=begin)
    language_box.bind("<<ComboboxSelected>>", sync)
    sync()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        self_test(Path(sys.argv[2]))
    else:
        show_installer()
