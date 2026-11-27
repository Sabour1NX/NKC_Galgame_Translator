# SPDX-License-Identifier: MIT
"""Serve the offline tour and receive one completion from its browser tab."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from threading import Event, Thread
import shutil
import webbrowser

PAGES = {"zh-CN": "Greeting_cn.html", "en": "Greeting.en.html", "ja": "Greeting.ja.html"}
FILES = {**{"docs/" + name: "text/html; charset=utf-8" for name in PAGES.values()},
         "docs/tour.css": "text/css", "docs/tour.js": "application/javascript",
         "assets/fonts/SourceHanSansSC-Regular.otf": "font/otf",
         "assets/fonts/SourceHanSansSC-Medium.otf": "font/otf"}


def _start_session(root, finished, prefix):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            name = self.path.removeprefix(prefix)
            if self.headers.get("Host") != authority or not self.path.startswith(prefix) or name not in FILES:
                self.send_error(404)
                return
            try:
                file = (root / name).open("rb")
            except OSError:
                self.send_error(404)
                return
            with file:
                self.send_response(200)
                self.send_header("Content-Type", FILES[name])
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Length", str((root / name).stat().st_size))
                self.end_headers()
                try:
                    shutil.copyfileobj(file, self.wfile)
                except (ConnectionError, TimeoutError):
                    pass

        def do_POST(self):
            if (self.path != prefix + "finish" or self.headers.get("Host") != authority
                    or self.headers.get("Origin") != "http://" + authority
                    or self.headers.get("X-Tour-Action") != "finish"):
                self.send_error(403)
                return
            self.send_response(204)
            self.end_headers()
            finished.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    authority = f"127.0.0.1:{server.server_port}"
    return server, f"http://{authority}{prefix}docs/"


class WelcomeSession:
    def __init__(self, root: Path):
        self.finished = Event()
        self.server, self.base = _start_session(root, self.finished, "/" + token_urlsafe(24) + "/")
        self.worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.worker.start()

    def open(self, language: str, opener=webbrowser.open):
        if not opener(self.base + PAGES.get(language, PAGES["en"])):
            raise OSError("Could not open the welcome tour.")

    def close(self):
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()


def show_before_start(root: Path, language: str) -> bool:
    session = WelcomeSession(root)
    try:
        session.open(language)
        return session.finished.wait(3600)
    finally:
        session.close()
