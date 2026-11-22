# SPDX-License-Identifier: MIT
"""Public-release UX/security checks with isolated hidden Tk and no HTTP."""
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

fixtures=runpy.run_path(str(Path(__file__).with_name('test_app_setup.py')))
hidden_app=fixtures['hidden_app']
KEY=fixtures['SYNTHETIC_KEY']
URL,MODEL=fixtures['BASE_URL'],fixtures['MODEL']

def pump(app,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        app.root.update()
        assert time.monotonic()<deadline,'Worker did not finish'
        time.sleep(.01)

def case_endpoint_change_cannot_move_saved_key(root,patch):
    with hidden_app(root,patch,key=KEY) as app:
        before=app.config_store.config_path.read_bytes()
        dialog=app.show_api_settings()
        assert dialog.key.get()==''
        dialog.base_url.set('https://different-provider.example.test/v1')
        assert '\u91cd\u65b0\u586b\u5199' in dialog.key_hint.get()
        assert not dialog.save_online()
        assert '\u91cd\u65b0\u586b\u5199' in dialog.error.get()
        assert app.config_store.config_path.read_bytes()==before
        assert KEY not in dialog.error.get()
        dialog.key.set(KEY+'-replacement')
        assert dialog.save_online()
        assert app.config['base_url']=='https://different-provider.example.test/v1'
        assert app.config['api_key']==KEY+'-replacement'

def case_canonical_endpoint_and_model_edit_keep_key(root,patch):
    with hidden_app(root,patch,key=KEY) as app:
        app.save_api_settings('https://API.EXAMPLE.TEST:443/v1/',MODEL+'-new',api_key=None)
        assert app.config['api_key']==KEY
        assert app.config['model']==MODEL+'-new'

def case_unknown_errors_and_oversized_numeric_input_are_not_echoed(root,patch):
    with hidden_app(root,patch) as app:
        assert KEY not in app.settings_error_message(ValueError(KEY))
        dialog=app.show_api_settings();dialog.key.set(KEY)
        patch.setattr(app.config_store,'save_api_slot',Mock(side_effect=ValueError(KEY)))
        assert not dialog.save_online()
        assert KEY not in dialog.error.get()
        dialog.close()
        assert not app.save_settings({'translation_workers':'1'*5000})
        assert '\u6574\u6570' in app.settings_panel.message.get()
        assert len(app.settings_panel.message.get())<100

def case_game_window_selection_is_explicit_and_survives_refresh(root,patch):
    with hidden_app(root,patch) as app:
        rows=[{'title':'Remilia test','process_path':'E:/RemiliaGame/Remilia.exe','hwnd':101,'pid':20},
              {'title':'Another game','process_path':'E:/Game/Game.exe','hwnd':102,'pid':21}]
        patch.setattr(module,'window_list',lambda:rows)
        patch.setattr(module,'window_metadata',lambda hwnd:next((dict(r) for r in rows if r['hwnd']==hwnd),None))
        app.refresh_windows();assert app.windows_box.current()==-1
        app.windows_box.current(1)
        rows.reverse();app.refresh_windows()
        assert app.chosen_window()['pid']==21
        rows[0]={**rows[0],'pid':22} # HWND reused by a different process.
        app.refresh_windows();assert app.windows_box.current()==-1

def case_manual_input_validation_does_not_create_engine_or_request(root,patch):
    with hidden_app(root,patch,settings={'max_input_chars':64}) as app:
        engine=Mock(side_effect=AssertionError('Must reject before engine/network'))
        patch.setattr(app,'get_engine',engine)
        app.manual_translate();assert '\u8bf7\u8f93\u5165' in app.status.get()
        app.manual_input.insert('1.0','A'*65);app._update_manual_count()
        assert '\u8bf7\u5206\u6bb5' in app.manual_count.get()
        app.manual_translate();assert '\u8d85\u8fc7 64' in app.status.get()
        app.manual_input.delete('1.0','end');app.manual_input.insert('1.0','Hello')
        app.source.set('\u7b80\u4f53\u4e2d\u6587');app.target.set('\u7b80\u4f53\u4e2d\u6587')
        app.manual_translate();assert '\u4e0d\u80fd\u76f8\u540c' in app.status.get()
        app.source.set('\u82f1\u8bed');app.context.set('x'*16385)
        app.manual_translate();assert '16384' in app.status.get()
        engine.assert_not_called()

def case_manual_stream_retains_one_latest_frame_and_read_only_result(root,patch):
    with hidden_app(root,patch) as app:
        for i in range(10000):app._post_manual('\u8bd1\u6587'+str(i))
        assert app.events.qsize()==1
        app.drain()
        assert app.manual_output.get('1.0','end').strip()=='\u8bd1\u65879999'
        assert str(app.manual_output['state'])=='disabled'
        app.manual_output.insert('end','not actually inserted')
        assert 'not actually inserted' not in app.manual_output.get('1.0','end')
        app._post_manual('a'*70000);app.drain()
        assert len(app.manual_output.get('1.0','end-1c'))==64000
        assert app.events.qsize()==0

def case_manual_busy_input_and_unknown_worker_error(root,patch):
    with hidden_app(root,patch) as app:
        engine=Mock();engine.get_stats.return_value={};engine.explain_local.return_value={'rule':'miss'}
        entered,release=threading.Event(),threading.Event()
        def work(*args,**kwargs):
            entered.set();assert release.wait(4);raise ValueError(KEY)
        engine.translate.side_effect=work
        patch.setattr(app,'get_engine',lambda:engine);patch.setattr(app,'remember_profile',lambda:None)
        app.source.set('\u82f1\u8bed');app.manual_input.insert('1.0','Hello')
        try:
            app.manual_translate();assert entered.wait(1)
            assert str(app.manual_input['state'])=='disabled'
        finally:release.set()
        pump(app,lambda:not app.manual_busy)
        assert KEY not in app.status.get()
        assert '\u64cd\u4f5c\u672a\u5b8c\u6210' in app.status.get()
        assert str(app.manual_input['state'])=='normal'

def case_dictionary_selection_and_preview_are_unambiguous(root,patch):
    with hidden_app(root,patch) as app:
        app.game.set('SyntheticGame')  # Game-specific AI references need a named scope.
        app.source.set('\u82f1\u8bed');app.term_source.set('Start');app.term_target.set('\u5f00\u59cb');app.save_term()
        item=app.term_tree.get_children()[0];app.term_tree.selection_set(item)
        app.term_source.set('');app.term_target.set('');app._load_selected_term()
        assert app.term_source.get()=='Start' and app.term_target.get()=='\u5f00\u59cb'
        dialog=app.open_dictionary_import()
        dialog.receive(('preview',[{'source':'Start','target':'\u5f00\u59cb'}],(*app.term_scope(),True)))
        assert str(dialog.preview_text['state'])=='disabled'
        dialog.preview_text.insert('end','altered')
        assert 'altered' not in dialog.preview_text.get('1.0','end')
        dialog.close()

def case_api_minimum_size_keeps_actions_visible(root,patch):
    with hidden_app(root,patch,key=KEY) as app:
        app.root.attributes('-alpha',0);app.root.geometry('850x720-10000-10000');app.root.deiconify()
        dialog=app.show_api_settings()
        dialog.window.attributes('-alpha',0);dialog.window.geometry('660x700-12000-12000');dialog.window.deiconify()
        dialog.base_url.set('https://another-provider.example.test/v1')
        app.root.update()
        for control in (dialog.save_button,dialog.offline_button,dialog.close_button):
            assert control.winfo_height()>=control.winfo_reqheight()
            assert control.winfo_rooty()+control.winfo_height()<=dialog.window.winfo_rooty()+dialog.window.winfo_height()
        dialog.close()

CASES=[name for name in globals() if name.startswith('case_')]

@pytest.mark.parametrize('case',CASES)
def test_public_release_ui(case):
    process=subprocess.run([sys.executable,'-c','import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',str(Path(__file__).resolve()),case],
        cwd=module.ROOT,capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,process.stdout+process.stderr

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='public-ui-') as folder,pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[-1]](Path(folder),patch)
