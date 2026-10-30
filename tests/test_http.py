import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from core import __version__
from core.connectors.http import HttpClient


class _Handler(BaseHTTPRequestHandler):
    """A tiny local API: echoes the request as JSON, serves bytes, and fails on /missing."""

    def _reply(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/missing":
            self._reply(404, b"not found", "text/plain")
        elif self.path == "/file":
            self._reply(200, b"\x00\x01binary", "application/octet-stream")
        else:
            echo = {"path": self.path, "agent": self.headers["User-Agent"], "key": self.headers.get("X-Key")}
            self._reply(200, json.dumps(echo).encode())

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self._reply(200, b"echo:" + body, "text/plain")

    def log_message(self, *args) -> None:  # keep pytest output clean
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_get_json_sends_params_headers_and_the_user_agent(server):
    body = HttpClient().get_json(f"{server}/data", params={"var": ["a", "b"], "n": "1"}, headers={"X-Key": "k"})

    assert body["path"] == "/data?var=a&var=b&n=1"  # a list is a repeated key
    assert body["agent"] == f"mallorca-data-platform/{__version__}"
    assert body["key"] == "k"


def test_get_text_and_bytes(server):
    client = HttpClient()

    assert json.loads(client.get_text(f"{server}/text"))["path"] == "/text"
    assert client.get_bytes(f"{server}/file") == b"\x00\x01binary"


def test_post_text_sends_the_json_body(server):
    assert HttpClient().post_text(f"{server}/search", json={"q": 1}) == 'echo:{"q": 1}'


def test_a_client_error_is_raised_without_retrying(server):
    with pytest.raises(requests.HTTPError, match="404"):
        HttpClient(retries=0).get_text(f"{server}/missing")


def test_retries_cover_server_errors_and_read_only_posts():
    retry = HttpClient(retries=3, backoff=0.5).session.get_adapter("https://example.org").max_retries

    assert retry.total == 3
    assert retry.backoff_factor == 0.5
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.allowed_methods == {"GET", "POST"}
