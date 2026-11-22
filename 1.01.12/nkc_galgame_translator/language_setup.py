# SPDX-License-Identifier: MIT
"""Guide first-time users through one native setup window."""

import tkinter as tk
from tkinter import ttk

from .agreement import AGREEMENT_TITLE
from .cuda_settings_ui import CudaControls
from .feature_ui import EXPORT_TITLE, EXPORT_WARNING, ThemeFields, choose_directory
from .i18n import NATIVE_NAMES, SUPPORTED, agreement_text, ui_source
from .localization_export import export_preferences
from .themes import validate_theme
from .tuning import validate_tuning


CUDA_FIELDS = ("cuda_enabled", "cuda_quality", "cuda_memory_mb")


class InitializationDialog:
    def __init__(self, app):
        self.app = app
        self.steps = []
        if app.config.get("app_language_selected") is not True:
            self.steps.append(("Interface language", self.language_page))
        if not app.agreement_accepted:
            self.steps.append(("User agreement", self.agreement_page))
        if "interface_theme" not in app.config:
            self.steps.extend((("Interface theme", self.theme_page),
                               ("CUDA text recognition", self.ocr_page)))
        if app.config.get("localization_setup_complete") is not True:
            self.steps.append(("Developer tools (Beta)", self.tools_page))

        self.index = 0
        self.preferences = {}
        self.window = tk.Toplevel(app.root)
        self.window.title(self.label("First-time setup"))
        self.window.transient(app.root)
        self.window.protocol("WM_DELETE_WINDOW", app.close)
        width = min(680, self.window.winfo_screenwidth() - 64)
        height = min(550, self.window.winfo_screenheight() - 96)
        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.shell = ttk.Frame(self.window, padding=26)
        self.shell.pack(fill="both", expand=True)
        self.render()
        self.window.after_idle(self.activate)

    def label(self, english):
        return self.app.tr(ui_source(english))

    def activate(self):
        if self.window.winfo_exists():
            self.window.grab_set()
            self.window.lift()

    def render(self):
        for child in self.shell.winfo_children():
            child.destroy()
        self.window.title(self.label("First-time setup"))
        name, build = self.steps[self.index]
        progress = self.label("Step {current} of {total}").format(
            current=self.index + 1, total=len(self.steps))
        ttk.Label(self.shell, text=progress, style="Hint.TLabel").pack(anchor="w")
        ttk.Label(self.shell, text=self.label(name), font=(self.app.ui_font, 23, "bold")).pack(
            anchor="w", pady=(5, 14))
        ttk.Separator(self.shell).pack(fill="x")

        footer = ttk.Frame(self.shell)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        self.error = tk.StringVar(master=self.window)
        ttk.Label(footer, textvariable=self.error, style="Hint.TLabel", wraplength=540).pack(
            anchor="w", pady=(0, 8))
        buttons = ttk.Frame(footer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.label("Exit"), command=self.app.close).pack(side="left")
        button_text = "Finish setup" if self.index == len(self.steps) - 1 else "Continue setup"
        self.next_button = ttk.Button(buttons, text=self.label(button_text),
                                      style="Accent.TButton", command=self.advance)
        self.next_button.pack(side="right")

        body = ttk.Frame(self.shell)
        body.pack(fill="both", expand=True, pady=(14, 0))
        self.commit_page = build(body)
        self.next_button.focus_set()

    def advance(self):
        try:
            if not self.commit_page():
                return False
            if self.index + 1 == len(self.steps):
                self.app.save_initial_preferences(self.preferences)
                self.close()
                self.app.root.after_idle(self.app.show_initial_setup)
            else:
                self.index += 1
                self.render()
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            self.error.set(self.app.tr(self.app.settings_error_message(error)))
            return False
        return True

    def language_page(self, body):
        self.app._hint(body, ui_source("The Windows display language is preselected. You can change it later in Settings.")).pack(
            anchor="w", pady=(0, 14))
        self.language = tk.StringVar(master=self.window, value=self.app.ui_language)
        for code in SUPPORTED:
            ttk.Radiobutton(body, text=NATIVE_NAMES[code], variable=self.language,
                            value=code).pack(anchor="w", pady=7)
        return self.save_language

    def save_language(self):
        code = self.language.get()
        if code not in SUPPORTED:
            return False
        self.app.config = self.app.config_store.save(
            {**self.app.config, "app_language": code, "app_language_selected": True})
        self.app.apply_ui_language(code)
        return True

    def agreement_page(self, body):
        ttk.Label(body, text=self.app.tr(AGREEMENT_TITLE), style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        consent = ttk.Checkbutton(body, text=self.label("I have read and agree to the terms above"),
                                  variable=self.app.agreement_checked, command=self.refresh_agreement)
        consent.pack(side="bottom", anchor="w", pady=(10, 0))
        text_area = ttk.Frame(body)
        text_area.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(text_area, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        text = self.app._text(text_area, height=10, yscrollcommand=scrollbar.set)
        text.pack(fill="both", expand=True)
        text.insert("1.0", agreement_text(self.app.ui_language))
        text.configure(state="disabled")
        scrollbar.configure(command=text.yview)
        self.next_button.configure(text=self.label("Agree and continue"))
        self.refresh_agreement()
        return self.save_agreement

    def refresh_agreement(self):
        self.next_button.configure(state="normal" if self.app.agreement_checked.get() else "disabled")

    def save_agreement(self):
        if self.app.accept_agreement(continue_setup=False):
            return True
        self.error.set(self.app.agreement_status.get())
        return False

    def theme_page(self, body):
        self.app._hint(body, ui_source("You can change the theme later in Settings.")).pack(
            anchor="w", pady=(0, 14))
        self.theme = ThemeFields(self.app, body)
        return self.save_theme

    def save_theme(self):
        self.preferences.update(validate_theme(self.theme.values()), interface_theme_setup_complete=True)
        return True

    def ocr_page(self, body):
        self.cuda = CudaControls(self.app, body)
        return self.save_ocr

    def save_ocr(self):
        tuning = validate_tuning({**self.app.config, **self.cuda.values()})
        self.preferences.update({name: tuning[name] for name in CUDA_FIELDS})
        return True

    def tools_page(self, body):
        ttk.Label(body, text=self.app.tr(EXPORT_TITLE), style="Heading.TLabel").pack(anchor="w")
        self.app._hint(body, EXPORT_WARNING).pack(anchor="w", pady=(6, 18))
        enabled = self.app.config.get("localization_enabled") is True
        self.tools_enabled = tk.BooleanVar(master=self.window, value=enabled)
        for value, label in ((False, "Keep developer tools off (recommended)"),
                             (True, "Enable developer tools")):
            ttk.Radiobutton(body, text=self.label(label), variable=self.tools_enabled,
                            value=value, command=self.refresh_tools).pack(anchor="w", pady=6)
        self.folder_group = ttk.Frame(body)
        self.folder = tk.StringVar(master=self.window, value=self.app.config.get("localization_folder", ""))
        ttk.Label(self.folder_group, text=self.label("Save folder (default: app folder)")).pack(anchor="w")
        row = ttk.Frame(self.folder_group)
        row.pack(fill="x", pady=(6, 4))
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.label("Choose folder"), command=self.pick_folder).pack(side="right", padx=(8, 0))
        self.app._hint(body, ui_source("You can enable or disable these tools later in Settings.")).pack(
            side="bottom", anchor="w", pady=(10, 0))
        self.refresh_tools()
        return self.save_tools

    def refresh_tools(self):
        if self.tools_enabled.get():
            self.folder_group.pack(fill="x", pady=(12, 0))
        else:
            self.folder_group.pack_forget()

    def pick_folder(self):
        folder = choose_directory(self.app, self.folder.get(), parent=self.window)
        if folder:
            self.folder.set(folder)

    def save_tools(self):
        enabled = self.tools_enabled.get()
        values = export_preferences({**self.app.config, "localization_enabled": enabled,
                                     "localization_folder": self.folder.get().strip() if enabled else ""})
        self.preferences.update(values, localization_setup_complete=True)
        return True

    def close(self):
        if self.window.winfo_exists():
            if self.window.grab_current() is self.window:
                self.window.grab_release()
            self.window.destroy()
        if self.app.setup_dialog is self:
            self.app.setup_dialog = None

