"""Real hidden Tk dictionaries and imports; temporary data, no API/key."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_app_profiles import app as app_fixture
import nkc_galgame_translator.app as module


def rows(app):
    return [app.term_tree.item(item,'values') for item in app.term_tree.get_children()]


def case_empty_profile_requires_shared_or_named_reference(app,patch):
    app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587')
    app.term_source.set('Raven');app.term_target.set('\u4e4c\u9e26')
    app.save_term()
    assert app.get_engine().list_terms('','en','zh-Hans')==[]
    assert '\u901a\u7528\u8bcd\u5178' in app.status.get()
    app.term_shared.set(True);app.save_term()
    assert app.engine.list_shared_terms('en','zh-Hans')==[{'source':'Raven','target':'\u4e4c\u9e26'}]
    assert rows(app)==[('Raven','\u4e4c\u9e26')]


def case_active_profile_and_language_rows_are_exact_and_visible(app,patch):
    engine=app.get_engine()
    engine.set_term('A','en','zh-Hans','Raven','\u9e26')
    engine.set_term('A','ja','zh-Hans','\u7d05\u9b54\u9928','\u7ea2\u9b54\u9986')
    engine.set_term('B','en','zh-Hans','Raven','\u5176\u4ed6\u9e26')
    app.game.set('A');app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.refresh_terms()
    assert rows(app)==[('Raven','\u9e26')]
    assert 'A · en → zh-Hans' in app.term_scope_status.get()
    app.source.set('\u65e5\u8bed');app.refresh_terms()
    assert rows(app)==[('\u7d05\u9b54\u9928','\u7ea2\u9b54\u9986')]
    app.game.set('B');app.refresh_terms()
    assert rows(app)==[]
    assert '\u6b64\u8303\u56f4\u6682\u65e0' in app.term_scope_status.get()
    assert engine.list_terms('A','en','zh-Hans')==[{'source':'Raven','target':'\u9e26'}]


def case_failed_read_keeps_previous_table_and_scope(app,patch):
    engine=app.get_engine();engine.set_term('A','en','zh-Hans','Raven','\u9e26')
    app.game.set('A');app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.refresh_terms()
    before=app.term_scope_status.get()
    def fail(*args):raise OSError('synthetic failure')
    patch.setattr(engine,'list_terms',fail)
    app.refresh_terms()
    assert rows(app)==[('Raven','\u9e26')]
    assert app.term_scope_status.get()==before


def case_stale_table_cannot_delete_from_another_scope(app,patch):
    engine=app.get_engine()
    for game in ('A','B'):engine.set_term(game,'en','zh-Hans','Raven',game)
    app.game.set('A');app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.refresh_terms()
    app.term_tree.selection_set(app.term_tree.get_children()[0])
    app.game.set('B');app.delete_term()
    assert engine.list_terms('A','en','zh-Hans') and engine.list_terms('B','en','zh-Hans')
    assert '\u91cd\u65b0\u9009\u62e9' in app.status.get()
    app.term_tree.selection_set(app.term_tree.get_children()[0]);app.delete_term()
    assert engine.list_terms('A','en','zh-Hans') and not engine.list_terms('B','en','zh-Hans')


def case_import_rechecks_preview_scope_and_unnamed_game(app,patch):
    app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587')
    dialog=app.open_dictionary_import()
    dialog.shared.set(False)
    dialog.entries=[{'source':'Raven','target':'\u9e26'}]
    dialog.preview_scope=('', 'en', 'zh-Hans',False)
    assert dialog.commit() is False
    assert not app.get_engine().list_terms('','en','zh-Hans')
    app.game.set('A')
    assert dialog.commit() is False
    assert '\u91cd\u65b0\u9884\u89c8' in dialog.message.get()
    assert dialog.entries is None
    dialog.close()


CASES=[name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case',CASES)
def test_dictionary_ui(case):
    process=subprocess.run([sys.executable,str(Path(__file__).resolve()),case],cwd=module.ROOT,
                           capture_output=True,text=True,timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,process.stdout+process.stderr


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='dictionary-ui29-') as folder,pytest.MonkeyPatch.context() as patch:
        fixture=app_fixture.__wrapped__(Path(folder),patch);instance=next(fixture)
        try:globals()[sys.argv[-1]](instance,patch)
        finally:
            try:next(fixture)
            except StopIteration:pass
