from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

import httpx
import pytest

from nkc_galgame_translator.translation import TranslationEngine, TranslationError, TranslationCancelled, ProfileBusyError
from nkc_galgame_translator.context_archive import scope_key, decode_event
from nkc_galgame_translator.profile_store import profile_id
from test_translation import sse_response


@pytest.fixture
def create(tmp_path):
    engines=[]
    def make(handler=None,**config):
        requests=[]
        def wrapped(request):
            requests.append(json.loads(request.content))
            return handler(request) if handler else sse_response('translated '+str(len(requests)))
        client=httpx.Client(transport=httpx.MockTransport(wrapped))
        engine=TranslationEngine({'api_key':'synthetic','max_retries':0,**config},tmp_path/'book.sqlite3',client=client)
        engines.append((engine,client));return engine,requests
    yield make
    for engine,client in engines:engine.close();client.close()


def tr(engine,text='First',name='Game',source='en',target='zh-Hans',**kw):
    return engine.translate(name,source,target,text,**kw)


def test_create_edit_reopen_resume_and_notes_prompt(create):
    engine,requests=create()
    profile=engine.save_profile('  Game  ',notes='A spaceship; Alice is the captain.',source_lang='en',target_lang='ja')
    assert profile['name']=='Game' and profile['source_lang']=='en' and len(profile['profile_id'])==64
    tr(engine,context=profile['notes'],target='ja')
    prompt=json.loads(json.loads(requests[-1]['messages'][1]['content'])['context'])
    assert prompt['profile_notes']==profile['notes'] and prompt['user_context']==''
    second,_=create();resumed=second.get_profile('Game')
    assert resumed['notes']==profile['notes'] and resumed['latest_translation']=='translated 1'
    assert resumed['progress']['completed']==1 and resumed['progress']['active_elapsed_ms']>0
    assert resumed['target_lang']=='ja' and resumed['latest_translation_at']
    assert resumed['summary_kind']=='local_recent_excerpts' and 'translated 1' in resumed['bounded_summary']
    engine.save_profile('Game',notes='Updated note')
    assert second.get_profile('Game')['notes']=='Updated note'


def test_additional_context_not_discarded(create):
    engine,requests=create();engine.save_profile('Game',notes='The ship is damaged.')
    tr(engine,context='This line appears in the repair shop.')
    prompt=json.loads(json.loads(requests[0]['messages'][1]['content'])['context'])
    assert prompt['profile_notes']=='The ship is damaged.'
    assert prompt['user_context']=='This line appears in the repair shop.'
    assert 'The ship is damaged.' not in requests[0]['messages'][0]['content']


def test_latest_translation_uses_event_order_when_cache_timestamps_tie(create):
    engine,_=create()
    for text in ['z source','a source','last source']:tr(engine,text)
    with engine._db:engine._db.execute('UPDATE translations SET created_at=1')
    profile=engine.get_profile('Game')
    assert profile['latest_source']=='last source' and profile['latest_translation']=='translated 3'


@pytest.mark.parametrize('field',['source_lang','target_lang'])
def test_explicit_empty_language_is_not_saved(create,field):
    engine,_=create()
    with pytest.raises(TranslationError):engine.save_profile('Game',**{field:''})
    assert engine.get_profile('Game') is None


def test_close_between_request_validation_and_note_read_is_cancellation(create,monkeypatch):
    engine,requests=create();original=engine._warmup_key
    def close_before_note_read(*args):
        result=original(*args);engine.close();return result
    monkeypatch.setattr(engine,'_warmup_key',close_before_note_read)
    with pytest.raises(TranslationCancelled):tr(engine)
    assert requests==[]


def test_legacy_migration_backfills_actual_context_and_counters(create):
    engine,_=create();tr(engine,context='Persist the actual user note.')
    with engine._db:
        engine._db.execute('DELETE FROM profile_details')
        engine._db.execute('DELETE FROM ai_context_scopes')
    reopened,_=create();p=reopened.get_profile('Game')
    assert p['notes']=='Persist the actual user note.'
    assert p['progress']['completed']==1 and p['progress']['scopes'][0]['records']==1
    assert 'bounded_history_excerpts' not in p['notes']


def test_auto_compact_prompt_preserves_every_full_event(create):
    engine,requests=create(context_max_chars=600,context_history_records=2)
    engine.save_profile('Game',notes='NOTE '*250)
    for i in range(8):tr(engine,str(i)+' source '*80)
    assert engine.get_profile('Game')['progress']['completed']==8
    for request in requests:
        record=json.loads(request['messages'][1]['content'])
        if 'context' in record:
            assert len(record['context'])<=600 and 'prompt_context' not in record['context']
        else:
            assert request['messages'][0]['content'].startswith('Summarize the game scene')
            assert len(request['messages'])==2 and set(record['data'])=={'previous_summary','recent_pairs'}
            assert len(record['data']['recent_pairs'])<=6
    rows=engine._db.execute('SELECT payload FROM ai_context_events').fetchall()
    assert len(rows)==8 and decode_event(rows[0][0])['source'].startswith('0 source ')


