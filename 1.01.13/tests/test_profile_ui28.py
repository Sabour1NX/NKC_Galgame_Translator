# SPDX-License-Identifier: MIT
import copy
import tkinter as tk
import pytest
from nkc_galgame_translator.profile_ui import ProfileManagerModel, ProfileManagerDialog, profile_values
from nkc_galgame_translator.profile_ui import UI_STRINGS
from nkc_galgame_translator.i18n import translate


class Backend:
    def __init__(self):
        self.rows={};self.deleted=[];self.saved=[];self.busy=False;self.next_id=1

    def get_profile(self,name):return copy.deepcopy(self.rows.get(name))
    def list_profile_details(self):return [self.get_profile(name) for name in sorted(self.rows)]

    def save_profile(self,name,**values):
        if self.busy:raise RuntimeError('busy')
        self.saved.append((name,values))
        old=self.rows.get(name,{'profile_id':self.next_id,'name':name,'game':name})
        if name not in self.rows:self.next_id+=1
        self.rows[name]={**old,**values,'progress':{'completed':4,'active_elapsed_ms':61000,'scopes':2},
                         'bounded_summary':'local reference','latest_translation':'\u4e2d\u6587\u8bd1\u6587','latest_source':'source',
                         'latest_translation_at':1700000000,'updated_at':1700000000,
                         'compression':{'method':'zlib','raw_bytes':100,'compressed_bytes':40}}
        return self.get_profile(name)

    def delete_profile(self,name):
        if self.busy:raise RuntimeError('busy')
        self.deleted.append(name);return self.rows.pop(name,None) is not None


@pytest.fixture
def backend():
    result=Backend()
    for name,source in [('A','ja'),('B','en')]:result.save_profile(name,notes=name+' notes',source_lang=source,target_lang='zh-Hans')
    return result


def test_save_preserves_explicit_language_pair_and_notes(backend):
    model=ProfileManagerModel(backend);model.new()
    result=model.save({'name':' New ','source_lang':'zh-Hans','target_lang':'en','notes':'Chinese source game'})
    assert result['name']=='New' and result['source_lang']=='zh-Hans' and result['target_lang']=='en'
    assert result['notes']=='Chinese source game'


@pytest.mark.parametrize('name,notes,message',[('', '', '\u6863\u6848\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a'),('new','x'*16385,'\u5907\u6ce8\u6700\u591a16384\u5b57'),('A','overwritten','\u6863\u6848\u540d\u79f0\u5df2\u5b58\u5728')])
def test_invalid_new_profile_never_overwrites_backend(backend,name,notes,message):
    model=ProfileManagerModel(backend);before=copy.deepcopy(backend.rows)
    with pytest.raises(ValueError,match=message):model.save({'name':name,'source_lang':'en','target_lang':'ja','notes':notes})
    assert backend.rows==before


def test_existing_name_cannot_silently_copy_or_rename_history(backend):
    model=ProfileManagerModel(backend);model.select('A')
    with pytest.raises(ValueError,match='\u4e0d\u53ef\u4fee\u6539'):model.save({'name':'C','source_lang':'en','target_lang':'ja','notes':''})
    assert 'C' not in backend.rows


def test_delete_requires_second_action_and_is_selection_bound(backend):
    model=ProfileManagerModel(backend);model.select('A');model.arm_delete()
    assert backend.deleted==[]
    model.select('B')
    with pytest.raises(ValueError):model.confirm_delete()
    assert backend.deleted==[]
    model.arm_delete();assert model.confirm_delete()
    assert backend.deleted==['B'] and 'A' in backend.rows


def test_delete_rejects_replaced_profile_and_busy_keeps_current(backend):
    model=ProfileManagerModel(backend);model.select('A');model.arm_delete()
    backend.rows['A']['profile_id']=99
    with pytest.raises(ValueError,match='\u4e0d\u5b58\u5728'):model.confirm_delete()
    assert not backend.deleted
    model.select('A');model.arm_delete();backend.busy=True
    with pytest.raises(RuntimeError,match='busy'):model.confirm_delete()
    assert model.selected['name']=='A' and 'A' in backend.rows


@pytest.fixture
def root():
    try:
        instance=tk.Tk();instance.withdraw()
    except tk.TclError as error:
        pytest.skip('Tk desktop unavailable: '+str(error))
    yield instance
    instance.destroy()


def test_hidden_dialog_details_existing_name_and_inline_delete(root,backend):
    dialog=ProfileManagerDialog(root,backend,initial={'name':'A'},show=False)
    root.update_idletasks()
    assert str(dialog.state())=='withdrawn'
    assert dialog.name_entry.instate(['readonly'])
    assert '\u4e2d\u6587\u8bd1\u6587' in dialog.latest_translation.get('1.0','end')
    assert '00:01:01' in dialog.progress.get()
    dialog.request_delete()
    assert backend.deleted==[] and dialog.model.delete_target[0]=='A'
    dialog.cancel_delete();assert dialog.model.delete_target is None
    dialog.request_delete();dialog.request_delete()
    assert backend.deleted==['A'] and dialog.model.selected is None
    dialog.close()


