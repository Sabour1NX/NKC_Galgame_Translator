# SPDX-License-Identifier: MIT
"""Hidden Tk onboarding, consent and API controls; one Tcl process per case."""
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import Mock

import httpx
import pytest

import nkc_galgame_translator.app as module
from nkc_galgame_translator.agreement import AGREEMENT_VERSION
from nkc_galgame_translator.config_store import ConfigStore, ConfigStoreError


SYNTHETIC_KEY = 'synthetic-key-for-hidden-ui-tests-no-real-api-access'
BASE_URL = 'https://api.example.test/v1'
MODEL = 'synthetic-model'


@contextmanager
def hidden_app(root, patch, *, accepted=True, key=None, settings=None):
    """Use an isolated config and withdraw windows before any event loop runs."""
    project_root = module.ROOT
    (root / 'config').mkdir()
    (root / 'config' / 'example.json').write_text(json.dumps({
        'api_key': 'YOUR_API_KEY', 'offline_only': True, 'game': '',
        'base_url': BASE_URL, 'model': MODEL,
    }), encoding='utf-8')
    # These cases begin at agreement/API setup, after the separate language step.
    # Interface-language tests explicitly override selected=False for first run.
    config = {'offline_only': True, 'app_language': 'zh-CN', 'app_language_selected': True}
    if accepted:
        config.update(agreement_version=AGREEMENT_VERSION,
                      agreement_accepted_at='2026-11-14T00:00:00+00:00')
    if settings:
        config.update(settings)
    ConfigStore(root).save(config, api_key=key)
    shutil.copytree(project_root / 'assets', root / 'assets')
    patch.setattr(module, 'ROOT', root)
    patch.setattr(module, 'window_list', lambda: [])
    def no_network(*args, **kwargs):
        pytest.fail('Onboarding and settings tests must not construct an HTTP client')
    patch.setattr(httpx, 'Client', no_network)
    patch.setattr(httpx, 'AsyncClient', no_network)
    original_root, original_top = module.tk.Tk, module.tk.Toplevel
    def hidden_root(*args, **kwargs):
        window = original_root(*args, **kwargs)
        window.withdraw()
        return window
    def hidden_top(*args, **kwargs):
        window = original_top(*args, **kwargs)
        window.withdraw()
        return window
    patch.setattr(module.tk, 'Tk', hidden_root)
    patch.setattr(module.tk, 'Toplevel', hidden_top)
    app = module.App(show_setup=False)
    try:
        yield app
    finally:
        app.close()


