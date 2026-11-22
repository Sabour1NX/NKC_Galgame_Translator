# SPDX-License-Identifier: MIT
"""DPAPI endpoint binding, migration and interrupted-commit regressions."""
import json
import pytest
from nkc_galgame_translator.config_store import ConfigStore, ConfigStoreError
from nkc_galgame_translator import config_store as module

KEY='synthetic-private-credential-one'
URL='https://first.example.com/v1'
OTHER='https://second.example.com/v1'


@pytest.fixture
def store(tmp_path):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/example.json').write_text(json.dumps({'base_url':URL,'model':'model'}))
    return ConfigStore(tmp_path)


def test_endpoint_binding_is_encrypted_and_tampering_hides_key(store):
    store.save({},KEY)
    assert URL.encode() not in store.credentials_path.read_bytes()
    payload=store._read_credentials()
    selected=store.load()['credential_id']
    assert payload['endpoints'][selected]==URL
    raw=json.loads(store.config_path.read_text())
    raw['api_slots'][0]['base_url']=OTHER
    raw['base_url']=OTHER
    store.config_path.write_text(json.dumps(raw))
    result=store.load()
    assert result['api_key']=='' and not result['api_slots'][0]['has_api_key']
    assert '\u7ed1\u5b9a' in store.credential_error
    assert store._read_credentials()['keys'][selected]==KEY  # Recoverable, not destroyed.


def test_path_change_also_requires_new_key_and_model_change_does_not(store):
    store.save({},KEY)
    original=store.config_path.read_bytes()
    with pytest.raises(ConfigStoreError):store.save_api_slot(0,URL+'/proxy','model')
    with pytest.raises(ConfigStoreError):store.save({'base_url':OTHER})
    assert store.config_path.read_bytes()==original
    assert store.save_api_slot(0,URL,'other-model')['api_key']==KEY


def test_explicit_key_reentry_binds_new_endpoint(store):
    store.save({},KEY)
    value=store.save_api_slot(0,OTHER,'model',KEY)
    assert value['api_key']==KEY
    assert store._read_credentials()['endpoints'][value['credential_id']]==OTHER


def test_legacy_unbound_cipher_stays_recoverable_but_never_activates(store):
    store.save({},KEY)
    old=store._read_credentials();old.pop('endpoints')
    ciphertext=module._MAGIC+module._dpapi(json.dumps(old).encode(),decrypt=False)
    store.credentials_path.write_bytes(ciphertext)
    assert store.load()['api_key']==''
    assert '\u65e7\u5bc6\u94a5' in store.credential_error
    assert store.save({'game':'Changed profile'})['api_key']==''
    assert store.credentials_path.read_bytes()==ciphertext
    with pytest.raises(ConfigStoreError):store.save_api_slot(0,URL,'model')
    assert store.save_api_slot(0,URL,'model',KEY)['api_key']==KEY


def test_swapping_credential_id_between_different_providers_does_not_expose_key(store):
    store.save_api_slot(0,URL,'model',KEY)
    store.save_api_slot(1,OTHER,'model','synthetic-second-key')
    raw=json.loads(store.config_path.read_text())
    raw['api_slots'][1]['credential_id']=raw['api_slots'][0]['credential_id']
    store.config_path.write_text(json.dumps(raw))
    assert store.load()['api_key']==''


def test_failed_rebind_commit_preserves_original_endpoint_and_key(store,monkeypatch):
    old=store.save({},KEY)
    real=module._atomic_write
    def fail_json(path,content):
        if path==store.config_path:raise OSError('simulated failure')
        return real(path,content)
    monkeypatch.setattr(module,'_atomic_write',fail_json)
    with pytest.raises(ConfigStoreError):
        store.save_api_slot(0,OTHER,'model',allow_key_reuse=True)
    result=store.load()
    assert result['api_key']==KEY and result['base_url']==URL
    assert store._read_credentials()['endpoints'][old['credential_id']]==URL


@pytest.mark.parametrize('bad',['https://localhost','https://api.example.com\nsecret'])
def test_store_rejects_invalid_endpoint_before_writing_key(store,bad):
    with pytest.raises(ConfigStoreError):store.save_api_slot(0,bad,'model',KEY)
    assert not store.config_path.exists() and not store.credentials_path.exists()


def test_deep_json_errors_are_sanitized(store):
    store.config_path.write_text('{"game":'+('['*2000)+'"secret"'+(']'*2000)+'}')
    with pytest.raises(ConfigStoreError) as error:store.load()
    assert 'secret' not in str(error.value)


def test_malformed_stored_metadata_can_recover_offline_without_key_activation(store):
    store.save({}, KEY)
    encrypted = store.credentials_path.read_bytes()
    raw=json.loads(store.config_path.read_text())
    raw['api_slots'][0]['base_url']='https://localhost'
    store.config_path.write_text(json.dumps(raw))
    config=store.load()
    assert config['api_key']=='' and config['base_url']=='https://api.deepseek.com'
    assert '\u505c\u7528' in store.credential_error
    assert store.save({**config,'offline_only':True})['api_key']==''
    assert store.save_api_slot(0,config['base_url'],config['model'],offline_only=True)['api_key']==''
    assert store.credentials_path.read_bytes()==encrypted


def test_duplicate_config_fields_are_rejected(store):
    store.config_path.write_text('{"base_url":"https://first.example.com","base_url":"https://other.example.com"}')
    with pytest.raises(ConfigStoreError):store.load()
