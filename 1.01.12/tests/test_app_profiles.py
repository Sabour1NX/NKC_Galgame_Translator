"""Exercise the real Tk controls with a temporary offline codebook."""
import json
from pathlib import Path
import shutil
import time
import subprocess
import sys
import tempfile
from unittest.mock import Mock

import pytest
import httpx
import nkc_galgame_translator.app as module
from nkc_galgame_translator.agreement import AGREEMENT_VERSION
from nkc_galgame_translator.branding import window_icon_handles


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/example.json').write_text(json.dumps({'api_key':'','offline_only':True,'game':''}),encoding='utf-8')
    (tmp_path/'config/local.json').write_text(json.dumps({
        'agreement_version': AGREEMENT_VERSION,
        'agreement_accepted_at': '2026-11-14T00:00:00+00:00',
    }), encoding='utf-8')
    shutil.copytree(module.ROOT/'assets',tmp_path/'assets')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module,'window_list',lambda:[])
    def no_network(*args, **kwargs):
        pytest.fail('Offline profile tests must not construct an HTTP client')
    monkeypatch.setattr(httpx, 'Client', no_network)
    monkeypatch.setattr(httpx, 'AsyncClient', no_network)
    original=module.tk.Tk
    def hidden_root(*args,**kwargs):
        root=original(*args,**kwargs);root.withdraw();return root
    monkeypatch.setattr(module.tk,'Tk',hidden_root)
    instance=module.App(show_setup=False)
    yield instance
    instance.close()


def case_optional_profile_save_and_existing_dropdown(app,monkeypatch):
    app.source.set('\u82f1\u8bed')
    app.term_source.set('Start');app.term_target.set('\u5f00\u59cb')
    app.term_shared.set(True)  # No profile: use an explicit shared AI reference.
    app.save_term()
    assert app.term_scope()==('','en','zh-Hans')
    assert app.engine.list_shared_terms('en','zh-Hans') == [{'source':'Start','target':'\u5f00\u59cb'}]
    app.term_shared.set(False)
    app.game.set('Game A');app.term_target.set('\u51fa\u53d1');app.save_term()
    app.game.set('Game B');app.term_target.set('\u542f\u7a0b');app.save_term()
    app.refresh_profiles()
    assert tuple(app.profile_box['values'])==('','Game A','Game B')
    app.profile_box.set('Game A');app.profile_box.event_generate('<<ComboboxSelected>>')
    app.refresh_terms()
    assert [app.term_tree.item(i,'values') for i in app.term_tree.get_children()]==[('Start','\u51fa\u53d1')]
    app.clear_profile()
    assert app.game.get()==''
    assert not app.term_tree.get_children()


def case_blank_profile_manual_translation_and_busy_controls(app,monkeypatch):
    app.source.set('\u82f1\u8bed')
    app.get_engine().set_term('','en','zh-Hans','Start','\u5f00\u59cb')
    app.manual_input.insert('1.0','Start')
    app.manual_translate()
    assert str(app.profile_box['state'])=='disabled'
    deadline=time.monotonic()+3
    while app.manual_busy and time.monotonic()<deadline:
        app.root.update();time.sleep(.01)
    assert not app.manual_busy
    assert app.manual_output.get('1.0','end').strip() != '\u5f00\u59cb'
    assert 'API' in app.status.get()
    assert str(app.profile_box['state'])=='normal'
    assert app.engine.get_stats()['session_requests']==0


def case_screen_pipeline_receives_optional_profile_without_validation_error(app,monkeypatch):
    app.core=Mock()
    app.core.languages.return_value=['ja-JP']
    monkeypatch.setattr(app,'chosen_window',lambda:{'hwnd':123,'pid':456})
    monkeypatch.setattr(module,'GameProcess',Mock(return_value=Mock(exited=Mock(return_value=False))))
    pipeline=Mock();pipeline.alive=False
    monkeypatch.setattr(module,'Pipeline',Mock(return_value=pipeline))
    app.game.set('  ')
    app.start()
    pipeline.start.assert_called_once()
    assert pipeline.start.call_args.args[1:4]==('','ja','zh-Hans')
    assert str(app.profile_box['state'])=='disabled'
    app.stop()
    assert str(app.profile_box['state'])=='normal'


def case_real_window_icon_and_plain_start_label(app,monkeypatch):
    assert Path(app.window_icon_path).name=='taiji.ico'
    app.root.update_idletasks()
    assert all(window_icon_handles(app.root).values())
    assert app.start_button['text']=='\u5f00\u59cb\u7ffb\u8bd1'


# Tk owns a process-wide Tcl runtime. Isolate complete App lifecycles instead
# of repeatedly destroying/reinitializing Tcl in a multi-threaded pytest host.
CASES=[name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case',CASES)
def test_app_profile_flow(case):
    process=subprocess.run([sys.executable,'-c',
        'import runpy,sys; runpy.run_path(sys.argv[1],run_name="__main__")',
        str(Path(__file__).resolve()),case],cwd=module.ROOT,
        capture_output=True,text=True,timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,process.stdout+process.stderr


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='profile-ui-') as folder,pytest.MonkeyPatch.context() as patch:
        fixture=app.__wrapped__(Path(folder),patch)
        instance=next(fixture)
        try:globals()[sys.argv[-1]](instance,patch)
        finally:
            try:next(fixture)
            except StopIteration:pass
