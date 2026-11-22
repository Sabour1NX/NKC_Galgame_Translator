# SPDX-License-Identifier: MIT
"""Isolated hidden Tk checks: never use actual API keys, files, or network."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import Mock

import pytest

import nkc_galgame_translator.app as module
import nkc_galgame_translator.dictionary_import as parser
import nkc_galgame_translator.settings_ui as settings_module
from nkc_galgame_translator.config_store import ConfigStore

_setup = runpy.run_path(str(Path(__file__).with_name('test_app_setup.py')))
hidden_app = _setup['hidden_app']
SYNTHETIC_KEY = _setup['SYNTHETIC_KEY']
BASE_URL, MODEL = _setup['BASE_URL'], _setup['MODEL']


def pump(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.root.update()
        if time.monotonic() > deadline:
            raise AssertionError('Timed out waiting for a background UI operation')
        time.sleep(.01)


def case_settings_preserve_three_slots_and_rebuild_resources(root, patch):
    with hidden_app(root, patch, key=SYNTHETIC_KEY) as app:
        for index in (1, 2):
            app.save_api_settings(BASE_URL, MODEL, api_key=SYNTHETIC_KEY+str(index), slot=index)
        labels = [app.tabs.tab(tab, 'text') for tab in app.tabs.tabs()]
        assert len(labels) == 5 and labels[-1] == '\u8bbe\u7f6e'
        engine, core = Mock(), Mock()
        engine.get_stats.return_value = {}
        app.engine, app.core = engine, core
        assert app.save_settings({'translation_workers': '16', 'ocr_min_confidence': '63', 'max_requests': '9'})
        assert app.engine is None and app.core is None
        engine.close.assert_called_once()
        core.close.assert_called_once()
        loaded = ConfigStore(root).load()
        assert loaded['translation_workers'] == loaded['max_concurrency'] == 16
        assert loaded['max_requests'] == 9
        assert all(slot['has_api_key'] for slot in loaded['api_slots'])
        for index in range(3):
            saved = app.config_store.save_api_slot(index, BASE_URL, MODEL, activate=True, offline_only=False)
            assert saved['api_key'] == SYNTHETIC_KEY+(str(index) if index else '')
        app.settings_panel.vars['translation_hold_ms'].set('2300')
        app.settings_panel.vars['scene_change_sensitivity'].set('85')
        assert app.save_settings()
        saved = ConfigStore(root).load()
        assert saved['translation_hold_ms'] == 2300 and saved['scene_change_sensitivity'] == 85
        assert app.save_settings({'settle_ms': 123})
        assert app.config['max_requests'] == 9  # Partial updates do not reset other values.


def case_save_failure_and_invalid_values_do_not_mutate_runtime(root, patch):
    with hidden_app(root, patch) as app:
        before = dict(app.config)
        raw = app.config_store.config_path.read_bytes()
        engine, core = Mock(), Mock()
        engine.get_stats.return_value = {}
        app.engine, app.core = engine, core
        assert not app.save_settings({'translation_workers': 'NaN'})
        assert '\u6574\u6570' in app.settings_panel.message.get()
        patch.setattr(app.config_store, 'save', Mock(side_effect=PermissionError(SYNTHETIC_KEY)))
        assert not app.save_settings({'translation_workers': 8})
        assert SYNTHETIC_KEY not in app.settings_panel.message.get()
        assert app.config == before
        assert app.config_store.config_path.read_bytes() == raw
        assert app.engine is engine and app.core is core
        engine.close.assert_not_called()
        core.close.assert_not_called()


def case_busy_disables_controls_and_rejects_mutations(root, patch):
    with hidden_app(root, patch) as app:
        before = app.config_store.config_path.read_bytes()
        app.manual_busy = True
        app._refresh_mode_control()
        assert all(str(c['state']) == 'disabled' for c in app.settings_panel.controls)
        assert not app.save_settings({'translation_workers': 8})
        assert app.open_dictionary_import() is None
        assert app.config_store.config_path.read_bytes() == before
        app.manual_busy = False
        app._refresh_mode_control()
        readonly=(app.settings_panel.language_box,app.settings_panel.ocr_mode_box,app.settings_panel.sampling_mode_box)
        assert all(str(c['state']) == ('readonly' if c in readonly else 'disabled' if c is app.settings_panel.font_size_controls['overlay_font_size'] else 'normal')
                   for c in app.settings_panel.controls)


def case_legacy_switches_are_not_editable_or_local_routes(root, patch):
    with hidden_app(root, patch) as app:
        assert 'aggressive_mode' not in app.settings_panel.vars
        assert 'expert_enabled' not in app.settings_panel.vars
        assert app.save_settings({'context_max_chars': 960, 'ocr_refine_workers': 3})
        assert app.config['context_max_chars'] == 960
        assert app.config['ocr_refine_workers'] == 3
        assert app.get_engine().get_stats()['ai_only']


def case_stale_aggressive_without_key_launches_local(root, patch):
    with hidden_app(root, patch, settings={'aggressive_mode': True, 'offline_only': False}) as app:
        assert app.offline_only.get()
        assert not app.config['aggressive_mode']
        assert 'aggressive_mode' not in app.settings_panel.vars
        engine = app.get_engine()
        assert engine is not None


def case_import_preview_is_read_only_then_commits_selected_scope(root, patch):
    with hidden_app(root, patch) as app:
        source = root / 'sample.json'
        source.write_text(json.dumps({'Hello': '\u4f60\u597d', 'Exit': '\u9000\u51fa'}), encoding='utf-8')
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.game.set('SyntheticGame')
        engine = app.get_engine()
        dialog = app.open_dictionary_import()
        assert not dialog.window.winfo_viewable()
        assert not dialog.commit()
        dialog.path.set(str(source))
        assert dialog.preview()
        pump(app, lambda: not app.import_busy)
        assert len(dialog.entries) == 2
        assert '\u5c1a\u672a\u5199\u5165' in dialog.message.get()
        assert engine.list_shared_terms('en', 'zh-Hans') == []
        assert engine.list_terms('SyntheticGame', 'en', 'zh-Hans') == []
        assert dialog.commit()
        pump(app, lambda: not app.import_busy)
        rows = engine.list_shared_terms('en', 'zh-Hans')
        assert {row['source']:row['target'] for row in rows} == {'Hello':'\u4f60\u597d', 'Exit':'\u9000\u51fa'}
        assert engine.list_terms('SyntheticGame', 'en', 'zh-Hans') == []
        assert '\u65b0\u589e 2' in dialog.message.get()
        assert dialog.entries is None
        app.term_shared.set(True);app.refresh_terms()
        assert len(app.term_tree.get_children()) == 2


def case_import_policy_preview_invalidation_and_bad_file(root, patch):
    with hidden_app(root, patch) as app:
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.game.set('SyntheticGame')
        engine = app.get_engine()
        engine.set_term('SyntheticGame', 'en', 'zh-Hans', 'Hello', '\u539f\u8bd1\u6587')
        source = root / 'sample.csv'
        source.write_text('source,target\nHello,\u65b0\u8bd1\u6587\n', encoding='utf-8')
        dialog = app.open_dictionary_import()
        dialog.shared.set(False);dialog.path.set(str(source))
        assert dialog.preview();pump(app, lambda: not app.import_busy)
        assert dialog.commit();pump(app, lambda: not app.import_busy)
        assert engine.list_terms('SyntheticGame','en','zh-Hans')[0]['target'] == '\u539f\u8bd1\u6587'
        assert dialog.preview();pump(app, lambda: not app.import_busy)
        dialog.replace.set(True)
        assert dialog.commit();pump(app, lambda: not app.import_busy)
        assert engine.list_terms('SyntheticGame','en','zh-Hans')[0]['target'] == '\u65b0\u8bd1\u6587'
        assert dialog.preview();pump(app, lambda: not app.import_busy)
        dialog.path.set(str(root/'missing.json'))
        assert dialog.entries is None and not dialog.commit()
        assert dialog.preview();pump(app, lambda: not app.import_busy)
        assert dialog.entries is None
        assert '\u9884\u89c8\u6210\u529f' not in dialog.message.get()


def case_parse_worker_keeps_tk_responsive_and_prevents_switch_or_close(root, patch):
    with hidden_app(root, patch) as app:
        started, release = threading.Event(), threading.Event()
        worker_threads = []
        def slow_parse(*args):
            worker_threads.append(threading.get_ident());started.set()
            assert release.wait(4)
            return [{'source':'Hello','target':'\u4f60\u597d'}]
        patch.setattr(parser,'parse_dictionary',slow_parse)
        dialog=app.open_dictionary_import();dialog.path.set(str(root/'synthetic.csv'))
        assert dialog.preview()
        assert started.wait(1)
        try:
            tick=[];app.root.after(1,lambda:tick.append(True))
            pump(app,lambda:bool(tick))
            assert worker_threads[0] != threading.get_ident()
            assert not dialog.close()
            assert not app.save_settings({'translation_workers':8})
            with pytest.raises(ValueError):app.save_api_settings(BASE_URL,MODEL,offline_only=True)
            assert all(str(c['state'])=='disabled' for c in app.settings_panel.controls)
        finally:release.set()
        pump(app,lambda:not app.import_busy)
        assert dialog.close()


def case_shared_list_is_bounded_and_manual_rule_is_visible(root, patch):
    with hidden_app(root, patch) as app:
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.game.set('SyntheticGame')
        engine=app.get_engine()
        engine.import_terms([{'source':f'Word{i}', 'target':f'\u8bcd{i}'} for i in range(205)],
                            'SyntheticGame','en','zh-Hans',shared=True)
        app.term_shared.set(True);app.refresh_terms()
        assert len(app.term_tree.get_children()) == 200
        engine.set_term('SyntheticGame','en','zh-Hans','Welcome','\u6b22\u8fce')
        app.manual_input.insert('1.0','Welcome')
        app.manual_translate();pump(app,lambda:not app.manual_busy)
        assert app.manual_output.get('1.0','end').strip() != '\u6b22\u8fce'
        assert 'API' in app.status.get()


def case_close_waits_for_import_transaction_and_file_picker_is_explicit(root, patch):
    with hidden_app(root, patch) as app:
        picker=Mock(return_value=str(root/'synthetic.csv'))
        patch.setattr(settings_module.filedialog,'askopenfilename',picker)
        dialog=app.open_dictionary_import()
        picker.assert_not_called()
        dialog.browse()
        picker.assert_called_once()
        assert dialog.path.get().endswith('synthetic.csv')
        started,release=threading.Event(),threading.Event()
        engine=Mock();engine.get_stats.return_value={};engine.list_terms.return_value=[]
        app.engine=engine
        def slow_import(*args,**kwargs):
            started.set()
            assert release.wait(4)
            return {'inserted':1,'updated':0,'skipped':0}
        engine.import_terms.side_effect=slow_import
        dialog.receive(('preview',[{'source':'Hello','target':'\u4f60\u597d'}],(*app.term_scope(),True)))
        assert dialog.commit();assert started.wait(1)
        with patch.context() as close_patch:
            destroyed=Mock();close_patch.setattr(app.root,'destroy',destroyed)
            app.close()
            engine.close.assert_not_called();destroyed.assert_not_called()
            release.set()
            pump(app,lambda:destroyed.called)
            engine.close.assert_called_once()
            assert not app.import_busy and dialog.closed


def case_minimum_window_keeps_settings_and_import_button_full_height(root, patch):
    with hidden_app(root, patch) as app:
        # Geometry negotiation needs a mapped root. Keep it fully transparent,
        # outside the desktop and without a taskbar entry throughout the check.
        app.root.attributes('-alpha', 0)
        app.root.overrideredirect(True)
        app.root.geometry('850x720+20000+20000')
        app.root.deiconify()
        app.tabs.select(app.settings_tab)
        app.root.update()
        button=app.settings_panel.save_button
        assert button.winfo_ismapped()
        top=(button.winfo_rootx(),button.winfo_rooty())
        assert top[0] > app.root.winfo_rootx() + 2 * app.root.winfo_width() // 3
        assert top[1] > app.settings_canvas.winfo_rooty() + app.settings_canvas.winfo_height()
        app.settings_canvas.yview_moveto(1)
        app.root.update_idletasks()
        assert (button.winfo_rootx(),button.winfo_rooty()) == top
        assert button.winfo_height() >= button.winfo_reqheight()
        body=button.master
        assert body.winfo_height() >= body.winfo_reqheight()
        app.tabs.select(0)
        app.root.update()
        assert not button.winfo_ismapped()
        app.tabs.select(app.settings_tab)
        app.root.update()
        assert button.winfo_ismapped()
        dialog=app.open_dictionary_import()
        dialog.window.attributes('-alpha',0)
        dialog.window.overrideredirect(True)
        dialog.window.geometry('700x580+20000+20000')
        dialog.window.deiconify()
        app.root.update()
        for button in (dialog.preview_button,dialog.commit_button,dialog.close_button):
            assert button.winfo_height() >= button.winfo_reqheight()


def case_display_preview_and_save_preserve_engine_and_dictionary(root, patch):
    with hidden_app(root, patch) as app:
        panel=app.settings_panel
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587')
        engine=app.get_engine();engine.set_term('','en','zh-Hans','Welcome','\u6b22\u8fce')
        before=engine.get_stats()
        panel.vars['overlay_font_family'].set('SimSun')
        assert 'SimSun' in panel.font_box.get()
        assert '\u82f1\u8bed' in panel.preview_text.get()
        panel.vars['show_source_label'].set(False)
        assert panel.preview_text.get()=='[\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c]'
        panel.vars['show_translation_brackets'].set(False)
        assert panel.preview_text.get()=='\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c'
        assert app.save_settings()
        assert app.engine is engine
        assert engine.get_stats()==before
        assert engine.list_terms('','en','zh-Hans')==[{'source':'Welcome','target':'\u6b22\u8fce'}]
        saved=ConfigStore(root).load()
        assert saved['overlay_font_family']=='SimSun'
        assert saved['show_source_label'] is False and saved['show_translation_brackets'] is False
        assert saved['source_lang']=='en' and saved['target_lang']=='zh-Hans'
        assert tuple(panel.language_box['values'])==('\u7b80\u4f53\u4e2d\u6587','English','\u65e5\u672c\u8a9e (beta)')
        panel.app_language_var.set('\u65e5\u672c\u8a9e (beta)');assert panel.values()['app_language']=='ja'
        panel.vars['overlay_font_family'].set('x'*32)
        assert not app.save_settings()
        assert ConfigStore(root).load()['overlay_font_family']=='SimSun'


def case_translation_language_selection_restores_and_persists(root, patch):
    with hidden_app(root, patch, settings={'source_lang':'en','target_lang':'ja'}) as app:
        assert app.source.get()=='\u82f1\u8bed' and app.target.get()=='\u65e5\u8bed'
        language_controls=[control for control,state in app.scope_controls
                           if state=='readonly' and control is not app.profile_box]
        assert len(language_controls)==2
        assert all('\u82f1\u8bed' in control['values'] for control in language_controls)
        app.source.set('\u6cd5\u8bed');app.target.set('\u82f1\u8bed')
        app.translation_language_changed()
        loaded=ConfigStore(root).load()
        assert loaded['source_lang']=='fr' and loaded['target_lang']=='en'
        assert module.translation_language_name(loaded['source_lang'],'\u65e5\u8bed')=='\u6cd5\u8bed'
        assert module.translation_language_name(loaded['target_lang'],'\u7b80\u4f53\u4e2d\u6587')=='\u82f1\u8bed'
        assert module.translation_language_name('zh-CN','\u65e5\u8bed')=='\u7b80\u4f53\u4e2d\u6587'
        assert module.translation_language_name('en-US','\u65e5\u8bed')=='\u82f1\u8bed'


def case_mixed_label_checkbox_preview_busy_and_persistence(root, patch):
    with hidden_app(root, patch) as app:
        panel=app.settings_panel
        assert panel.vars['source_label_mixed_only'].get() is True
        assert panel.preview_text.get()=='\u5355\u8bed\uff1a[\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c]\n\u6df7\u5408\uff1a[\u82f1\u8bed\uff1a\u6b22\u8fce] / [\u65e5\u8bed\uff1a\u5f00\u59cb]'
        panel.vars['show_translation_brackets'].set(False)
        assert panel.preview_text.get()=='\u5355\u8bed\uff1a\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c\n\u6df7\u5408\uff1a\u82f1\u8bed\uff1a\u6b22\u8fce / \u65e5\u8bed\uff1a\u5f00\u59cb'
        panel.vars['show_source_label'].set(False)
        assert str(panel.mixed_only_check['state'])=='disabled'
        assert panel.preview_text.get()=='\u6b22\u8fce\u6765\u5230\u661f\u9645\u4e16\u754c'
        panel.vars['show_source_label'].set(True)
        assert str(panel.mixed_only_check['state'])=='normal'
        panel.refresh(True)
        panel.vars['show_source_label'].set(False)
        panel.vars['show_source_label'].set(True)
        assert str(panel.mixed_only_check['state'])=='disabled'
        panel.refresh(False)
        assert str(panel.mixed_only_check['state'])=='normal'
        engine=app.get_engine();before=engine.get_stats()
        assert app.save_settings()
        assert app.engine is engine and engine.get_stats()==before
        saved=ConfigStore(root).load()
        assert saved['source_label_mixed_only'] is True
        assert saved['show_source_label'] is True
        assert saved['show_translation_brackets'] is False
        assert not app.save_settings({'source_label_mixed_only':'false'})
        assert ConfigStore(root).load()['source_label_mixed_only'] is True


def case_start_passes_display_options_without_changing_translation_scope(root, patch):
    with hidden_app(root, patch, settings={'source_lang':'en','target_lang':'zh-Hans',
            'overlay_font_family':'SimSun','show_source_label':False,'show_translation_brackets':False,
            'scene_change_sensitivity':95,'translation_hold_ms':150}) as app:
        core=Mock();core.languages.return_value=['en-US'];app.core=core
        target={'hwnd':123,'pid':456,'process_path':r'C:\Game\Fixture.exe','exe_name':'Fixture.exe'}
        patch.setattr(module,'GameProcess',Mock(return_value=Mock(exited=Mock(return_value=False))))
        patch.setattr(app,'chosen_window',lambda:target)
        patch.setattr(app,'remember_profile',lambda:None)
        pipeline=Mock();pipeline.alive=False
        constructor=Mock(return_value=pipeline);patch.setattr(module,'Pipeline',constructor)
        app.start()
        core.set_overlay_font.assert_called_once_with('SimSun')
        assert core.enable_live_capture.call_args.kwargs['scene_change_sensitivity'] == 95
        assert core.enable_live_capture.call_args.kwargs['translation_hold_ms'] == 150
        assert constructor.called, app.status.get()
        assert constructor.call_args.kwargs['show_source_label'] is False
        assert constructor.call_args.kwargs['show_translation_brackets'] is False
        assert constructor.call_args.kwargs['source_label_mixed_only'] is True
        assert pipeline.start.call_args.args[2:4]==('en','zh-Hans')


def case_context_archive_view_is_readonly_and_does_not_call_api(root,patch):
    with hidden_app(root,patch) as app:
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.game.set('History')
        engine=app.get_engine()
        with engine._lock,engine._db:
            engine.context_archive.record(('History','en','zh-Hans'),None,'Welcome','\u6b22\u8fce','Station','{}','synthetic')
        before=engine.get_stats()['session_requests']
        window=app.open_translation_history()
        assert window is not None
        texts=[]
        def visit(widget):
            if isinstance(widget,module.tk.Text):texts.append(widget.get('1.0','end'))
            for child in widget.winfo_children():visit(child)
        visit(window)
        assert any('Welcome' in text and '\u6b22\u8fce' in text and 'Station' in text for text in texts)
        assert engine.get_stats()['session_requests']==before==0
        window.destroy()


def case_font_and_capture_settings_states_and_persistence(root,patch):
    with hidden_app(root,patch) as app:
        panel=app.settings_panel
        assert panel.vars['capture_translations'].get()
        assert str(panel.font_size_controls['overlay_font_size']['state'])=='disabled'
        panel.vars['auto_font_size'].set(False)
        assert str(panel.font_size_controls['overlay_font_size']['state'])=='normal'
        assert str(panel.font_size_controls['overlay_font_min']['state'])=='disabled'
        panel.vars['overlay_font_size'].set('27')
        panel.vars['overlay_font_min'].set('12');panel.vars['overlay_font_max'].set('48')
        panel.vars['capture_translations'].set(False)
        app.save_settings()
        loaded=app.config_store.load()
        assert loaded['overlay_font_size']==27 and loaded['overlay_font_min']==12 and loaded['overlay_font_max']==48
        assert loaded['auto_font_size'] is False and loaded['capture_translations'] is False
        panel.refresh(True)
        assert all(str(c['state'])=='disabled' for c in panel.font_size_controls.values())
        panel.refresh(False)
        assert str(panel.font_size_controls['overlay_font_size']['state'])=='normal'


def case_context_agent_switch_persists_and_status_does_not_translate_or_leak(root, patch):
    with hidden_app(root, patch, key=SYNTHETIC_KEY) as app:
        assert app.settings_panel.vars['context_web_search'].get() is False
        assert app.save_settings({'context_web_search': True})
        assert ConfigStore(root).load()['context_web_search'] is True
        app.settings_panel.refresh(False)
        assert app.settings_panel.context_agent_status.get() == '\u8054\u7f51\u7406\u89e3\uff1a\u7b49\u5f85\u9996\u6bb5\u6587\u5b57'
        engine = app.get_engine()
        assert engine.get_stats()['session_requests'] == 0
        app.settings_panel.refresh(False)
        assert SYNTHETIC_KEY not in app.settings_panel.context_agent_status.get()
        assert app.save_settings({'context_web_search': False})
        app.settings_panel.refresh(False)
        assert app.settings_panel.context_agent_status.get() == '\u8054\u7f51\u7406\u89e3\uff1a\u5df2\u5173\u95ed'


CASES=[name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case',CASES)
def test_hidden_settings_and_import(case):
    process=subprocess.run([sys.executable,'-c',
        'import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',
        str(Path(__file__).resolve()),case],cwd=module.ROOT,capture_output=True,text=True,
        timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0,process.stdout+process.stderr


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='tuning-ui-') as folder,pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[-1]](Path(folder),patch)

