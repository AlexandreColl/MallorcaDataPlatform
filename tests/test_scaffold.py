import json
import shutil
import subprocess
from datetime import date, timedelta

import pytest

import connectors
from core.config import PROJECT_ROOT, load_region
from core.connectors import ConnectorConfig, ConnectorError, registry
from core.connectors.recording import MANIFEST, Manifest, RecordedHttp, Recorder, record
from core.connectors.scaffold import class_name, new_connector
from core.models import TimeWindow

REGIONS = PROJECT_ROOT / "config" / "regions"


class FakeApi:
    """A JSON API with one record per hour of the window, for the scaffold's default extractor."""

    def __init__(self, *, size=24, fail=False):
        self.size = size
        self.fail = fail
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        if self.fail:
            msg = "the API is down"
            raise ConnectorError(msg)
        start = params["start"]
        return [
            {"entity": "palma", "ts": f"{start}T{h:02d}:00:00+00:00", "value": h * 10, "lat": 39.57, "lon": 2.65}
            for h in range(self.size)
        ]

    def get_text(self, url, params=None, headers=None):
        return "a,b\n1,2\n"


def _record(folder, *, days=1, api=None):
    return record(
        "demo_source",
        days=days,
        region_name="mallorca",
        connectors_dir=folder,
        regions_dir=REGIONS,
        http=api or FakeApi(),
    )


@pytest.fixture
def scaffolded(tmp_path, monkeypatch):
    """A new connector in a temporary connectors folder, importable as connectors.<name>."""
    folder = tmp_path / "connectors"
    folder.mkdir()
    monkeypatch.setattr(connectors, "__path__", [*connectors.__path__, str(folder)])
    new_connector("demo_source", folder)
    return folder


def test_the_scaffold_is_a_valid_disabled_connector(scaffolded):
    files = sorted(p.relative_to(scaffolded).as_posix() for p in scaffolded.rglob("*") if p.is_file())

    assert files == [
        "demo_source/README.md",
        "demo_source/__init__.py",
        "demo_source/connector.yaml",
        "demo_source/extractor.py",
        "demo_source/tests/fixtures/.gitkeep",
        "demo_source/tests/test_demo_source.py",
    ]
    config = ConnectorConfig.from_yaml(scaffolded / "demo_source" / "connector.yaml")
    assert config.name == "demo_source"
    assert not config.enabled  # out of the DAG's default selection until it works
    assert config.entrypoint == "connectors.demo_source.extractor:DemoSourceConnector"
    assert registry.runnable_names(scaffolded) == []
    compile((scaffolded / "demo_source" / "tests" / "test_demo_source.py").read_text(encoding="utf-8"), "t", "exec")


def test_names_are_checked():
    assert class_name("water_quality") == "WaterQualityConnector"
    with pytest.raises(ConnectorError, match="not a connector name"):
        new_connector("Water-Quality", PROJECT_ROOT / "connectors")
    with pytest.raises(ConnectorError, match="already exists"):
        new_connector("open_meteo", PROJECT_ROOT / "connectors")


@pytest.mark.skipif(shutil.which("ruff") is None, reason="needs ruff")
def test_the_generated_package_passes_the_project_lint(scaffolded):
    package = scaffolded / "demo_source"
    files = [str(package / "__init__.py"), str(package / "extractor.py")]
    command = [shutil.which("ruff") or "ruff", "check", "--no-cache", "--extend-ignore", "EXE002"]
    config = ["--config", str(PROJECT_ROOT / "pyproject.toml")]
    result = subprocess.run([*command, *config, *files], capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stdout


def test_recording_then_replaying_gives_the_same_observations(scaffolded):
    manifest = _record(scaffolded)
    fixtures = scaffolded / "demo_source" / "tests" / "fixtures"

    assert manifest.window.end == manifest.window.start  # one complete day, yesterday
    assert [r.file for r in manifest.recordings] == ["01_values.json"]
    saved = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    assert saved["window"]["start"] == manifest.window.start.isoformat()
    assert saved["requests"][0]["params"] == {"end": saved["window"]["end"], "start": saved["window"]["start"]}

    replayed = registry.load("demo_source", http=RecordedHttp(fixtures), connectors_dir=scaffolded)
    region = load_region("mallorca", REGIONS)
    observations = [o for p in replayed.extract(manifest.window, region) for o in replayed.normalize(p, region)]
    assert len(observations) == 24
    assert {o.metric for o in observations} == {"value"}
    assert observations[3].value == 30.0
    assert observations[0].ts.date() == manifest.window.start


def test_replaying_a_request_that_was_not_recorded_fails(scaffolded):
    _record(scaffolded)
    fixtures = scaffolded / "demo_source" / "tests" / "fixtures"
    replayed = registry.load("demo_source", http=RecordedHttp(fixtures), connectors_dir=scaffolded)
    window = Manifest.load(fixtures).window

    with pytest.raises(ConnectorError, match="no recorded response"):
        replayed.extract(TimeWindow(window.start - timedelta(days=1), window.end), load_region("mallorca", REGIONS))


def test_without_recordings_the_tests_say_what_to_run(tmp_path):
    with pytest.raises(ConnectorError, match="make record-fixtures"):
        RecordedHttp(tmp_path)


def test_a_failed_recording_keeps_the_previous_fixtures(scaffolded):
    _record(scaffolded)
    fixtures = scaffolded / "demo_source" / "tests" / "fixtures"
    before = sorted(p.name for p in fixtures.iterdir())

    with pytest.raises(ConnectorError, match="down"):
        _record(scaffolded, api=FakeApi(fail=True))
    assert sorted(p.name for p in fixtures.iterdir()) == before


def test_a_new_recording_replaces_only_the_files_of_the_previous_one(scaffolded):
    fixtures = scaffolded / "demo_source" / "tests" / "fixtures"
    (fixtures / "hand_picked.json").write_text("[]", encoding="utf-8")
    _record(scaffolded)
    _record(scaffolded, days=2)

    assert sorted(p.name for p in fixtures.iterdir()) == [".gitkeep", "01_values.json", "hand_picked.json", MANIFEST]


def test_a_response_too_large_for_git_stops_the_recording(tmp_path):
    recorder = Recorder(FakeApi(size=1000), tmp_path, max_bytes=1000)
    with pytest.raises(ConnectorError, match="more than 1,000"):
        recorder.get_json("https://example.org/api/values", params={"start": "2026-11-01", "end": "2026-11-01"})


def test_text_responses_are_recorded_as_text(tmp_path):
    recorder = Recorder(FakeApi(), tmp_path)
    recorder.get_text("https://example.org/data.csv", params={"b": "2", "a": "1"})
    Manifest("x", "mallorca", TimeWindow(date(2026, 11, 1), date(2026, 11, 1)), recorder.recordings).save(tmp_path)

    replay = RecordedHttp(tmp_path)
    assert replay.get_text("https://example.org/data.csv", params={"a": "1", "b": "2"}) == "a,b\n1,2\n"  # any order
    assert recorder.recordings[0].file == "01_data_csv.txt"