def case_unaccepted_agreement_blocks_both_translation_paths(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        chosen = Mock(side_effect=AssertionError('Must not select game without consent'))
        engine = Mock(side_effect=AssertionError('Must not get engine without consent'))
        pipeline = Mock(side_effect=AssertionError('Must not construct pipeline without consent'))
        patch.setattr(app, 'chosen_window', chosen)
        patch.setattr(app, 'get_engine', engine)
        patch.setattr(module, 'Pipeline', pipeline)
        app.manual_input.insert('1.0', 'Synthetic untranslated text')
        app.start()
        app.manual_translate()
        chosen.assert_not_called()
        engine.assert_not_called()
        pipeline.assert_not_called()
        assert not app.manual_busy
        assert app.pipeline is None
        assert app.tabs.select() == str(app.agreement_tab)
        assert '\u534f\u8bae' in app.status.get()
        assert str(app.start_button['state']) == 'disabled'
        assert str(app.manual_button['state']) == 'disabled'
        assert app.show_api_settings() is None
        with pytest.raises(ValueError, match='\u534f\u8bae'):
            app.save_api_settings(BASE_URL, MODEL, offline_only=True)


def case_accept_requires_checkbox_and_persists_version_and_time(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        original = app.config_store.config_path.read_bytes()
        assert not app.accept_agreement()
        assert not app.agreement_accepted
        assert app.config_store.config_path.read_bytes() == original
        assert '\u52fe\u9009' in app.agreement_status.get()
        app.agreement_checked.set(True)
        app._refresh_agreement_button()
        assert str(app.accept_agreement_button['state']) == 'normal'
        assert app.accept_agreement()
        saved = ConfigStore(root).load()
        assert saved['agreement_version'] == AGREEMENT_VERSION
        assert datetime.fromisoformat(saved['agreement_accepted_at']).tzinfo is not None
        assert saved['api_key'] == ''
        assert app.agreement_accepted
        assert app.agreement_checked.get()
        assert str(app.agreement_checkbox['state']) == 'disabled'
        assert app.accept_agreement_button['text'] == '\u5df2\u6388\u6743'
        assert app.tabs.index(app.tabs.select()) == 0
        assert str(app.start_button['state']) == 'normal'
        assert str(app.manual_button['state']) == 'normal'
        assert app.api_dialog is None  # show_setup=False suppresses automatic dialogs.


def case_accept_save_failure_does_not_grant_runtime_consent(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        before = app.config_store.config_path.read_bytes()
        app.agreement_checked.set(True)
        patch.setattr(app.config_store, 'save', Mock(side_effect=PermissionError(SYNTHETIC_KEY)))
        assert not app.accept_agreement()
        assert not app.agreement_accepted
        assert SYNTHETIC_KEY not in app.agreement_status.get()
        assert app.config_store.config_path.read_bytes() == before
        assert str(app.start_button['state']) == 'disabled'


def case_outdated_agreement_is_not_current_consent(root, patch):
    with hidden_app(root, patch, settings={'agreement_version': 'obsolete-test-version'}) as app:
        assert not app.agreement_accepted
        dialog = Mock()
        patch.setattr(app, 'show_api_settings', dialog)
        app.root.after_idle(app.show_initial_setup)
        app.root.update_idletasks()
        dialog.assert_not_called()
        assert app.tabs.select() == str(app.agreement_tab)


def case_first_launch_and_missing_key_trigger_setup_even_after_offline_choice(root, patch):
    with hidden_app(root, patch) as app:
        dialog = Mock()
        patch.setattr(app, 'show_api_settings', dialog)
        # Explicitly run the startup callback; never map a user-visible window.
        app.root.after_idle(app.show_initial_setup)
        app.root.update_idletasks()
        assert dialog.call_count == 1
        app.save_api_settings(BASE_URL, MODEL, offline_only=True)
        assert app.config['api_setup_complete']
        app.show_initial_setup()
        assert dialog.call_count == 2
        app.save_api_settings(BASE_URL, MODEL, api_key=SYNTHETIC_KEY, offline_only=True)
        app.show_initial_setup()
        assert dialog.call_count == 2
        app.config['api_setup_complete'] = False
        app.show_initial_setup()
        assert dialog.call_count == 3


def case_unaccepted_first_launch_only_opens_agreement(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        dialog = Mock()
        patch.setattr(app, 'show_api_settings', dialog)
        app.root.after_idle(app.show_initial_setup)
        app.root.update_idletasks()
        dialog.assert_not_called()
        assert app.tabs.select() == str(app.agreement_tab)
        assert not app.root.winfo_viewable()


def case_online_dialog_missing_key_fails_then_offline_choice_saves(root, patch):
    with hidden_app(root, patch) as app:
        before = app.config_store.config_path.read_bytes()
        dialog = app.show_api_settings()
        assert dialog is not None
        assert not dialog.window.winfo_viewable()
        assert dialog.key.get() == ''
        assert dialog.key_entry['show'] == '●'
        assert not dialog.save_online()
        assert '\u5bc6\u94a5' in dialog.error.get()
        assert app.config_store.config_path.read_bytes() == before
        assert dialog.window.winfo_exists()
        assert dialog.use_offline()
        assert app.api_dialog is None
        saved = ConfigStore(root).load()
        assert saved['api_key'] == ''
        assert saved['api_setup_complete'] is True
        assert saved['offline_only'] is True
        assert not app.has_api_key


def case_online_settings_encrypt_key_and_reset_idle_engine(root, patch):
    with hidden_app(root, patch) as app:
        engine = app.get_engine()
        app.source.set('\u82f1\u8bed')
        engine.set_term('', 'en', 'zh-Hans', 'Hello', '\u4f60\u597d')
        dialog = app.show_api_settings()
        dialog.key.set(SYNTHETIC_KEY)
        assert dialog.save_online()
        assert dialog.key.get() == ''
        assert app.api_dialog is None
        assert app.engine is None
        assert app.has_api_key
        assert not app.offline_only.get()
        saved = ConfigStore(root).load()
        assert saved['api_key'] == SYNTHETIC_KEY
        assert saved['model'] == MODEL
        assert saved['base_url'] == BASE_URL
        assert saved['offline_only'] is False
        assert SYNTHETIC_KEY.encode() not in app.config_store.config_path.read_bytes()
        assert SYNTHETIC_KEY.encode() not in app.config_store.credentials_path.read_bytes()
        assert 'api_key' not in json.loads(app.config_store.config_path.read_text(encoding='utf-8'))


def case_offline_dialog_preserves_key_unless_explicitly_cleared(root, patch):
    with hidden_app(root, patch, key=SYNTHETIC_KEY, settings={'api_setup_complete': True}) as app:
        dialog = app.show_api_settings()
        assert dialog.key.get() == ''
        dialog.key.set('synthetic-unsubmitted-replacement-must-not-be-saved')
        assert dialog.use_offline()
        assert ConfigStore(root).load()['api_key'] == SYNTHETIC_KEY
        assert app.offline_only.get()
        dialog = app.show_api_settings()
        dialog.clear_key.set(True)
        assert not dialog.save_online()
        assert dialog.window.winfo_exists()
        assert ConfigStore(root).load()['api_key'] == SYNTHETIC_KEY
        assert dialog.use_offline()
        assert ConfigStore(root).load()['api_key'] == ''
        assert not app.has_api_key
        assert not app.config_store.credentials_path.exists()


def case_offline_accepts_blank_online_form_without_saving_unsubmitted_key(root, patch):
    with hidden_app(root, patch) as app:
        dialog = app.show_api_settings()
        dialog.base_url.set('')
        dialog.model.set('')
        dialog.key.set(SYNTHETIC_KEY)
        assert dialog.use_offline()
        assert app.api_dialog is None
        saved = ConfigStore(root).load()
        assert saved['base_url'] == BASE_URL
        assert saved['model'] == MODEL
        assert saved['offline_only'] is True
        assert saved['api_key'] == ''
        assert saved['api_setup_complete'] is True
        assert dialog.key.get() == ''
        assert not app.config_store.credentials_path.exists()
        contents = app.config_store.config_path.read_text(encoding='utf-8')
        assert SYNTHETIC_KEY not in contents
        assert 'api_key' not in json.loads(contents)


def case_offline_ignores_invalid_unsubmitted_connection_fields(root, patch):
    with hidden_app(root, patch) as app:
        dialog = app.show_api_settings()
        dialog.base_url.set('http://user:password@bad endpoint.test?token=unsubmitted')
        dialog.model.set('invalid\nmodel')
        dialog.key.set('invalid unsubmitted key')
        assert dialog.use_offline()
        saved = ConfigStore(root).load()
        assert saved['base_url'] == BASE_URL
        assert saved['model'] == MODEL
        assert saved['api_key'] == ''
        assert app.offline_only.get()
        contents = app.config_store.config_path.read_text(encoding='utf-8')
        assert 'unsubmitted' not in contents
        assert 'password' not in contents
        assert 'api_key' not in json.loads(contents)
        assert not app.config_store.credentials_path.exists()


def case_busy_translation_blocks_dialog_and_settings_without_mutation(root, patch):
    with hidden_app(root, patch) as app:
        before = app.config_store.config_path.read_bytes()
        busy_engine = Mock()
        busy_engine.get_stats.return_value = {'in_flight': 1}
        for condition in ('manual', 'pipeline', 'in_flight'):
            app.manual_busy = condition == 'manual'
            app.pipeline = Mock() if condition == 'pipeline' else None
            app.engine = busy_engine if condition == 'in_flight' else None
            app._refresh_mode_control()
            assert str(app.api_settings_button['state']) == 'disabled'
            assert app.show_api_settings() is None
            with pytest.raises(ValueError, match='\u505c\u6b62\u7ffb\u8bd1'):
                app.save_api_settings(BASE_URL, MODEL, api_key=SYNTHETIC_KEY)
            assert app.config_store.config_path.read_bytes() == before
            assert not app.config_store.credentials_path.exists()
        app.manual_busy = False
        app.pipeline = None
        app.engine = None
        app._refresh_mode_control()
        assert str(app.api_settings_button['state']) == 'normal'


def case_dialog_close_discards_unsaved_key_without_persisting(root, patch):
    with hidden_app(root, patch) as app:
        before = app.config_store.config_path.read_bytes()
        dialog = app.show_api_settings()
        assert app.show_api_settings() is dialog
        dialog.key.set(SYNTHETIC_KEY)
        dialog.close()
        assert dialog.key.get() == ''
        assert app.api_dialog is None
        assert app.config_store.config_path.read_bytes() == before
        assert not app.config_store.credentials_path.exists()


def case_api_settings_reject_invalid_endpoints_models_and_keys(root, patch):
    with hidden_app(root, patch) as app:
        before = app.config_store.config_path.read_bytes()
        invalid_values = [
            ('http://api.example.test', MODEL, SYNTHETIC_KEY),
            ('https://name:password@api.example.test', MODEL, SYNTHETIC_KEY),
            ('https://api.example.test?token=anything', MODEL, SYNTHETIC_KEY),
            ('https://api.example.test#fragment', MODEL, SYNTHETIC_KEY),
            ('https://api.example.test:invalid', MODEL, SYNTHETIC_KEY),
            (BASE_URL, '', SYNTHETIC_KEY),
            (BASE_URL, 'invalid\nmodel', SYNTHETIC_KEY),
            (BASE_URL, MODEL, 'invalid key'),
            (BASE_URL, MODEL, '\u5bc6\u94a5'),
            (BASE_URL, MODEL, 'YOUR_API_KEY'),
        ]
        for endpoint, model, key in invalid_values:
            with pytest.raises(ValueError) as error:
                app.save_api_settings(endpoint, model, api_key=key)
            assert SYNTHETIC_KEY not in str(error.value)
            assert app.config_store.config_path.read_bytes() == before
            assert not app.config_store.credentials_path.exists()


def case_dialog_save_failure_keeps_runtime_config_and_redacts_errors(root, patch):
    with hidden_app(root, patch) as app:
        before = dict(app.config)
        persisted_before = app.config_store.config_path.read_bytes()
        dialog = app.show_api_settings()
        dialog.key.set(SYNTHETIC_KEY)
        patch.setattr(app.config_store, 'save_api_slot', Mock(side_effect=OSError(SYNTHETIC_KEY)))
        assert not dialog.save_online()
        assert SYNTHETIC_KEY not in dialog.error.get()
        assert app.config == before
        assert app.config_store.config_path.read_bytes() == persisted_before
        assert not app.has_api_key
        assert dialog.window.winfo_exists()


def case_api_entry_is_located_in_settings_page(root, patch):
    with hidden_app(root, patch) as app:
        assert app.api_settings_button['text'] == 'API \u914d\u7f6e · 3 \u69fd\u4f4d'
        assert app.api_settings_button['style'] == 'Accent.TButton'
        parent=app.api_settings_button.master
        ancestors=[]
        while parent is not None:
            ancestors.append(parent);parent=getattr(parent,'master',None)
        assert app.settings_tab in ancestors
        app.root.update_idletasks()
        app.tabs.select(app.settings_tab)
        assert '\u69fd\u4f4d 1' in app.api_slot_hint.get()
        app.api_settings_button.invoke()
        assert app.api_dialog is not None
        assert len(app.api_dialog.slot_buttons) == 3


def case_three_slots_switch_independently_and_never_echo_saved_key(root, patch):
    with hidden_app(root, patch, key=SYNTHETIC_KEY) as app:
        for index in (1, 2):
            dialog = app.show_api_settings()
            assert dialog.select_slot(index)
            assert dialog.key.get() == ''
            dialog.base_url.set(f'https://api{index}.example.test/v1')
            dialog.model.set(f'model-{index}')
            dialog.key.set(SYNTHETIC_KEY+str(index))
            assert dialog.save_online()
            assert app.config['active_api_slot'] == index
            assert app.config['api_key'] == SYNTHETIC_KEY+str(index)
            assert f'\u69fd\u4f4d {index+1}' in app.api_slot_hint.get()
        dialog = app.show_api_settings()
        assert dialog.select_slot(0)
        assert dialog.key.get() == ''
        assert dialog.base_url.get() == BASE_URL
        assert dialog.model.get() == MODEL
        assert dialog.save_online()
        assert app.config['api_key'] == SYNTHETIC_KEY
        saved = ConfigStore(root).load()
        assert saved['active_api_slot'] == 0
        assert all(s['has_api_key'] for s in saved['api_slots'])
        assert all('api_key' not in s for s in saved['api_slots'])


def case_switch_retains_unsaved_drafts_and_save_does_not_discard_other_slot(root, patch):
    with hidden_app(root, patch) as app:
        dialog = app.show_api_settings()
        dialog.key.set(SYNTHETIC_KEY)
        dialog.model.set('first-draft')
        assert dialog.select_slot(1)
        dialog.key.set(SYNTHETIC_KEY+'second')
        dialog.model.set('second-draft')
        assert dialog.select_slot(0)
        assert dialog.key.get() == SYNTHETIC_KEY
        assert dialog.model.get() == 'first-draft'
        assert dialog.save_online()
        assert app.api_dialog is dialog
        assert '\u672a\u4fdd\u5b58' in dialog.error.get()
        assert dialog.key.get() == ''
        assert not app.config['api_slots'][1]['has_api_key']
        assert dialog.select_slot(1)
        assert dialog.key.get() == SYNTHETIC_KEY+'second'
        assert dialog.model.get() == 'second-draft'
        assert dialog.save_online()
        assert app.api_dialog is None
        assert dialog.drafts == {}
        assert dialog.key.get() == ''
        assert app.config['api_slots'][0]['has_api_key']
        assert app.config['api_slots'][1]['has_api_key']


def case_empty_other_slot_does_not_borrow_active_key(root, patch):
    with hidden_app(root, patch,key=SYNTHETIC_KEY) as app:
        before=app.config_store.config_path.read_bytes()
        dialog=app.show_api_settings()
        dialog.select_slot(2)
        assert not dialog.save_online()
        assert '\u5bc6\u94a5' in dialog.error.get()
        assert app.config['active_api_slot']==0
        assert app.config_store.config_path.read_bytes()==before
        dialog.key.set('unsubmitted-invalid-key')
        dialog.base_url.set('')
        dialog.model.set('')
        assert dialog.use_offline()
        assert app.config['active_api_slot']==2
        assert app.config['api_key']==''
        assert app.config['api_slots'][0]['has_api_key']
        assert not app.config['api_slots'][2]['has_api_key']


def case_clear_only_selected_slot_and_close_discards_all_drafts(root, patch):
    with hidden_app(root, patch,key=SYNTHETIC_KEY) as app:
        app.save_api_settings(BASE_URL,MODEL,api_key=SYNTHETIC_KEY+'second',slot=1)
        dialog=app.show_api_settings()
        dialog.select_slot(0)
        dialog.clear_key.set(True)
        assert dialog.use_offline()
        assert app.config['api_key']==''
        assert not app.config['api_slots'][0]['has_api_key']
        assert app.config['api_slots'][1]['has_api_key']
        dialog=app.show_api_settings()
        dialog.key.set(SYNTHETIC_KEY+'unsaved-first')
        dialog.select_slot(2)
        dialog.key.set(SYNTHETIC_KEY+'unsaved-last')
        dialog.close()
        assert dialog.drafts=={}
        assert dialog.key.get()==''
        saved=ConfigStore(root).load()
        assert not saved['api_slots'][0]['has_api_key']
        assert not saved['api_slots'][2]['has_api_key']


def case_busy_open_dialog_disables_slot_selection_and_all_mutations(root, patch):
    with hidden_app(root, patch,key=SYNTHETIC_KEY) as app:
        dialog=app.show_api_settings()
        app.manual_busy=True
        app._refresh_mode_control()
        assert all(str(b['state'])=='disabled' for b in dialog.slot_buttons)
        assert str(dialog.save_button['state'])=='disabled'
        assert str(dialog.key_entry['state'])=='disabled'
        before=app.config_store.config_path.read_bytes()
        assert not dialog.select_slot(1)
        assert dialog.slot.get()==0
        assert not dialog.save_online()
        assert not dialog.use_offline()
        assert app.config_store.config_path.read_bytes()==before
        app.manual_busy=False
        app._refresh_mode_control()
        assert all(str(b['state'])=='normal' for b in dialog.slot_buttons)


def case_saved_key_placeholder_is_visual_and_draft_aware(root,patch):
    with hidden_app(root,patch,key=SYNTHETIC_KEY) as app:
        dialog=app.show_api_settings()
        shown=lambda:dialog.key_placeholder.winfo_manager()=='place'
        assert shown() and dialog.key.get()=='' and dialog._replacement_key() is None
        assert dialog.key_placeholder['text']=='●'*12
        dialog._focus_key_entry()
        assert shown()
        dialog.key.set('new-synthetic-key')
        assert not shown()
        dialog.key.set('')
        assert shown()
        dialog.clear_key.set(True)
        assert not shown() and dialog._replacement_key()==''
        dialog.clear_key.set(False)
        assert shown()
        dialog.base_url.set('https://another.example.test')
        assert not shown()
        dialog.base_url.set(BASE_URL)
        assert shown()
        assert dialog.select_slot(1) and not shown()
        assert dialog.select_slot(0) and shown()
        credentials=app.config_store.credentials_path.read_bytes()
        assert dialog.save_online()
        assert app.config_store.credentials_path.read_bytes()==credentials
        dialog=app.show_api_settings()
        assert dialog.key_placeholder.winfo_manager()=='place' and dialog.key.get()==''


def case_consent_gates_tabs_and_decline_exits(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        assert app.tabs.select()==str(app.agreement_tab)
        for tab in app.tabs.tabs():
            assert app.tabs.tab(tab,'state')==('normal' if tab==str(app.agreement_tab) else 'disabled')
        destroyed=[]
        app.root.bind('<Destroy>',lambda e:destroyed.append(e.widget is app.root),add='+')
        app.decline_agreement_button.invoke()
        assert True in destroyed
        patch.setattr(app,'close',lambda:None)


def case_persistent_consent_and_fixed_start_with_shortcut_hint(root, patch):
    with hidden_app(root, patch) as app:
        assert app.agreement_checked.get()
        assert '\u5df2\u6388\u6743' in app.tabs.tab(app.agreement_tab,'text')
        assert app.start_button.master is app.run_action_bar
        assert app.run_action_bar.pack_info()['side']=='bottom'
        assert 'Ctrl+Alt+R' in app.hotkey_hint.get()
        assert not hasattr(app,'retranslate_button')
        app.apply_ui_language('en')
        assert 'accepted' in app.tabs.tab(app.agreement_tab,'text').lower()
        assert app.agreement_checked.get()


def case_profiles_save_restore_and_deleted_selection_does_not_resurrect(root, patch):
    with hidden_app(root, patch) as app:
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587')
        app.game.set('Review A');app.profile_changed()
        app.context.set('The crew are merchants.');assert app._persist_profile()
        assert app.get_engine().get_profile('Review A')['notes']=='The crew are merchants.'
        app.game.set('Review B');app.profile_changed()
        assert app.context.get()==''
        app.context.set('A different journey.');app._persist_profile()
        app.resume_profile(app.get_engine().get_profile('Review A'))
        assert app.context.get()=='The crew are merchants.'
        assert ConfigStore(root).load()['last_profile']=='Review A'
        app.get_engine().delete_profile('Review A');app._profiles_changed()
        assert app.game.get()=='' and app.context.get()==''
        app._persist_profile()
        assert app.get_engine().get_profile('Review A') is None
        assert app.get_engine().get_profile('Review B')['notes']=='A different journey.'


def case_shortcut_retranslation_targets_existing_pipeline(root, patch):
    with hidden_app(root, patch) as app:
        pipeline=Mock();pipeline.request_retranslation.return_value=True
        app.pipeline=pipeline
        app.events.put(('retranslate',0,None))
        app.drain()
        pipeline.request_retranslation.assert_called_once_with()
        assert '\u91cd\u65b0\u8bc6\u522b' in app.status.get()
        app.pipeline=None


def case_provider_presets_keep_slot_credentials_bound(root, patch):
    with hidden_app(root,patch,key=SYNTHETIC_KEY) as app:
        dialog=app.show_api_settings()
        assert dialog.provider.current()==2  # This fixture uses a custom endpoint.
        dialog.select_slot(1)
        assert dialog.provider.current()==0 and dialog.model.get()=='deepseek-flash'
        dialog.key.set('synthetic-unsaved-key')
        dialog.provider.current(1);dialog._choose_provider()
        assert dialog.base_url.get()=='https://api.openai.com/v1'
        assert dialog.model.get()=='gpt-4.1-mini' and not dialog.key.get()
        dialog.key.set('synthetic-openai-test-key')
        dialog.select_slot(0);dialog.select_slot(1)
        assert dialog.provider.current()==1 and dialog.key.get()=='synthetic-openai-test-key'
        dialog.save_online()
        saved=ConfigStore(root).load()
        assert saved['active_api_slot']==1 and saved['api_key']=='synthetic-openai-test-key'
        reopened=app.show_api_settings()
        assert reopened.provider.current()==1 and not reopened.key.get()
        reopened.provider.current(2);reopened._choose_provider()
        assert not reopened.base_url.get() and not reopened.model.get()
        reopened.base_url.set('https://custom.example/v1');reopened.model.set('custom-vision')
        reopened.key.set('synthetic-entered-for-custom')
        reopened.base_url.set('https://other.example/v1')
        assert not reopened.key.get()
        reopened.close()
        assert ConfigStore(root).load()['api_key']=='synthetic-openai-test-key'


def case_shortcut_settings_update_hint_and_rollback_on_save_failure(root, patch):
    from types import SimpleNamespace
    with hidden_app(root, patch) as app:
        services=[Mock(),Mock(),Mock()]
        for service in services:
            service.update.side_effect=lambda enabled,key:SimpleNamespace(error='',registered=enabled,shortcut=key)
        factory=Mock(side_effect=services)
        patch.setattr(module,'GlobalHotkey',factory)
        app.show_setup=True
        app.settings_panel.vars['retranslate_hotkey'].set('Ctrl+Alt+Y')
        assert app.save_settings()
        assert 'Ctrl+Alt+Y' in app.hotkey_hint.get()
        assert 'Ctrl+Alt+T' in app.hotkey_hint.get()
        assert ConfigStore(root).load()['retranslate_hotkey']=='Ctrl+Alt+Y'
        persisted=app.config_store.config_path.read_bytes()
        app.settings_panel.vars['retranslate_hotkey'].set('Ctrl+Alt+U')
        app.settings_panel.vars['toggle_hotkey'].set('Ctrl+Alt+I')
        patch.setattr(app.config_store,'save',Mock(side_effect=OSError('synthetic failure')))
        assert not app.save_settings()
        assert services[0].update.call_args.args==(True,'Ctrl+Alt+Y')
        assert services[1].update.call_args.args==(True,'Ctrl+Alt+T')
        assert 'Ctrl+Alt+Y' in app.hotkey_hint.get()
        assert 'Ctrl+Alt+T' in app.hotkey_hint.get()
        assert app.config_store.config_path.read_bytes()==persisted


def case_profile_notes_and_selection_restore_in_next_app(root, patch):
    with hidden_app(root, patch) as app:
        app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587')
        app.game.set('Persistent journey');app.profile_changed()
        app.context.set('Mira is the navigator.');app._persist_profile()
        app.close();patch.setattr(app,'close',lambda:None)
        reopened=module.App(show_setup=False)
        try:
            assert reopened.game.get()=='Persistent journey'
            assert reopened.context.get()=='Mira is the navigator.'
            assert reopened.source.get()=='\u82f1\u8bed'
            assert reopened.agreement_checked.get()
        finally:reopened.close()


def case_local_presets_work_without_keys_and_survive_reopen(root, patch):
    with hidden_app(root, patch, key=SYNTHETIC_KEY) as app:
        dialog = app.show_api_settings()
        assert tuple(dialog.provider['values'])[-2:] == ('Ollama', '\u672c\u5730')
        dialog.select_slot(2)
        assert dialog.provider_hint.get() == 'deepseek-flash'
        dialog.select_slot(0)
        dialog.provider.current(3)
        dialog._choose_provider()
        assert dialog.base_url.get() == 'http://127.0.0.1:11434/v1'
        assert not dialog.key.get() and not dialog.key_placeholder.place_info()
        assert not dialog.save_online()
        dialog.base_url.set('http://localhost:19191/v1')
        dialog.model.set('local-model:latest')
        dialog.select_slot(1)
        dialog.select_slot(0)
        assert dialog.provider.get() == 'Ollama'
        assert dialog.save_online()
        assert app.backend_ready and not app.has_api_key and not app.offline_only.get()
        assert app.config['api_key'] == ''
        assert '\u5df2\u914d\u7f6e' in app.api_slot_hint.get()
        reopened = app.show_api_settings()
        assert reopened.provider.get() == 'Ollama'
        reopened.select_slot(1)
        reopened.provider.current(4)
        reopened._choose_provider()
        assert reopened.base_url.get() == 'http://127.0.0.1:1234/v1'
        reopened.model.set('another-model')
        assert reopened.save_online()
        app.close()
        patch.setattr(app, 'close', lambda: None)
        restarted = module.App(show_setup=False)
        try:
            assert restarted.backend_ready and not restarted.has_api_key and not restarted.offline_only.get()
            assert not restarted.get_engine().offline_only
            restarted.show_initial_setup()
            assert restarted.api_dialog is None
            assert restarted.show_api_settings().provider.get() == '\u672c\u5730'
            slots = restarted.config['api_slots']
            assert slots[0]['local_provider'] == 'ollama' and slots[1]['local_provider'] == 'local'
            assert not any(slot['has_api_key'] for slot in slots)
        finally:
            restarted.close()


def case_appearance_and_toolkit_settings_restore_and_shortcut_leaves_main_hidden(root, patch):
    with hidden_app(root, patch) as app:
        assert app.root.state()=='withdrawn'
        assert app.tabs.tab(app.tabs.tabs()[0],'text')=='\u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1'
        assert not app.export_button.winfo_manager()
        colors={'paper':'#111522','surface':'#262638','ink':'#F0F0F0','accent':'#FAB1CD'}
        assert app.save_settings(dict(interface_theme='custom',interface_colors=colors,
                                      localization_enabled=True,localization_wait='12',
                                      localization_format='csv'))
        assert app.export_button.winfo_manager()=='pack'
        assert ConfigStore(root).load()['interface_colors']==colors
        assert ConfigStore(root).load()['localization_wait']==12
        notify=Mock()
        patch.setattr(module,'shortcut_popup',notify)
        patch.setattr(app,'start',lambda:setattr(app,'pipeline',Mock()))
        app._toggle_translation()
        notify.assert_called_once()
        assert app.root.state()=='withdrawn'
        app.pipeline=None



def case_setup_toolkit_opt_in_and_theme_share_the_same_window(root, patch):
    with hidden_app(root, patch, accepted=False) as app:
        app.show_setup = True
        patch.setattr(app, '_configure_hotkey', Mock())
        api = Mock()
        patch.setattr(app, 'show_api_settings', api)
        wizard = app.show_initial_setup()
        window = wizard.window
        assert wizard.steps[wizard.index][0] == 'User agreement'
        assert str(wizard.next_button['state']) == 'disabled'
        assert not wizard.advance()
        api.assert_not_called()
        app.agreement_checked.set(True)
        assert wizard.advance() and app.agreement_accepted
        wizard.theme.theme.set('\u9713\u8679\u6ce2')
        assert wizard.advance()
        assert wizard.advance()
        assert wizard.window is window and app.setup_dialog is wizard
        assert not wizard.tools_enabled.get()
        assert not wizard.folder_group.winfo_manager()
        wizard.tools_enabled.set(True)
        wizard.refresh_tools()
        assert wizard.folder_group.winfo_manager() == 'pack'
        wizard.folder.set('relative-is-invalid')
        assert not wizard.advance() and wizard.error.get()
        assert not ConfigStore(root).load().get('localization_setup_complete')
        wizard.folder.set(str(root))
        assert wizard.advance()
        app.root.update_idletasks()
        api.assert_called_once()
        assert app.setup_dialog is None
        assert app.resource_usage.winfo_manager() == 'pack'
        saved = ConfigStore(root).load()
        assert saved['interface_theme'] == 'neon' and saved['interface_theme_setup_complete']
        assert saved['localization_enabled'] and saved['localization_setup_complete']
        assert saved['localization_folder'] == str(root)
        assert app.export_button.winfo_manager() == 'pack'


def case_toolkit_default_off_stays_off_after_restart(root, patch):
    with hidden_app(root, patch, settings={'interface_theme': 'nishokuchou'}) as app:
        app.show_setup = True
        patch.setattr(app, 'show_api_settings', Mock())
        wizard = app.show_initial_setup()
        assert len(wizard.steps) == 1
        assert wizard.steps[0][0] == 'Developer tools (Beta)'
        assert wizard.advance()
        app.root.update_idletasks()
        saved = ConfigStore(root).load()
        assert saved['localization_setup_complete'] and not saved['localization_enabled']
        assert not app.export_button.winfo_manager()
        app.show_initial_setup()
        assert app.setup_dialog is None


def case_neon_default_and_system_theme_updates_without_resaving(root, patch):
    from nkc_galgame_translator import themes
    from tkinter import font, ttk

    current = ['#FFFFFF', '#000000', '#0078D4']
    patch.setattr(themes, 'windows_colors', lambda: tuple(current))
    with hidden_app(root, patch) as app:
        fields = app.feature_panel.theme_fields
        assert fields.values()['interface_theme'] == 'neon'
        assert app.resource_usage.winfo_manager() == 'pack'
        assert app.ui_font == 'Source Han Sans SC Medium'
        ui_font = ttk.Style(app.root).lookup('TLabel', 'font')
        assert font.Font(root=app.root, font=ui_font).actual('size') == 11

        app.tabs.select(app.settings_tab)
        box = fields.box
        box.winfo_id()
        box.tk.call('ttk::combobox::SelectEntry', str(box), tuple(fields.labels).index('system'))
        app.root.update()
        assert fields.values()['interface_theme'] == 'system'
        assert app.resource_usage.winfo_manager() == 'pack'
        assert ConfigStore(root).load().get('interface_theme') != 'system'
        app.settings_panel.save_button.invoke()
        assert ConfigStore(root).load()['interface_theme'] == 'system'
        assert app.manual_input.cget('bg') == '#FFFFFF'
        assert app.resource_usage.winfo_manager() == 'pack'
        assert app._system_palette_watch is not None

        app.apply_ui_language('en')
        assert fields.theme.get() == 'Use Windows colors'
        current[:] = ['#101010', '#FFFFFF', '#E45D94']
        app.root.after_cancel(app._system_palette_watch)
        app._update_system_palette()
        assert app.manual_input.cget('bg') == '#101010'
        assert app.manual_input.cget('fg') == '#FFFFFF'
        assert app._ui_colors[4] == '#E45D94'
        assert ConfigStore(root).load()['interface_theme'] == 'system'

        assert app.save_settings({'interface_theme': 'nishokuchou'})
        assert app._system_palette_watch is None
        assert app.manual_input.cget('bg') == themes.PRESETS['nishokuchou']['surface']


def case_profile_context_refreshes_from_archive_without_overwriting_notes(root, patch):
    with hidden_app(root, patch) as app:
        engine = app.get_engine()
        engine.save_profile('Cabin', notes='Stored note', source_lang='ja', target_lang='zh-Hans')
        get_profile = engine.get_profile
        summaries = ['First summary from archive']
        patch.setattr(engine, 'get_profile', lambda name: {**get_profile(name), 'summary_note': summaries[0]})
        app.game.set('Cabin')
        assert app.profile_changed(reopen=True)
        assert app.context.get() == 'Stored note'
        assert app.profile_summary.get() == summaries[0]

        app.context.set('Manual note')
        app.save_profile_context()
        assert app._profile_save_after is None
        assert get_profile('Cabin')['notes'] == 'Manual note'

        engine.save_profile('Cabin', notes='Changed in archive')
        summaries[0] = 'Refreshed summary from archive'
        assert app.profile_changed(reopen=True)
        assert app.context.get() == 'Changed in archive'
        assert app.profile_summary.get() == summaries[0]
        assert get_profile('Cabin')['notes'] == 'Changed in archive'

        app.context.set('Automatic save')
        assert app._profile_save_after is not None
        completed = module.tk.BooleanVar()
        app.root.after(720, lambda: completed.set(True))
        app.root.wait_variable(completed)
        assert get_profile('Cabin')['notes'] == 'Automatic save'


def case_lightweight_disables_region_controls_and_gpu_chart_follows_the_ocr_backend(root, patch):
    from types import SimpleNamespace
    with hidden_app(root, patch) as app:
        app.capture_region = ((4, 5, 22, 40),)
        buttons = (app.select_region_button, app.full_region_button)
        chooser = Mock()
        patch.setattr(app, 'chosen_window', chooser)
        app.lightweight_var.set(True)
        app._apply_lightweight()
        assert all(button.instate(('disabled',)) for button in buttons)
        app.select_region()
        app.full_region()
        chooser.assert_not_called()
        assert app.capture_region == ((4, 5, 22, 40),)

        app.events.put(('toggle_lightweight', 0, None))
        app.drain()
        assert not app.lightweight_var.get()
        assert all(button.instate(('!disabled',)) for button in buttons)
        assert app.capture_region == ((4, 5, 22, 40),)

        assert not app._using_gpu_for_ocr()
        worker = SimpleNamespace(last_status={'state': 'cuda'})
        app._gpu_warm_core = worker
        assert app._using_gpu_for_ocr()
        app._gpu_warm_core = None
        for status, actual in (('ready', True), ('active', True), ('pixel_priority', False), ('failed', False)):
            app.core = SimpleNamespace(cuda_status=status, cuda=worker)
            assert app._using_gpu_for_ocr() is actual
        app.config['cuda_enabled'] = False
        assert not app._using_gpu_for_ocr()
        app.core = None


CASES = [name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case', CASES)
def test_app_setup_flow(case):
    process = subprocess.run([
        sys.executable, '-c',
        'import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',
        str(Path(__file__).resolve()), case,
    ], cwd=module.ROOT, capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0, process.stdout + process.stderr


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='setup-ui-') as folder, pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[-1]](Path(folder), patch)
