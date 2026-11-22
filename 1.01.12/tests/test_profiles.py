# SPDX-License-Identifier: MIT
"""Optional profile persistence and isolation with real SQLite, never real HTTP."""
import json
import sqlite3

import httpx
import pytest

from nkc_galgame_translator.translation import (
    LocalTranslationMiss, TranslationCancelled, TranslationEngine, TranslationError,
)


@pytest.fixture
def offline(tmp_path, monkeypatch):
    def no_client(*args, **kwargs):
        pytest.fail('Profile operations must not construct an HTTP client')
    monkeypatch.setattr(httpx, 'Client', no_client)
    with TranslationEngine({}, tmp_path / 'book.sqlite3') as engine:
        yield engine


def test_blank_profile_normalizes_and_stays_isolated(offline):
    offline.set_term(' \t\n', 'en', 'zh-Hans', 'Start', '\u5f00\u59cb')
    offline.set_term('Mansion', 'en', 'zh-Hans', 'Start', '\u8fdb\u5165\u5b85\u90b8')
    offline.set_term('\u901a\u7528', 'en', 'zh-Hans', 'Start', '\u53e6\u4e00\u4e2a\u6863\u6848')
    assert offline.list_terms('', 'en', 'zh-Hans')[0]['target'] == '\u5f00\u59cb'
    assert offline.list_terms(' \r\n', 'en', 'zh-Hans')[0]['target'] == '\u5f00\u59cb'
    assert offline.list_terms('Mansion', 'en', 'zh-Hans')[0]['target'] == '\u8fdb\u5165\u5b85\u90b8'
    assert offline.list_terms('\u901a\u7528', 'en', 'zh-Hans')[0]['target'] == '\u53e6\u4e00\u4e2a\u6863\u6848'
    assert offline.list_terms('', 'en', 'ja') == []
    assert offline.list_terms('Other', 'en', 'zh-Hans') == []
    with pytest.raises(TranslationError):
        offline.translate('Other', 'en', 'zh-Hans', 'Start')
    assert offline.delete_term(' \t', 'en', 'zh-Hans', 'Start')
    assert offline.list_terms('Mansion', 'en', 'zh-Hans')[0]['target'] == '\u8fdb\u5165\u5b85\u90b8'
    assert offline.get_stats()['session_requests'] == 0


@pytest.mark.parametrize('game,source,target', [
    ('', '', 'zh-Hans'), ('', 'en', ' '), ('', 'x' * 257, 'zh-Hans'),
    ('', 'en', 'x' * 257), ('x' * 257, 'en', 'zh-Hans'),
])
def test_optional_profile_does_not_relax_language_or_length_limits(offline, game, source, target):
    with pytest.raises(TranslationError):
        offline.list_terms(game, source, target)


def test_profile_registry_normalizes_persists_and_does_not_change_terms(tmp_path, offline):
    offline.set_term('Mansion', 'en', 'zh-Hans', 'Start', '\u5f00\u59cb')
    before = offline.get_stats()
    with sqlite3.connect(tmp_path / 'book.sqlite3') as db:
        revisions = db.execute('SELECT * FROM revisions').fetchall()
    offline.remember_profile('  Z Game  ')
    offline.remember_profile('Cafe\u0301')
    offline.remember_profile('Café')
    offline.remember_profile('')
    offline.remember_profile(' \t\n')
    offline.remember_profile('A Game')
    with pytest.raises(TranslationError, match='256'):
        offline.remember_profile('x' * 257)
    assert offline.list_profiles() == ['A Game', 'Café', 'Mansion', 'Z Game']
    assert offline.get_stats() == before
    with sqlite3.connect(tmp_path / 'book.sqlite3') as db:
        assert db.execute('SELECT * FROM revisions').fetchall() == revisions
        assert db.execute('SELECT COUNT(*) FROM translations').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM game_profiles').fetchone()[0] == 3
    offline.close()
    with TranslationEngine({}, tmp_path / 'book.sqlite3') as reopened:
        assert reopened.list_profiles() == ['A Game', 'Café', 'Mansion', 'Z Game']
        assert reopened.list_terms('Mansion', 'en', 'zh-Hans')[0]['target'] == '\u5f00\u59cb'


