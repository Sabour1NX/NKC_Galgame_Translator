# SPDX-License-Identifier: MIT
"""Isolated hidden Tk language flows; no real credentials, HTTP or browser."""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from unittest.mock import Mock

import pytest

import nkc_galgame_translator.app as module
import nkc_galgame_translator.i18n as i18n
from nkc_galgame_translator.agreement import AGREEMENT_TEXT
from nkc_galgame_translator.agreement_en import AGREEMENT_TEXT_EN
from nkc_galgame_translator.agreement_ja import AGREEMENT_TEXT_JA
from nkc_galgame_translator.config_store import ConfigStore

_setup = runpy.run_path(str(Path(__file__).with_name('test_app_setup.py')))
hidden_app = _setup['hidden_app']


def use_interactive_language_detection(patch, os_language):
    """Exercise first-launch detection while the fixture suppresses auto-dialogs."""
    patch.setattr(i18n, 'detect_system_language', lambda: os_language)
    patch.setattr(module, 'initial_language',
                  lambda config, **options: i18n.initial_language(config, interactive=True))


def case_first_language_choice_preselects_os_without_granting_consent(root, patch):
    use_interactive_language_detection(patch, 'ja')
    patch.setattr(module,'video_memory_mb',lambda *args:8192)
    settings = {'app_language': 'zh-CN', 'app_language_selected': False,
                'aggressive_mode': False, 'source_lang': 'en', 'target_lang': 'zh-Hans'}
    with hidden_app(root, patch, accepted=False, settings=settings) as app:
        before = ConfigStore(root).load()
        api_dialog = Mock(side_effect=AssertionError('Language choice must not open API setup before consent'))
        engine = Mock(side_effect=AssertionError('Language choice must not obtain a translation engine'))
        patch.setattr(app, 'show_api_settings', api_dialog)
        patch.setattr(app, 'get_engine', engine)
        app.show_setup = True
        dialog = app.show_initial_setup()
        assert dialog.language.get() == 'ja'
        assert not dialog.window.winfo_viewable()
        assert not app.agreement_accepted and not app.agreement_checked.get()
        dialog.language.set('en')
        assert dialog.advance()
        app.root.update_idletasks()
        assert app.setup_dialog is dialog and app.ui_language == 'en'
        saved = ConfigStore(root).load()
        assert saved['app_language'] == 'en' and saved['app_language_selected'] is True
        assert saved['sampling_mode'] == 'supersample'
        for name in ('source_lang', 'target_lang', 'aggressive_mode'):
            assert saved[name] == before[name]
        assert not app.agreement_accepted and not app.agreement_checked.get()
        assert not saved.get('agreement_accepted_at')
        assert app.tabs.select() == str(app.agreement_tab)
        assert str(app.start_button['state']) == 'disabled'
        assert str(app.manual_button['state']) == 'disabled'
        assert 'User terms' in app.agreement_text.get('1.0', '2.0')
        assert not app.config_store.credentials_path.exists()
        api_dialog.assert_not_called()
        engine.assert_not_called()


