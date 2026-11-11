"""Bronze round-trip with in-memory fakes: no network, no MinIO, no Postgres."""

import io
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import core.pipeline
from core.connectors import registry
from core.models import Location, Region, TimeWindow
from core.pipeline import (
    NoObservationsError,
    _load_observations,
    bronze_to_silver,
    extract_to_bronze,
    recovery_windows,
    remaining_window,
    run_connector,
)
from core.storage import BronzeStore

FIXTURES = Path(__file__).parent.parent / "connectors" / "open_meteo" / "tests" / "fixtures"
REGION = Region(
    "test",
    39.25,
    2.30,
    39.97,
    3.50,
    (Location("palma", 39.5696, 2.6502), Location("inca", 39.7210, 2.9110)),
)
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))


class FakeS3:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803 (boto3 signature)
        self.objects[(Bucket, Key)] = Body
        self.puts += 1

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class RecordedHttp:
    def get_json(self, url, params=None, headers=None):
        name = "air_quality.json" if "air-quality" in url else "weather.json"
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _Settings:
    bronze_bucket = "bronze"


@pytest.fixture
def store():
    return BronzeStore(_Settings(), client=FakeS3())


def test_bronze_roundtrip_and_idempotent_keys(store):
    connector = registry.load("open_meteo", http=RecordedHttp())

    keys_first = extract_to_bronze(connector, WINDOW, REGION, store)
    keys_second = extract_to_bronze(connector, WINDOW, REGION, store)

    assert keys_first == keys_second  # same window -> same objects (overwritten, versioned)
    assert len(store.client.objects) == 2
    normalized = bronze_to_silver(connector, keys_first, REGION, store)
    assert len(normalized.observations) == 2 * 24 * 10
    assert normalized.entities == []  # these test points have no label
    assert normalized.routes == []  # not a transit feed


class EmptyHttp:
    """An FDSN service with no events in the window answers ``204 No Content``."""

    def get_text(self, url, params=None, headers=None):
        return ""


def test_event_source_without_events_lands_bronze_and_loads_nothing(store):
    connector = registry.load("ign", http=EmptyHttp())

    keys, normalized = _load_observations(connector, WINDOW, REGION, store)

    assert len(keys) == 1  # the empty response is kept in bronze
    assert normalized.observations == []


def test_time_series_source_without_data_fails(store, monkeypatch):
    connector = registry.load("open_meteo", http=RecordedHttp())
    monkeypatch.setattr(connector, "normalize", lambda payload, region: [])

    with pytest.raises(NoObservationsError):
        _load_observations(connector, WINDOW, REGION, store)


# --- only_missing: what is left to download of a window ------------------------------------------------------------

WEEK = TimeWindow(date(2026, 11, 2), date(2026, 11, 8))


def test_nothing_left_when_every_day_was_loaded():
    assert remaining_window(WEEK, [], rereads=False) is None
    assert remaining_window(WEEK, [], rereads=True) is None


def test_the_window_starts_at_its_first_missing_day():
    remaining = remaining_window(WEEK, [date(2026, 11, 7), date(2026, 11, 8)], rereads=False)

    assert remaining == TimeWindow(date(2026, 11, 7), date(2026, 11, 8))


def test_a_gap_in_the_middle_is_downloaded_with_what_follows_it():
    remaining = remaining_window(WEEK, [date(2026, 11, 4), date(2026, 11, 8)], rereads=False)

    assert remaining == TimeWindow(date(2026, 11, 4), date(2026, 11, 8))


def test_a_source_that_rereads_for_revisions_keeps_its_whole_window():
    assert remaining_window(WEEK, [date(2026, 11, 8)], rereads=True) == WEEK


class _LoadedWarehouse:
    """A warehouse where every day was already loaded: run_connector must not record a run or call the source."""

    def __init__(self, settings):
        self.calls = []

    def ensure_schema(self):
        pass

    def missing_days(self, source, region, window):
        return []

    def start_run(self, *args):
        pytest.fail("a skipped window records no run")


def test_a_window_already_loaded_is_skipped_without_downloading(monkeypatch):
    monkeypatch.setattr(core.pipeline, "Warehouse", _LoadedWarehouse)
    monkeypatch.setattr(core.pipeline, "BronzeStore", lambda settings: pytest.fail("no download"))

    summary = run_connector("open_meteo", 1, run_id="r1", only_missing=True)

    assert summary.skipped
    assert (summary.payloads, summary.rows_silver) == (0, 0)


# --- recovery of a gap longer than the catch-up ---------------------------------------------------------------------

