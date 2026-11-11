import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from core import __version__
from core.connectors import ConnectorError, SourceNotUpdatedError, failure_action, is_outage, is_permanent
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


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


@pytest.mark.parametrize(
    ("exc", "permanent"),
    [
        (SourceNotUpdatedError("EEA files end before the window"), True),
        (_http_error(404), True),  # a moved URL: SOCIB's /ncss/ in November 2026
        (_http_error(403), True),
        (_http_error(429), False),  # rate limit: a later try may pass
        (_http_error(408), False),
        (_http_error(503), False),
        (requests.ConnectionError("connection refused"), False),
        (ConnectorError("no file of the configured stations"), False),
    ],
)
def test_only_failures_that_waiting_will_not_fix_are_permanent(exc, permanent):
    assert is_permanent(exc) is permanent


@pytest.mark.parametrize(
    ("exc", "outage"),
    [
        (requests.ConnectionError("connection refused"), True),
        (requests.ConnectTimeout("connect timeout"), True),
        (requests.ReadTimeout("read timeout"), True),
        (requests.exceptions.RetryError("too many 500 error responses"), True),  # Dataestur, November 2026
        (_http_error(503), True),
        (SourceNotUpdatedError("EEA files end before the window"), True),
        (_http_error(404), False),  # a moved URL is ours to fix
        (_http_error(429), False),
        (ConnectorError("no file of the configured stations"), False),
        (KeyError("fecha"), False),  # a format the parser does not know
    ],
)
def test_an_outage_is_the_source_being_down_not_our_code(exc, outage):
    assert is_outage(exc) is outage


@pytest.mark.parametrize(
    ("exc", "retries_left", "action"),
    [
        (_http_error(503), True, "retry"),  # a short outage may clear before the next try
        (_http_error(503), False, "skip"),  # still down after the retries: skipped, not failed
        (SourceNotUpdatedError("not published yet"), True, "skip"),  # waiting minutes will not publish it
        (_http_error(404), True, "fail"),  # ours, and retrying will not fix it
        (KeyError("fecha"), True, "retry"),  # unknown: the scheduler retries and then fails it
        (KeyError("fecha"), False, "retry"),
    ],
)
def test_a_source_still_down_after_its_retries_is_skipped(exc, retries_left, action):
    assert failure_action(exc, retries_left=retries_left) == action