def test_delete_all_languages_and_owned_state_without_global_or_other_effects(create):
    engine,_=create()
    for source in ['en','ja']:
        tr(engine,'content '+source,source=source)
        engine.set_term('Game',source,'zh-Hans','term','value')
    tr(engine,'other profile',name='Other')
    tr(engine,'unassigned',name='',warmup_scope='exe:A')
    engine.import_terms([{'source':'shared','target':'shared-value'}],'','en','zh-Hans',shared=True)
    before_shared=engine.list_shared_terms('en','zh-Hans');before_other=engine.get_profile('Other')
    directories=[Path(engine.get_context_status('Game',s,'zh-Hans')['directory']) for s in ['en','ja']]
    warmup=hashlib.sha256(json.dumps(['game-warmup-v1','profile:Game'],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    with engine._db:engine._db.execute('INSERT INTO warmup_progress VALUES(?,?,?,4,0)',(warmup,'en','zh-Hans'))
    assert engine.delete_profile('Game')
    assert engine.get_profile('Game') is None and not any(p.exists() for p in directories)
    for table in ['translations','glossary','auto_terms','revisions','term_index_revisions','warmup_legacy_scopes','game_profiles','profile_details','ai_context_scopes']:
        assert engine._db.execute('SELECT count(*) FROM '+table+' WHERE game=?',('Game',)).fetchone()[0]==0
    assert engine._db.execute('SELECT count(*) FROM warmup_progress WHERE scope_key=?',(warmup,)).fetchone()[0]==0
    assert engine.get_profile('Other')==before_other and engine.list_shared_terms('en','zh-Hans')==before_shared
    assert len(engine.list_translation_history('','en','zh-Hans',warmup_scope='exe:A'))==1
    assert not engine.delete_profile('Game')
    with pytest.raises(TranslationError):tr(engine)
    with pytest.raises(TranslationError):engine.set_term('Game','en','zh-Hans','late','stale')
    engine.save_profile('Game',notes='A new session')
    assert engine.get_profile('Game')['progress']['completed']==0


def test_delete_rejected_while_another_engine_has_active_request(create):
    entered=threading.Event();release=threading.Event()
    def handler(request):entered.set();assert release.wait(3);return sse_response('done')
    engine,_=create(handler);other,_=create()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(tr,engine);assert entered.wait(1)
        with pytest.raises(ProfileBusyError):other.delete_profile('Game')
        release.set();assert future.result()=='done'
    assert other.delete_profile('Game') and engine.get_profile('Game') is None


def test_delete_rolls_back_every_sql_table_on_failure(create):
    engine,_=create();tr(engine)
    directory=Path(engine.get_context_status('Game','en','zh-Hans')['directory'])
    with engine._db:engine._db.execute("CREATE TRIGGER deny_delete BEFORE DELETE ON translations BEGIN SELECT RAISE(ABORT,'test rollback'); END")
    with pytest.raises(sqlite3.IntegrityError):engine.delete_profile('Game')
    assert engine.get_profile('Game')['progress']['completed']==1
    assert engine.get_context_status('Game','en','zh-Hans')['records']==1 and (directory/'updated.json').is_file()


@pytest.mark.parametrize('name',['../escape','C:\\Windows\\name','\u4e2d\u6587\u6807\u9898','name:stream'])
def test_names_are_data_and_paths_are_hashed(create,name):
    engine,_=create();engine.save_profile(name,notes='context');tr(engine,name=name)
    directory=Path(engine.get_context_status(name,'en','zh-Hans')['directory'])
    assert len(directory.name)==64 and directory.name.isascii()
    assert directory.parent==engine.context_archive.folder and engine.delete_profile(name)


@pytest.mark.parametrize('name',['', '   ','a\x00b','a\u202eb','x'*257])
def test_invalid_names_cannot_be_saved_or_deleted(create,name):
    engine,_=create()
    with pytest.raises(TranslationError):engine.save_profile(name)
    with pytest.raises(TranslationError):engine.delete_profile(name)


def test_note_and_language_validation_are_atomic(create):
    engine,_=create();before=engine.save_profile('Game',notes='kept')
    for kwargs in [{'notes':'x'*16385},{'notes':'\ud800'},{'source_lang':'!!!'}]:
        with pytest.raises(TranslationError):engine.save_profile('Game',**kwargs)
        assert engine.get_profile('Game')==before


def test_stale_process_lease_can_be_removed(create,monkeypatch):
    engine,_=create();engine.save_profile('Game')
    with engine._db:engine._db.execute('INSERT INTO profile_activity VALUES(?,?,?,?,?,?)',('dead',profile_id('Game'),'other',987654,'old',1))
    monkeypatch.setattr('nkc_galgame_translator.profile_store._process_token',lambda pid:None)
    assert engine.delete_profile('Game')


def test_close_releases_own_leases(create):
    engine,_=create();engine.save_profile('Game')
    with engine._lock:engine.profile_store.begin(('Game','en','zh-Hans'))
    engine.close();reopened,_=create()
    assert reopened.delete_profile('Game')