MONTH = TimeWindow(date(2026, 10, 9), date(2026, 11, 8))  # 31 days, as grown by the catch-up


def test_no_gap_to_recover_when_the_source_never_loaded_or_the_catch_up_reached_it():
    assert recovery_windows(MONTH, None, recover_days=366, chunk_days=31) == []  # its history is a backfill
    assert recovery_windows(MONTH, date(2026, 10, 8), recover_days=366, chunk_days=31) == []


def test_an_older_gap_is_recovered_oldest_first_in_chunks_of_the_catch_up():
    chunks = recovery_windows(MONTH, date(2026, 8, 19), recover_days=366, chunk_days=31)

    assert chunks == [
        TimeWindow(date(2026, 8, 20), date(2026, 9, 19)),
        TimeWindow(date(2026, 9, 20), date(2026, 10, 8)),
    ]


def test_the_recovery_goes_back_no_further_than_recover_days():
    chunks = recovery_windows(MONTH, date(2020, 1, 1), recover_days=60, chunk_days=31)

    assert chunks == [TimeWindow(date(2026, 9, 10), date(2026, 10, 8))]  # 60 days before 8 November


# REData: catch_up_days 92 (its max_days) and recover_days 366.
REDATA_END = registry.discover()["redata"].window(1).end


class _BehindWarehouse:
    """A warehouse whose last successful load is 200 days before the end of the window."""

    def __init__(self, settings):
        self.settings = settings

    def ensure_schema(self):
        pass

    def last_loaded_day(self, source, region):
        return REDATA_END - timedelta(days=200)


def test_run_connector_loads_the_older_gap_first_in_runs_of_its_own(monkeypatch):
    loaded = []

    def load_window(connector, region, window, run_id, warehouse):
        loaded.append((run_id, window))
        return core.pipeline.RunSummary(run_id, connector.name, region.name, str(window.start), str(window.end),
                                        1, 0, 0, 0)  # fmt: skip

    monkeypatch.setattr(core.pipeline, "Warehouse", _BehindWarehouse)
    monkeypatch.setattr(core.pipeline, "_load_window", load_window)

    summary = run_connector("redata", 1, run_id="r1")

    (first_id, first), (second_id, second), (main_id, main) = loaded
    assert main_id == "r1"
    assert main.n_days == 92
    assert (first.n_days, second.n_days) == (92, 16)  # the other 108 days of the gap, oldest first
    assert first.start == REDATA_END - timedelta(days=199)
    assert second.end == main.start - timedelta(days=1)
    assert (first_id, second_id) == (f"r1_{first.start:%Y%m%d}", f"r1_{second.start:%Y%m%d}")
    assert summary.recovered_days == 108


def test_a_failed_recovery_stops_before_the_window(monkeypatch):
    def load_window(connector, region, window, run_id, warehouse):
        msg = "down"
        raise ConnectionError(msg)

    monkeypatch.setattr(core.pipeline, "Warehouse", _BehindWarehouse)
    monkeypatch.setattr(core.pipeline, "_load_window", load_window)

    # The next run resumes from the last successful load, so nothing is skipped.
    with pytest.raises(ConnectionError):
        run_connector("redata", 1, run_id="r1")


# --- a source that is down is recorded apart from a failure of ours -------------------------------------------------


class _RecordingWarehouse:
    def __init__(self, settings=None):
        self.settings = settings
        self.finished = []

    def start_run(self, *args):
        pass

    def finish_run(self, run_id, source, status, **kwargs):
        self.finished.append((source, status, kwargs.get("error", "")))


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (requests.exceptions.RetryError("too many 500 error responses"), "unavailable"),
        (requests.ConnectTimeout("connect timeout"), "unavailable"),
        (KeyError("fecha"), "failed"),
    ],
)
def test_a_run_whose_source_is_down_is_unavailable_not_failed(monkeypatch, error, status):
    def down(connector, window, region, store):
        raise error

    monkeypatch.setattr(core.pipeline, "BronzeStore", lambda settings: SimpleNamespace(ensure=lambda: None))
    monkeypatch.setattr(core.pipeline, "_load_observations", down)
    warehouse = _RecordingWarehouse()
    connector = registry.load("open_meteo")

    with pytest.raises(type(error)):
        core.pipeline._load_window(connector, REGION, WINDOW, "r1", warehouse)

    ((source, recorded, message),) = warehouse.finished
    assert (source, recorded) == ("open_meteo", status)
    assert message.startswith(type(error).__name__)  # the exception type stays readable