def case_settings_switches_chrome_and_agreement_preserving_user_data_and_engine(root, patch):
    with hidden_app(root, patch, settings={'app_language': 'zh-CN', 'app_language_selected': True,
                                         'source_lang': 'en', 'target_lang': 'zh-Hans'}) as app:
        original = 'Start / \u5f00\u59cb\u7ffb\u8bd1 / \u8a2d\u5b9a\nGame text must stay exactly as typed.'
        translated = 'Settings / \u8bbe\u7f6e / \u7ffb\u8a33\u958b\u59cb\n\u8fd9\u6bb5\u8bd1\u6587\u4e5f\u4e0d\u5c5e\u4e8e\u8f6f\u4ef6\u754c\u9762\u3002'
        app.manual_input.insert('1.0', original)
        app._set_manual_output(translated)
        app.game.set('Settings / \u8bbe\u7f6e / \u8a2d\u5b9a')
        engine = app.get_engine()
        engine.set_term(app.game.get(), 'en', 'zh-Hans', 'Start / \u8bbe\u7f6e', '\u5f00\u59cb / Settings')
        # Seed an already consumed session quota without performing any HTTP.
        with engine._lock:
            engine._stats['session_requests'] = 7
            engine._stats['prompt_tokens'] = 123
        app.refresh_terms()
        before_stats = engine.get_stats()
        before_terms = engine.list_terms(app.game.get(), 'en', 'zh-Hans')
        before_rows = [app.term_tree.item(item, 'values') for item in app.term_tree.get_children()]
        agreement_time = app.config['agreement_accepted_at']
        cases = [
            ('English', 'en', ('Game translation', 'Glossary', 'Translate text manually', 'Agreement · accepted', 'Settings'),
             'Start translation', AGREEMENT_TEXT_EN),
            ('\u65e5\u672c\u8a9e (beta)', 'ja', ('\u30b2\u30fc\u30e0\u7ffb\u8a33', '\u7528\u8a9e\u96c6', '\u30c6\u30ad\u30b9\u30c8\u7ffb\u8a33', '\u5229\u7528\u898f\u7d04 · \u540c\u610f\u6e08\u307f', '\u8a2d\u5b9a'),
             '\u7ffb\u8a33\u958b\u59cb', AGREEMENT_TEXT_JA),
            ('\u7b80\u4f53\u4e2d\u6587', 'zh-CN', ('\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1', '\u7ffb\u8bd1\u8bcd\u5178', '\u6587\u672c\u7ffb\u8bd1', '\u4f7f\u7528\u534f\u8bae · \u5df2\u6388\u6743', '\u8bbe\u7f6e'),
             '\u5f00\u59cb\u7ffb\u8bd1', AGREEMENT_TEXT),
        ]
        for selection, code, tabs, start_label, agreement in cases:
            app.settings_panel.app_language_var.set(selection)
            assert app.save_settings()
            assert app.ui_language == code
            assert tuple(app.tabs.tab(tab, 'text') for tab in app.tabs.tabs()) == tabs
            assert app.start_button['text'] == start_label, ascii((code, app.start_button['text'], start_label))
            assert app.agreement_text.get('1.0', 'end-1c') == agreement
            assert str(app.agreement_text['state']) == 'disabled'
            saved = ConfigStore(root).load()
            assert saved['app_language'] == code and saved['app_language_selected'] is True
            assert saved['agreement_accepted_at'] == agreement_time
            assert app.engine is engine and engine.get_stats() == before_stats
            assert app.manual_input.get('1.0', 'end-1c') == original
            assert app.manual_output.get('1.0', 'end-1c') == translated
            assert app.game.get() == 'Settings / \u8bbe\u7f6e / \u8a2d\u5b9a'
            assert engine.list_terms(app.game.get(), 'en', 'zh-Hans') == before_terms
            assert [app.term_tree.item(item, 'values') for item in app.term_tree.get_children()] == before_rows


def case_reopened_explicit_language_wins_over_changed_windows_language(root, patch):
    first_root = root / 'first'
    first_root.mkdir()
    with patch.context() as first_patch:
        use_interactive_language_detection(first_patch, 'ja')
        with hidden_app(first_root, first_patch, settings={'app_language': 'zh-CN',
                'app_language_selected': False, 'source_lang': 'en', 'target_lang': 'zh-Hans'}) as app:
            assert app.ui_language == 'ja'
            app.settings_panel.app_language_var.set('English')
            assert app.save_settings()
            saved = ConfigStore(first_root).load()
    # Rehydrate precisely the persisted settings in a fresh Tcl instance.
    reopened_root = root / 'reopened'
    reopened_root.mkdir()
    with patch.context() as reopened_patch:
        use_interactive_language_detection(reopened_patch, 'zh-CN')
        with hidden_app(reopened_root, reopened_patch, settings=saved) as reopened:
            assert reopened.ui_language == 'en'
            assert reopened.source.get() == 'English'
            assert reopened.target.get() == 'Simplified Chinese'
            assert reopened.settings_panel.app_language_var.get() == 'English'
            assert reopened.tabs.tab(reopened.settings_tab, 'text') == 'Settings'
            assert reopened.setup_dialog is None
            assert reopened.config['source_lang'] == 'en'
            assert reopened.config['target_lang'] == 'zh-Hans'


