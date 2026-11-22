import json
from pathlib import Path

from nkc_galgame_translator.diagnostics import startup_record, write_startup_report


def test_secret_exception_chain_and_locals_never_enter_report(tmp_path):
    secret = 'sk-' + 'example-secret-' * 5
    try:
        try:
            raise ValueError(secret)
        except ValueError as cause:
            raise RuntimeError('Provider replied with private story: ' + secret) from cause
    except RuntimeError as error:
        path = write_startup_report(tmp_path, error)
    text = path.read_text(encoding='utf-8')
    assert secret not in text and 'private story' not in text and str(tmp_path) not in text
    assert len(text.encode('utf-8')) < 16000
    record = json.loads(text)
    assert record['error_type'] == 'RuntimeError'
    assert record['frames'][-1]['file'] == 'test_diagnostics.py'
    assert not list(tmp_path.glob('.startup-*'))


def test_unwritable_or_absent_log_parent_is_nonfatal(tmp_path):
    assert write_startup_report(tmp_path/'missing', ValueError('private value')) is None


def test_deep_traceback_is_bounded():
    def recurse(depth):
        if depth: return recurse(depth-1)
        raise ValueError('hidden text')
    try:
        recurse(40)
    except ValueError as error:
        record = startup_record(error)
    assert len(record['frames']) == 8
    assert 'hidden text' not in json.dumps(record)
