# SPDX-License-Identifier: MIT
import http.client
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
import runpy
import sys

import pytest

from nkc_galgame_translator.welcome import WelcomeSession

ROOT = Path(__file__).resolve().parents[1]


def test_only_session_finish_notifies_launcher():
    session = WelcomeSession(ROOT)
    try:
        url = urlsplit(session.base)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
        finish = url.path.rsplit("docs/", 1)[0] + "finish"
        for name in ["Greeting_cn.html", "Greeting.en.html", "Greeting.ja.html", "tour.js", "tour.css"]:
            connection.request("GET", url.path + name)
            result = connection.getresponse()
            content = result.read()
            assert result.status == 200 and content
            if name.endswith(".html"):
                assert content.count(b'class="slide') == 5
                assert content.split(b'<section class="slide', 2)[2].startswith(b' pain-points"')
        connection.request("GET", url.path.replace("docs/", "assets/fonts/") + "SourceHanSansSC-Medium.otf")
        result = connection.getresponse()
        assert result.status == 200 and result.read(4) == b"OTTO"
        result.read()
        headers = {"Origin": "http://" + url.netloc, "X-Tour-Action": "finish"}
        for method, endpoint, request_headers in [
            ("GET", finish, {}), ("POST", "/finish", headers), ("POST", finish, {}),
            ("POST", finish, {**headers, "Origin": "http://localhost:1"})
        ]:
            connection.request(method, endpoint, headers=request_headers)
            response = connection.getresponse()
            assert response.status >= 400
            response.read()
            assert not session.finished.is_set()
        connection.request("POST", finish, headers=headers)
        assert connection.getresponse().status == 204
        assert session.finished.wait(1)
        connection.close()
    finally:
        session.close()


@pytest.mark.parametrize("completed", [False, True])
def test_main_starts_only_after_tour(completed):
    start_app = Mock()
    with patch.object(sys, "argv", ["main.py", "--welcome", "ja"]), \
         patch("nkc_galgame_translator.welcome.show_before_start", return_value=completed) as show, \
         patch("nkc_galgame_translator.app.main", start_app):
        runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
    show.assert_called_once_with(ROOT, "ja")
    assert start_app.call_count == int(completed)