def case_localized_translation_language_choices_save_stable_codes(root, patch):
    with hidden_app(root, patch, settings={'app_language': 'en', 'app_language_selected': True}) as app:
        controls = [control for control, state in app.scope_controls
                    if state == 'readonly' and control is not app.profile_box]
        assert len(controls) == 2
        for code, choice, source, target in (
            ('en', 'English', 'English', 'Simplified Chinese'),
            ('ja', '\u65e5\u672c\u8a9e (beta)', '\u82f1\u8a9e', '\u7c21\u4f53\u5b57\u4e2d\u56fd\u8a9e'),
            ('zh-CN', '\u7b80\u4f53\u4e2d\u6587', '\u82f1\u8bed', '\u7b80\u4f53\u4e2d\u6587'),
        ):
            app.settings_panel.app_language_var.set(choice)
            assert app.save_settings()
            assert all(source in control['values'] and target in control['values'] for control in controls)
            app.source.set(source)
            app.target.set(target)
            app.translation_language_changed()
            saved = ConfigStore(root).load()
            assert saved['app_language'] == code
            assert saved['source_lang'] == 'en' and saved['target_lang'] == 'zh-Hans'
            assert app.term_scope()[1:] == ('en', 'zh-Hans')


def case_manual_opens_matching_bundled_html_and_reports_missing_file(root, patch):
    with hidden_app(root, patch, settings={'app_language': 'zh-CN', 'app_language_selected': True}) as app:
        docs = root / 'docs'
        docs.mkdir()
        chinese = docs / 'PROJECT_MANUAL.html'
        english = docs / 'PROJECT_MANUAL.en.html'
        japanese = docs / 'PROJECT_MANUAL.ja.html'
        for path in (chinese, english, japanese):
            path.write_text('<!doctype html><title>Synthetic local manual</title>', encoding='utf-8')
        opener = Mock()
        patch.setattr(module.os, 'startfile', opener)
        for code, path in (('zh-CN', chinese), ('en', english), ('ja', japanese)):
            app.apply_ui_language(code)
            assert app.open_manual()
            opener.assert_called_with(str(path))
        assert opener.call_count == 3
        english.unlink()
        app.apply_ui_language('en')
        assert not app.open_manual()
        assert opener.call_count == 3
        assert app.status.get() == 'The bundled manual is missing. Check the complete release folder.'
        app.apply_ui_language('zh-CN')
        opener.side_effect = OSError('Synthetic private filesystem detail must not be displayed')
        assert not app.open_manual()
        assert app.status.get() == '\u672a\u627e\u5230\u968f\u5305\u624b\u518c\uff0c\u8bf7\u68c0\u67e5\u5b8c\u6574\u53d1\u884c\u76ee\u5f55\u3002'