def test_profile_list_discovers_old_tables_without_rewriting_rows(tmp_path, offline):
    # Remove only the new registry to represent a database from 0.01.06. Each
    # previous table contributes a distinct profile, plus duplicate/blank names.
    offline.close()
    path = tmp_path / 'book.sqlite3'
    statements = [
        ("INSERT INTO glossary VALUES(?,?,?,?,?)", ('Terms', 'en', 'ja', 'Start', '\u958b\u59cb')),
        ("INSERT INTO glossary VALUES(?,?,?,?,?)", ('', 'en', 'ja', 'Start', '\u958b\u59cb')),
        ("INSERT INTO translations VALUES(?,?,?,?,?,?,?,?)", ('legacy', 'Cache', 'en', 'ja', 'Hello', '\u3053\u3093\u306b\u3061\u306f', 'old', 1)),
        ("INSERT INTO revisions VALUES(?,?,?,?)", ('Revisions', 'en', 'ja', 4)),
        ("INSERT INTO auto_terms VALUES(?,?,?,?,?)", ('Learned', 'en', 'ja', 'Start', 1)),
        ("INSERT INTO auto_terms VALUES(?,?,?,?,?)", ('Terms', 'en', 'ja', 'Start', 1)),
    ]
    tables = ('glossary', 'translations', 'revisions', 'auto_terms')
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE game_profiles')
        for statement, values in statements:
            db.execute(statement, values)
        before = {table: db.execute(f'SELECT * FROM {table}').fetchall() for table in tables}
    with TranslationEngine({}, path) as reopened:
        assert reopened.list_profiles() == ['Cache', 'Learned', 'Revisions', 'Terms']
        reopened.remember_profile('Fresh')
        assert reopened.list_profiles() == ['Cache', 'Fresh', 'Learned', 'Revisions', 'Terms']
    with sqlite3.connect(path) as db:
        assert {table: db.execute(f'SELECT * FROM {table}').fetchall() for table in tables} == before


def test_closed_profile_operations_raise_cancelled(offline):
    offline.close()
    with pytest.raises(TranslationCancelled):
        offline.list_profiles()
    for profile in ('', ' \t', 'Mansion'):
        with pytest.raises(TranslationCancelled):
            offline.remember_profile(profile)


def test_blank_profile_archive_remains_browsable_in_its_own_scope(tmp_path):
    # Simulate AI calls, then reopen for browsing with no API configuration.
    calls = []
    def handler(request):
        calls.append(request)
        events = [
            {'choices': [{'delta': {'content': '\u6b22\u8fce\u56de\u5bb6\u3002'}, 'finish_reason': None}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
        ]
        data = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events) + 'data: [DONE]\n\n'
        return httpx.Response(200, text=data, headers={'Content-Type': 'text/event-stream'})
    path = tmp_path / 'book.sqlite3'
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with TranslationEngine({'api_key': 'test-only', 'auto_promote_short_terms': False}, path, client=client) as engine:
            assert engine.translate('  ', 'en', 'zh-Hans', 'Welcome home.') == '\u6b22\u8fce\u56de\u5bb6\u3002'
            assert engine.translate('', 'en', 'zh-Hans', 'Welcome home.') == '\u6b22\u8fce\u56de\u5bb6\u3002'
            assert len(calls) == 2
    with TranslationEngine({}, path) as engine:
        assert engine.list_translation_history('', 'en', 'zh-Hans')[0]['translation'] == '\u6b22\u8fce\u56de\u5bb6\u3002'
        with pytest.raises(TranslationError):
            engine.translate('Mansion', 'en', 'zh-Hans', 'Welcome home.')
        assert engine.list_profiles() == []
        assert engine.get_stats()['session_requests'] == 0