def test_drafts_survive_selection_and_resume_saves_then_returns_scope(root,backend):
    resumed=[]
    dialog=ProfileManagerDialog(root,backend,initial={'name':'A'},on_resume=lambda record:resumed.append(record),show=False)
    dialog.notes.delete('1.0','end');dialog.notes.insert('1.0','new saved notes')
    dialog._select('B');dialog._select('A')
    assert dialog.notes.get('1.0','end-1c')=='new saved notes'
    dialog.resume_selected()
    assert resumed[0]['source_lang']=='ja' and resumed[0]['target_lang']=='zh-Hans'
    assert resumed[0]['notes']=='new saved notes'
    assert backend.rows['A']['notes']=='new saved notes'


def test_resume_rejection_keeps_dialog_and_notes_errors_inline(root,backend):
    dialog=ProfileManagerDialog(root,backend,initial={'name':'A'},on_resume=lambda _:False,show=False)
    dialog.resume_selected();assert dialog.winfo_exists()
    assert '\u505c\u6b62\u7ffb\u8bd1' in dialog.status.get()
    dialog.notes.delete('1.0','end');dialog.notes.insert('1.0','x'*16385)
    assert dialog.save_selected() is None
    assert '16384' in dialog.status.get() and backend.rows['A']['notes']=='A notes'
    dialog.close()


def test_new_profile_saves_and_unknown_stored_language_is_not_rewritten(root,backend):
    backend.rows['A']['source_lang']='ru'
    dialog=ProfileManagerDialog(root,backend,initial={'name':'A'},show=False)
    assert dialog._values()['source_lang']=='ru'
    dialog.new_profile();dialog.name.set('C')
    dialog.notes.insert('1.0','new context')
    saved=dialog.save_selected()
    assert saved['name']=='C' and 'new context' in saved['notes']
    assert dialog.name_entry.instate(['readonly'])
    dialog.close()


def test_change_callback_is_no_argument_and_refresh_keeps_fresh_saved_fields(root,backend):
    changes=[]
    dialog=ProfileManagerDialog(root,backend,initial={'name':'A'},on_changed=lambda:changes.append(True),show=False)
    backend.rows['A']['notes']='externally refreshed'
    dialog.refresh();assert dialog.notes.get('1.0','end-1c')=='externally refreshed'
    dialog.notes.insert('end',' edited');dialog.save_selected()
    assert changes==[True]
    dialog.request_delete();dialog.request_delete()
    assert changes==[True,True]
    dialog.close()


@pytest.mark.parametrize('language',['zh-CN','en','ja'])
def test_localized_dialog_keeps_internal_language_codes(root,backend,language):
    dialog=ProfileManagerDialog(root,backend,tr=lambda text:translate(text,language),initial={'name':'A'},show=False)
    assert dialog.title()==translate('\u8bed\u5883\u6863\u6848\u7ba1\u7406',language)
    assert dialog._values()['source_lang']=='ja'
    assert dialog._values()['target_lang']=='zh-Hans'
    # Existing app localization may replace displayed selector values. The
    # selected index continues to identify a language, never a localized code.
    for box in (dialog.source_box,dialog.target_box):
        current=box.current();box.configure(values=tuple(translate(str(v),'en') for v in box.cget('values')));box.current(current)
    assert dialog._values()['source_lang']=='ja'
    dialog.close()


def test_profile_ui_strings_have_english_and_japanese_translations():
    for value in UI_STRINGS:
        assert translate(value,'en')!=value,value
        assert translate(value,'ja')!=value,value


def test_dialog_uses_real_backend_scope_progress_and_persists(root,tmp_path):
    from nkc_galgame_translator.translation import TranslationEngine
    import httpx
    client=httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('UI must not call an API')))
    engine=TranslationEngine({'api_key':''},tmp_path/'book.sqlite3',client=client)
    try:
        engine.save_profile('Real',source_lang='zh-Hans',target_lang='en',notes='original note')
        dialog=ProfileManagerDialog(root,engine,initial={'name':'Real'},show=False)
        assert '\u8bed\u5883\u8303\u56f4: 0' in dialog.progress.get()
        dialog.notes.delete('1.0','end');dialog.notes.insert('1.0','saved note')
        dialog.save_selected();assert engine.get_profile('Real')['notes']=='saved note'
        dialog.close()
    finally:engine.close();client.close()
