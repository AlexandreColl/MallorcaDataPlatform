"""Bronze round-trip with in-memory fakes: no network, no MinIO, no Postgres."""

import io
import json
from datetime import date
from pathlib import Path

import pytest

import core.pipeline
from core.connectors import registry
from core.models import Location, Region, TimeWindow
from core.pipeline import (
    NoObservationsError,
    _load_observations,
    bronze_to_silver,
    extract_to_bronze,
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
