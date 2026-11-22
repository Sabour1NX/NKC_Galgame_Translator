# SPDX-License-Identifier: MIT
"""Capture actual localized idle UI, only from this process's own HWNDs.

Each language runs in a fresh process with an isolated temporary configuration,
no API keys, blocked HTTP constructors, no game enumeration, no activation or
input calls. PrintWindow renders the actual application's windows. The parent
aggregates PNGs and layout measurements in reports/ui-language-*.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import ui_snapshot as capture
from nkc_galgame_translator import __version__
from nkc_galgame_translator import app as app_module
from nkc_galgame_translator import i18n
from nkc_galgame_translator.tuning import TUNING_DEFAULTS
from nkc_galgame_translator.agreement import AGREEMENT_VERSION

REPORTS = ROOT / 'reports' / 'ui30'
NO_ACTIVATE = 0x08000000


def own_handle(window):
    hwnd = capture.user32.GetAncestor(window.winfo_id(), 2)
    owner = W.DWORD()
    capture.user32.GetWindowThreadProcessId(hwnd, C.byref(owner))
    if owner.value != os.getpid():
        raise RuntimeError('Refusing to capture a window from another process')
    return hwnd


def no_activation(window):
    hwnd = own_handle(window)
    style = capture.user32.GetWindowLongPtrW(hwnd, -20)
    capture.user32.SetWindowLongPtrW(hwnd, -20, style | NO_ACTIVATE)
    return hwnd


def widget_bounds(widget, window):
    return [widget.winfo_rootx() - window.winfo_rootx(),
            widget.winfo_rooty() - window.winfo_rooty(),
            widget.winfo_width(), widget.winfo_height()]


def intersects_visible_client(widget, window):
    left, top, width, height = widget_bounds(widget, window)
    right, bottom = left + width, top + height
    parent = widget.master
    while parent is not None:
        x, y, w, h = widget_bounds(parent, window)
        left, top, right, bottom = max(left, x), max(top, y), min(right, x + w), min(bottom, y + h)
        if parent is window:
            break
        parent = parent.master
    return right > left and bottom > top


def layout_measurements(window, important):
    measurements = {}
    for name, widget in important.items():
        x, y, width, height = widget_bounds(widget, window)
        measurements[name] = {
            'bounds': [x, y, width, height],
            'requested': [widget.winfo_reqwidth(), widget.winfo_reqheight()],
            'inside_client': (x >= 0 and y >= 0 and x + width <= window.winfo_width()
                              and y + height <= window.winfo_height()),
            'full_height': height >= widget.winfo_reqheight(),
        }
    clipped = []
    pending = [window]
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        if (not widget.winfo_viewable() or not intersects_visible_client(widget,window)
                or not isinstance(widget, (ttk.Button, ttk.Checkbutton,
                ttk.Radiobutton, ttk.Label))):
            continue
        # Wrapped labels use their requested width after Tk's geometry pass.
        if widget.winfo_width() + 2 < widget.winfo_reqwidth():
            clipped.append({'class': widget.winfo_class(), 'text': str(widget.cget('text')),
                            'bounds': widget_bounds(widget, window),
                            'requested_width': widget.winfo_reqwidth()})
    return {'important_controls': measurements, 'possibly_clipped_labels': clipped}


def worker(language):
    REPORTS.mkdir(exist_ok=True)
    foreground_before = capture.user32.GetForegroundWindow()
    focus_observations = []
    records = []
    blocked_http = []
    picker = language == 'picker'
    code = 'ja' if picker else language

    def forbid_http(*args, **kwargs):
        blocked_http.append('HTTP client construction attempted')
        raise AssertionError('Localized idle UI capture must never construct HTTP clients')

    def observe_focus(stage):
        current = capture.user32.GetForegroundWindow()
        if current != foreground_before:
            owner = W.DWORD()
            capture.user32.GetWindowThreadProcessId(current, C.byref(owner))
            if owner.value == os.getpid():
                focus_observations.append(stage)

    original_tk, original_top = tk.Tk, tk.Toplevel

    def hidden_root(*args, **kwargs):
        window = original_tk(*args, **kwargs)
        window.withdraw()
        no_activation(window)
        return window

    def hidden_top(*args, **kwargs):
        window = original_top(*args, **kwargs)
        window.withdraw()
        no_activation(window)
        return window

    with tempfile.TemporaryDirectory(prefix='nishokuchou-language-ui-') as folder:
        fixture = Path(folder)
        shutil.copytree(ROOT / 'assets', fixture / 'assets')
        (fixture / 'config').mkdir()
        config = {'api_key': '', 'offline_only': True, 'app_language': code,
                  'app_language_selected': not picker, 'source_lang': 'en', 'target_lang': 'zh-Hans',
                  'source_label_mixed_only': True, 'game': '', 'api_setup_complete': True,
                  'base_url': 'https://api.example.test/v1', 'model': 'example-model'}
        if not picker:
            config.update(agreement_version=AGREEMENT_VERSION,
                          agreement_accepted_at='2026-11-15T00:00:00+00:00')
        (fixture / 'config' / 'example.json').write_text(json.dumps(config), encoding='utf-8')
        with patch.object(tk, 'Tk', hidden_root), patch.object(tk, 'Toplevel', hidden_top), \
                patch.object(tk.Misc, 'grab_set', lambda self: None), \
                patch.object(app_module, 'ROOT', fixture), \
                patch.object(app_module, 'window_list', lambda: []), \
                patch.object(httpx, 'Client', forbid_http), \
                patch.object(httpx, 'AsyncClient', forbid_http):
            app = app_module.App(show_setup=False)
            # A minimal first-run fixture may omit managed options in config;
            # the controls expose the effective defaults shown to the user.
            current_defaults={
                'overlay_font_min':int(app.settings_panel.vars['overlay_font_min'].get()),
                'overlay_font_max':int(app.settings_panel.vars['overlay_font_max'].get()),
                'context_max_chars':int(app.settings_panel.vars['context_max_chars'].get()),
                'vision_ocr_mode':app.settings_panel.values()['vision_ocr_mode'],
                'context_web_search':app.settings_panel.vars['context_web_search'].get(),
            }
            assert current_defaults=={'overlay_font_min':8,'overlay_font_max':72,
                                      'context_max_chars':int(app.config.get('context_max_chars', TUNING_DEFAULTS['context_max_chars'])),
                                      'vision_ocr_mode':app.config['vision_ocr_mode'],
                                      'context_web_search':False}
            assert app.settings_panel.vars['unlimited_requests'].get() is False
            unlimited_capture=False
            try:
                def show(window):
                    window.update_idletasks()
                    hwnd = no_activation(window)
                    capture.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                    # Tk's first Map/Configure and Windows' nonclient paint can
                    # arrive on separate turns, especially for a new Toplevel.
                    for _ in range(3):
                        time.sleep(.025)
                        app.root.update()
                    capture.user32.UpdateWindow(hwnd)
                    return hwnd

                def take(window, suffix, important):
                    hwnd = show(window)
                    observe_focus(suffix)
                    name = f'ui-language-{language}-{suffix}.png'
                    shot = capture.print_own_window(hwnd)
                    shot.save(REPORTS / name)
                    records.append({'image': name, 'client_size': [window.winfo_width(), window.winfo_height()],
                                    'image_size': list(shot.size), **layout_measurements(window, important)})

                def settings_control(name,widget_type,option):
                    variable=str(app.settings_panel.vars[name])
                    return next(widget for widget in app.settings_panel.controls
                                if isinstance(widget,widget_type) and str(widget.cget(option))==variable)

                def scroll_settings_to(widget):
                    app.root.update_idletasks()
                    canvas=app.settings_canvas
                    top=widget.winfo_rooty()-canvas.winfo_rooty()+canvas.canvasy(0)
                    bounds=canvas.bbox('all')
                    height=max(1,bounds[3]-bounds[1])
                    canvas.yview_moveto(max(0,(top-bounds[1]-80)/height))
                    app.root.update()

                app.windows_box.configure(values=())
                app.root.geometry('980x820+40+30')
                show(app.root)
                if picker:
                    # Actual first-step dialog, with an unselected/unsigned config.
                    dialog = app.show_language_setup()
                    assert dialog.selected.get() == 'ja'
                    actions={f'action_{index}':widget for index,widget in enumerate(dialog.window.winfo_children()[0].winfo_children())
                             if isinstance(widget,ttk.Button)}
                    take(dialog.window, '620x350', actions)
                    min_width,min_height=dialog.window.minsize()
                    dialog.window.geometry(f'{min_width}x{min_height}+80+60')
                    take(dialog.window, f'minimum-{min_width}x{min_height}', actions)
                    assert not app.agreement_accepted and not app.config.get('app_language_selected')
                    dialog.close()
                else:
                    for index, name in enumerate(('screen', 'dictionary', 'text', 'agreement', 'settings')):
                        app.tabs.select(index)
                        take(app.root, name, {})
                    if language == 'zh-CN':
                        for index, fraction in enumerate((.18, .36, .54, .72, .90, 1.0), 1):
                            app.settings_canvas.yview_moveto(fraction)
                            take(app.root, f'settings-scroll-{index}', {})
                        app.tabs.select(0)
                        profiles = app.open_profiles()
                        if profiles is None:
                            profiles = app.profile_dialog
                        take(profiles, 'game-profiles', {})
                        profiles.destroy()
                        app.tabs.select(1)
                        dialog = app.open_dictionary_import()
                        take(dialog.window, 'dictionary-import', {})
                        dialog.close()
                        with patch.object(app.get_engine(), 'get_context_status',
                                          return_value={'updated_at': None, 'directory': 'data/contexts/example'}):
                            history = app.open_translation_history()
                        if history is not None:
                            take(history, 'translation-history', {})
                            history.destroy()
                    for width, height in ((980, 820),):
                        app.root.geometry(f'{width}x{height}+40+30')
                        app.tabs.select(app.settings_tab)
                        app.settings_canvas.yview_moveto(0)
                        app.root.update()
                        take(app.root, f'settings-{width}x{height}', {
                            'font_family': app.settings_panel.font_box,
                            'mixed_language_switch': app.settings_panel.mixed_only_check,
                            'interface_language': app.settings_panel.language_box,
                            'header_api': app.api_settings_button,
                        })
                        if width == 850:
                            panel=app.settings_panel
                            panel.vars['unlimited_requests'].set(True)
                            panel.refresh(False)
                            assert str(panel.request_limit_control['state'])=='disabled'
                            scroll_settings_to(panel.unlimited_requests_check)
                            take(app.root,'settings-unlimited-850x720',{
                                'unlimited_requests':panel.unlimited_requests_check,
                                'disabled_finite_quota':panel.request_limit_control})
                            unlimited_capture=True
                            panel.vars['unlimited_requests'].set(False)
                            panel.refresh(False)
                            assert str(panel.request_limit_control['state'])=='normal'
                            font_min=settings_control('overlay_font_min',ttk.Spinbox,'textvariable')
                            font_max=settings_control('overlay_font_max',ttk.Spinbox,'textvariable')
                            scroll_settings_to(font_min)
                            take(app.root,'settings-font-range-850x720',{
                                'automatic_font_minimum':font_min,'automatic_font_maximum':font_max})
                            vision=app.settings_panel.vision_mode_box
                            web=settings_control('context_web_search',ttk.Checkbutton,'variable')
                            scroll_settings_to(vision)
                            take(app.root,'settings-vision-850x720',{'vision_ocr':vision})
                            scroll_settings_to(web)
                            take(app.root,'settings-context-850x720',{'context_web_search':web})
                            app.settings_canvas.yview_moveto(1)
                            app.root.update()
                            take(app.root, 'settings-bottom-850x720', {'save': app.settings_panel.save_button})
                        app.tabs.select(app.agreement_tab)
                        app.agreement_text.yview_moveto(0)
                        app.root.update()
                        take(app.root, f'agreement-{width}x{height}', {
                            'agreement': app.agreement_text, 'consent': app.agreement_checkbox,
                            'continue': app.accept_agreement_button,
                        })
                    app.root.geometry('980x820+40+30')
                    dialog = app.show_api_settings()
                    assert dialog is not None and not dialog.key.get()
                    assert not any(slot['has_api_key'] for slot in app.config['api_slots'])
                    for width, height in ((700, 720),):
                        dialog.window.geometry(f'{width}x{height}+80+60')
                        take(dialog.window, f'api-{width}x{height}', {
                            'slot_1': dialog.slot_buttons[0], 'slot_3': dialog.slot_buttons[2],
                            'key_entry': dialog.key_entry, 'save': dialog.save_button,
                            'offline': dialog.offline_button, 'close': dialog.close_button,
                        })
                    if language == 'zh-CN':
                        for slot in (1, 2):
                            dialog.select_slot(slot)
                            take(dialog.window, f'api-slot-{slot+1}', {})
                    dialog.close()
                assert not blocked_http
                assert not app.config_store.credentials_path.exists()
                app.root.withdraw()
            finally:
                app.close()

    unchanged = not focus_observations
    report = {'version': __version__, 'language': language, 'capture': 'PrintWindow; verified own process HWND',
              'isolated_temporary_configuration': True, 'api_key_present': False,
              'network_requests': 0, 'http_constructor_attempts': len(blocked_http),
              'current_defaults': current_defaults,
              'unlimited_default':False,'unlimited_checked_disabled_quota':unlimited_capture,
              'game_enumeration': False, 'game_launched': False, 'input_calls': 0,
              'activation_calls': 0, 'modal_input_grabs': False, 'foreground_unchanged_after_cleanup': unchanged,
              'focus_observations': focus_observations, 'snapshots': records}
    (REPORTS / f'ui-language-{language}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'language': language, 'images': len(records), 'report': f'ui-language-{language}.json'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('zh-CN', 'en', 'ja', 'picker'))
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    REPORTS.mkdir(exist_ok=True)
    reports = []
    for language in ('zh-CN', 'en', 'ja', 'picker'):
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', language],
                                   cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                   timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode:
            raise RuntimeError(f'{language} capture failed:\n{completed.stdout}\n{completed.stderr}')
        reports.append(json.loads((REPORTS / f'ui-language-{language}.json').read_text(encoding='utf-8')))
    summary = {'version': __version__, 'languages': ['zh-CN', 'en', 'ja'],
               'images': [shot['image'] for report in reports for shot in report['snapshots']],
               'reports': [f'ui-language-{report["language"]}.json' for report in reports],
               'network_requests': 0, 'input_calls': 0, 'activation_calls': 0,
               'foreground_unchanged': all(report['foreground_unchanged_after_cleanup'] for report in reports),
               'layout_warnings': [{'language': report['language'], 'image': shot['image'],
                                    'labels': shot['possibly_clipped_labels']}
                                   for report in reports for shot in report['snapshots']
                                   if shot['possibly_clipped_labels']]}
    (REPORTS / 'ui-language-snapshots.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'images': len(summary['images']), 'layout_warnings': len(summary['layout_warnings']),
                      'report': str(REPORTS / 'ui-language-snapshots.json')}))


if __name__ == '__main__':
    main()
