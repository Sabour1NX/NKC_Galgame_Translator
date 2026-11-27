# SPDX-License-Identifier: MIT
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json

import pytest
from PIL import Image
from nkc_galgame_translator.api_providers import PRESETS, provider_for
from nkc_galgame_translator.security import SecurityValidationError, validate_api_url
from nkc_galgame_translator.translation import TranslationEngine
from nkc_galgame_translator.vision import ScreenshotRecognizer


@pytest.mark.parametrize('url', ['http://192.168.1.1:1234/v1', 'http://localhost.evil.test:1234',
    'http://127.0.0.1', 'http://[::1]extra:1234/', 'http://localhost:1234/v1?key=x',
    'http://token@localhost:1234', 'http://0.0.0.0:1234'])
def test_local_service_requires_an_explicit_loopback_endpoint(url):
    with pytest.raises(SecurityValidationError):
        validate_api_url(url)


def test_canonical_local_presets():
    assert validate_api_url('http://localhost:11434') == PRESETS['ollama'][0]
    assert validate_api_url('http://[::1]:1234') == 'http://[::1]:1234/v1'
    assert provider_for(PRESETS['local'][0]) == 'local'


@pytest.mark.parametrize('key', ['', 'local-only-test-token'])
def test_local_text_stream_and_image_over_http(tmp_path, key):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, self.headers.get('Authorization'), payload))
            if payload['stream']:
                content_type = 'text/event-stream'
                chunk = {'choices': [{'delta': {'content': '\u8f66\u7ad9\u5728\u5317\u8fb9\u3002'}, 'finish_reason': 'stop'}]}
                body = ('data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n').encode()
            else:
                content_type = 'application/json'
                lines = json.dumps({'lines': [{'text': 'Exit', 'box': [100, 100, 500, 500]}]})
                body = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': lines}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        endpoint = f'http://localhost:{server.server_port}/v1'
        settings = dict(base_url=endpoint, model='fixture/model:latest', api_key=key, max_retries=0)
        engine = TranslationEngine(settings, tmp_path / 'history.db')
        try:
            assert not engine.offline_only
            chunks = []
            result = engine.translate('station', 'en', 'zh-Hans', 'The station is to the north.', chunks.append)
            assert result == '\u8f66\u7ad9\u5728\u5317\u8fb9\u3002' and result in chunks
            rows = ScreenshotRecognizer(engine).recognize_frame(Image.new('RGB', (100, 80)), cancelled=lambda: False)
            assert rows == [dict(text='Exit', x=10, y=8, w=40, h=32)]
        finally:
            engine.close()
            server.shutdown()
            worker.join()
    assert [request[2]['stream'] for request in requests] == [True, False]
    for path, auth, payload in requests:
        assert path == '/v1/chat/completions' and payload['model'] == settings['model']
        assert auth == ('Bearer ' + key if key else None)
        assert 'thinking' not in payload
    assert requests[1][2]['messages'][1]['content'][0]['image_url']['url'].startswith('data:image/png;base64,')
