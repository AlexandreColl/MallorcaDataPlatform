"""Record a connector's real API responses as test fixtures, and replay them without a network.

``make record-fixtures CONNECTOR=x`` runs the connector's ``extract`` for a short recent window through a
`Recorder`, which saves every response under ``connectors/x/tests/fixtures/`` and writes ``recorded.json``: the
window, the region and, for each request, its method, URL, parameters and file. The tests replay them with
`RecordedHttp`, which answers the same requests from those files and fails on any other, so a change in what the
connector asks for shows up as a test failure instead of a silent call to the network.

Connectors written before this keep their hand-picked fixtures; only ``recorded.json`` and the files it lists are
ever replaced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from core.config import load_region
from core.connectors import registry
from core.connectors.base import ConnectorError
from core.connectors.http import HttpClient
from core.models import TimeWindow

if TYPE_CHECKING:
    from pathlib import Path

    from core.connectors.http import JsonGetter, JsonValue, Params

MANIFEST = "recorded.json"
_EXTENSIONS = {"get_json": "json", "get_text": "txt", "get_bytes": "bin", "post_text": "txt"}
_SLUG = re.compile(r"[^a-z0-9]+")


def _canonical(params: Params | JsonValue | None) -> object:
    """Parameters in a fixed order, so the same request always matches its recording."""
    return json.loads(json.dumps(params or {}, sort_keys=True, default=str))


@dataclass(frozen=True)
class Recording:
    """One recorded request and the file with its response."""

    method: str
    url: str
    params: object  # as _canonical left them
    file: str

    def matches(self, method: str, url: str, params: Params | JsonValue | None) -> bool:
        """Same method, URL and parameters."""
        return (self.method, self.url, self.params) == (method, url, _canonical(params))


@dataclass
class Manifest:
    """``recorded.json``: what was recorded, when and for which window and region."""

    connector: str
    region: str
    window: TimeWindow
    recordings: list[Recording] = field(default_factory=list)

    @classmethod
    def load(cls, fixtures: Path) -> Manifest:
        """Read ``fixtures/recorded.json``.

        Raises:
            ConnectorError: when there is none yet.
        """
        path = fixtures / MANIFEST
        if not path.exists():
            msg = f"no recorded responses in {fixtures}: run `make record-fixtures CONNECTOR=<name>` first"
            raise ConnectorError(msg)
        data = json.loads(path.read_text(encoding="utf-8"))
        window = TimeWindow(date.fromisoformat(data["window"]["start"]), date.fromisoformat(data["window"]["end"]))
        return cls(data["connector"], data["region"], window, [Recording(**r) for r in data["requests"]])

    def save(self, fixtures: Path) -> None:
        """Write ``fixtures/recorded.json``."""
        data = {
            "connector": self.connector,
            "region": self.region,
            "window": {"start": self.window.start.isoformat(), "end": self.window.end.isoformat()},
            "requests": [r.__dict__ for r in self.recordings],
        }
        (fixtures / MANIFEST).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Recorder:
    """Passes every request to the real client and saves its response as a fixture.

    A response larger than ``max_bytes`` stops the recording: fixtures live in git, so a 7 MB GTFS file should be
    cut down by hand (or the window shortened) rather than committed by accident.
    """

    def __init__(self, http: JsonGetter, fixtures: Path, *, max_bytes: int = 2_000_000) -> None:
        self.http = http
        self.fixtures = fixtures
        self.max_bytes = max_bytes
        self.recordings: list[Recording] = []

    def _save(self, method: str, url: str, params: Params | JsonValue | None, body: bytes) -> None:
        if len(body) > self.max_bytes:
            msg = f"{url} answered {len(body):,} bytes, more than {self.max_bytes:,}: shorten the window or trim it"
            raise ConnectorError(msg)
        stem = _SLUG.sub("_", url.rstrip("/").rsplit("/", 1)[-1].lower()).strip("_") or "response"
        name = f"{len(self.recordings) + 1:02d}_{stem[:40]}.{_EXTENSIONS[method]}"
        (self.fixtures / name).write_bytes(body)
        self.recordings.append(Recording(method, url, _canonical(params), name))

    def get_json(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> JsonValue:
        """GET JSON and record it, indented so a diff of a re-recording is readable."""
        body = self.http.get_json(url, params=params, headers=headers)
        self._save("get_json", url, params, (json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode())
        return body

    def get_text(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> str:
        """GET text (CSV, XML...) and record it."""
        body = self.http.get_text(url, params=params, headers=headers)
        self._save("get_text", url, params, body.encode())
        return body

    def get_bytes(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> bytes:
        """GET a binary body (zip, Parquet...) and record it."""
        body = self.http.get_bytes(url, params=params, headers=headers)
        self._save("get_bytes", url, params, body)
        return body

    def post_text(self, url: str, json: JsonValue, headers: dict[str, str] | None = None) -> str:
        """POST a query and record its answer (the JSON body is matched like parameters)."""
        body = self.http.post_text(url, json=json, headers=headers)
        self._save("post_text", url, json, body.encode())
        return body


class RecordedHttp:
    """Answers the requests of ``recorded.json`` from their files; any other request fails."""

    def __init__(self, fixtures: Path) -> None:
        self.fixtures = fixtures
        self.manifest = Manifest.load(fixtures)

    def _file(self, method: str, url: str, params: Params | JsonValue | None) -> Path:
        for recording in self.manifest.recordings:
            if recording.matches(method, url, params):
                return self.fixtures / recording.file
        msg = f"no recorded response for {method} {url} {_canonical(params)}: record the fixtures again"
        raise ConnectorError(msg)

    def get_json(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> JsonValue:
        """The recorded JSON of this request (headers carry keys, not the request: they are not matched)."""
        del headers
        return json.loads(self._file("get_json", url, params).read_text(encoding="utf-8"))

    def get_text(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> str:
        """The recorded text of this request."""
        del headers
        return self._file("get_text", url, params).read_text(encoding="utf-8")

    def get_bytes(self, url: str, params: Params | None = None, headers: dict[str, str] | None = None) -> bytes:
        """The recorded body of this request."""
        del headers
        return self._file("get_bytes", url, params).read_bytes()

    def post_text(self, url: str, json: JsonValue, headers: dict[str, str] | None = None) -> str:
        """The recorded answer of this query."""
        del headers
        return self._file("post_text", url, json).read_text(encoding="utf-8")


def record(  # noqa: PLR0913 - keyword-only: the window, the region and where everything lives
    name: str,
    *,
    days: int,
    region_name: str,
    connectors_dir: Path,
    regions_dir: Path,
    http: JsonGetter | None = None,
    max_bytes: int = 2_000_000,
) -> Manifest:
    """Run ``name``'s ``extract`` for its last ``days`` days and keep every response as a fixture.

    Responses are written to a fresh list; the files of the previous recording are removed only once the new one
    has finished, so a failed recording leaves the old fixtures as they were.
    """
    fixtures = connectors_dir / name / "tests" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    previous = Manifest.load(fixtures).recordings if (fixtures / MANIFEST).exists() else []
    staging = fixtures / ".recording"
    staging.mkdir(exist_ok=True)
    recorder = Recorder(http or HttpClient(), staging, max_bytes=max_bytes)
    connector = registry.load(name, http=recorder, connectors_dir=connectors_dir)
    region = load_region(region_name, regions_dir)
    window = connector.config.window(days)
    connector.validate_window(window)
    try:
        connector.extract(window, region)
    except Exception:
        for leftover in staging.iterdir():
            leftover.unlink()
        staging.rmdir()
        raise
    for old in previous:
        (fixtures / old.file).unlink(missing_ok=True)
    for recording in recorder.recordings:
        (staging / recording.file).replace(fixtures / recording.file)
    staging.rmdir()
    manifest = Manifest(name, region.name, window, recorder.recordings)
    manifest.save(fixtures)
    return manifest