def case_cuda_slider_onboarding_and_settings_persist_without_gpu_or_network(root,patch):
    with hidden_app(root,patch,accepted=False,settings={'app_language_selected':False}) as app:
        app.show_setup=True
        patch.setattr(app, '_configure_hotkey', Mock())
        patch.setattr(app, 'show_api_settings', Mock())
        dialog=app.show_initial_setup()
        assert dialog.advance()
        assert not ConfigStore(root).load().get('agreement_accepted_at')
        app.agreement_checked.set(True)
        assert dialog.advance()
        assert dialog.advance()
        dialog.cuda.vars['cuda_enabled'].set(False)
        dialog.cuda.vars['cuda_quality'].set(42.4)
        dialog.cuda.vars['cuda_memory_mb'].set('1536')
        assert dialog.advance()
        assert dialog.advance()
        saved=ConfigStore(root).load()
        assert (saved['cuda_enabled'],saved['cuda_quality'],saved['cuda_memory_mb'])==(False,42,1536)
        assert saved.get('agreement_accepted_at') and not app.has_api_key
        app.show_setup=False
        ui=app.settings_panel.cuda_controls
        assert ui.values()=={'cuda_enabled':False,'cuda_quality':42,'cuda_memory_mb':'1536'}
        ui.vars['cuda_enabled'].set(True);ui.refresh()
        assert str(ui.scale['state'])=='normal'
        ui.vars['cuda_quality'].set(87.6)
        assert app.save_settings()
        assert ConfigStore(root).load()['cuda_quality']==88
        app.manual_busy=True;app._refresh_mode_control()
        assert str(ui.scale['state'])=='disabled' and str(ui.toggle['state'])=='disabled'
        app.manual_busy=False;app._refresh_mode_control()
        assert str(ui.scale['state'])=='normal'
        app.apply_ui_language('en')
        assert 'Quality coefficient 88 / 100' in ui.value.get()


def case_cuda_prewarm_is_background_and_handed_to_ocr_without_second_load(root,patch):
    import threading,time
    from types import SimpleNamespace
    import nkc_galgame_translator.cuda_ocr as gpu_module
    import nkc_galgame_translator.ocr as ocr_module
    gate=threading.Event();entered=threading.Event();instances=[]
    class Fake:
        def __init__(self,*args,**kwargs):self.closed=False;self.last_status={};instances.append(self)
        def available(self):return True
        def warmup(self):
            entered.set();assert gate.wait(3)
            self.last_status={'state':'cuda'}
        def close(self):self.closed=True
        def cancel(self):gate.set()
    patch.setattr(gpu_module,'CudaOcr',Fake)
    with hidden_app(root,patch,key='synthetic-test-token',settings={'cuda_enabled':True}) as app:
        app._prepare_cuda()
        assert entered.wait(1) and app._gpu_warm_busy
        assert app._mode_busy() and str(app.start_button['state'])=='disabled'
        # The Tk thread still pumps events while only the worker waits.
        tick=[];app.root.after(0,lambda:tick.append(True));app.root.update()
        assert tick and len(instances)==1
        app._prepare_cuda();assert len(instances)==1
        gate.set()
        deadline=time.monotonic()+3
        while app._gpu_warm_busy and time.monotonic()<deadline:
            app.drain();time.sleep(.002)
        assert not app._gpu_warm_busy
        spy=Mock(return_value=SimpleNamespace(close=lambda:None))
        patch.setattr(ocr_module,'OcrCore',spy)
        app._new_ocr_core()
        assert spy.call_args.kwargs['cuda_instance'] is instances[0]
        assert app._gpu_warm_core is None and not instances[0].closed
        instances[0].close()


def case_cuda_warm_failure_is_latched_for_cpu_fallback(root,patch):
    import time
    import nkc_galgame_translator.cuda_ocr as gpu_module
    class Fake:
        last_status={}
        def __init__(self,*a,**kw):pass
        def available(self):return True
        def warmup(self):raise RuntimeError('synthetic failure')
        def close(self):pass
        def cancel(self):pass
    patch.setattr(gpu_module,'CudaOcr',Fake)
    with hidden_app(root,patch,key='synthetic-test-token') as app:
        app._prepare_cuda()
        deadline=time.monotonic()+3
        while app._gpu_warm_busy and time.monotonic()<deadline:
            app.drain();time.sleep(.002)
        assert app._gpu_warm_core.last_status['state']=='unavailable'
        assert not app._mode_busy()
        assert '\u5df2\u56de\u9000' in app.status.get()


CASES = [name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case', CASES)
def test_hidden_interface_language_flow(case):
    process = subprocess.run([
        sys.executable, '-c',
        'import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',
        str(Path(__file__).resolve()), case,
    ], cwd=module.ROOT, capture_output=True, text=True, timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0, process.stdout + process.stderr


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='interface-ui-') as folder, pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[-1]](Path(folder), patch)
