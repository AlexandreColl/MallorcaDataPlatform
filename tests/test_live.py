"""Live sources (ADR 0026): the poller, the snapshot keys in bronze and what the daily run may expect of them."""

from datetime import UTC, date, datetime, timedelta

import pytest

import core.pipeline
import core.storage
from core.connectors import ConnectorError, registry
from core.connectors.live import floor_to, instant_of
from core.connectors.recording import Manifest, record
from core.live import live_names, poll_connector, poll_period
from core.models import TimeWindow
from core.pipeline import _from_first_day, run_connector
from core.storage import BronzeStore


def test_bicipalma_is_the_live_source_and_the_poller_runs_every_five_minutes():
    assert live_names() == ["bicipalma"]
    assert poll_period() == timedelta(minutes=5)
    config = registry.discover()["bicipalma"]
    assert config.is_live
    assert config.poll_every("station_information") == timedelta(hours=1)
    assert not registry.discover()["redata"].is_live


def test_a_poll_period_of_a_month_is_refused(tmp_path):
    folder = tmp_path / "slow"
    folder.mkdir()
    (folder / "connector.yaml").write_text(
        "name: slow\nentrypoint: x:Y\ndatasets:\n  feed: {poll_every: 1mo}\n", encoding="utf-8"
    )

    with pytest.raises(ConnectorError, match="poll_every"):
        registry.discover(tmp_path)


def test_instants_round_down_to_their_step_and_come_back_from_the_key():
    at = datetime(2026, 11, 26, 15, 37, 21, tzinfo=UTC)

    assert floor_to(at, timedelta(hours=1)) == datetime(2026, 11, 26, 15, tzinfo=UTC)
    assert floor_to(at, timedelta(minutes=5)) == datetime(2026, 11, 26, 15, 35, tzinfo=UTC)
    assert instant_of("bicipalma/snapshots/station_status/day=2026-11-26/20261126T153721Z.json") == at


def test_only_live_connectors_are_polled():
    with pytest.raises(ConnectorError, match="no polled dataset"):
        poll_connector("redata", store=object())


# --- the daily run of a live source -------------------------------------------------------------------------------


class _Live:
    """A connector whose poller kept its first snapshot on ``first``."""

    name = "live"

    def __init__(self, first):
        self.first = first

    def first_day(self):
        return self.first


WEEK = TimeWindow(date(2026, 11, 20), date(2026, 11, 26))


def test_a_window_starts_on_the_first_snapshot_and_one_before_it_is_skipped():
    assert _from_first_day(_Live(None), WEEK, "r") == WEEK  # a source with a history
    assert _from_first_day(_Live(date(2026, 11, 1)), WEEK, "r") == WEEK
    assert _from_first_day(_Live(date(2026, 11, 24)), WEEK, "r") == TimeWindow(date(2026, 11, 24), WEEK.end)
    assert _from_first_day(_Live(date(2026, 11, 27)), WEEK, "r") is None
    assert _from_first_day(_Live(date.max), WEEK, "r") is None  # never polled


class _EmptyBronze:
    def keys(self, prefix):
        return []

    def folders(self, prefix):
        return []


class _Warehouse:
    def __init__(self, settings):
        pass

    def ensure_schema(self):
        pass

    def start_run(self, *args):
        pytest.fail("a window before the first snapshot records no run")


def test_a_live_source_that_was_never_polled_skips_its_run_without_recording_it(monkeypatch):
    monkeypatch.setattr(core.pipeline, "Warehouse", _Warehouse)
    monkeypatch.setattr(core.storage, "BronzeStore", lambda settings: _EmptyBronze())  # the connector's own bronze

    summary = run_connector("bicipalma", 1, run_id="r1")

    assert summary.skipped
    assert summary.payloads == 0


# --- bronze listing -----------------------------------------------------------------------------------------------


class _Paginator:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def paginate(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.pages)


class _ListingS3:
    def __init__(self, pages):
        self.paginator = _Paginator(pages)

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self.paginator


class _Settings:
    bronze_bucket = "bronze"


def test_bronze_lists_keys_across_pages_and_folders_without_their_objects():
    pages = [
        {"Contents": [{"Key": "b/x/day=2026-11-26/2.json"}], "CommonPrefixes": [{"Prefix": "b/x/day=2026-11-26/"}]},
        {"Contents": [{"Key": "b/x/day=2026-11-25/1.json"}], "CommonPrefixes": [{"Prefix": "b/x/day=2026-11-25/"}]},
    ]
    s3 = _ListingS3(pages)
    store = BronzeStore(_Settings(), client=s3)

    assert store.keys("b/x/") == ["b/x/day=2026-11-25/1.json", "b/x/day=2026-11-26/2.json"]
    assert store.folders("b/x/") == ["b/x/day=2026-11-25/", "b/x/day=2026-11-26/"]
    assert s3.paginator.calls == [
        {"Bucket": "bronze", "Prefix": "b/x/"},
        {"Bucket": "bronze", "Prefix": "b/x/", "Delimiter": "/"},
    ]


# --- fixtures of a live source ------------------------------------------------------------------------------------


class _Feed:
    def get_json(self, url, params=None, headers=None):
        return {"last_updated": 1795708239, "ttl": 60, "data": {"stations": []}}


def test_recording_a_live_source_records_one_poll_of_each_dataset(tmp_path):
    connectors = tmp_path / "connectors"
    (connectors / "bicipalma").mkdir(parents=True)

    yaml = (core.pipeline.Settings.from_env().connectors_dir / "bicipalma" / "connector.yaml").read_text(
        encoding="utf-8"
    )
    (connectors / "bicipalma" / "connector.yaml").write_text(yaml, encoding="utf-8")
    regions = core.pipeline.Settings.from_env().regions_dir

    manifest = record("bicipalma", days=1, region_name="mallorca", connectors_dir=connectors, regions_dir=regions,
                      http=_Feed())  # fmt: skip

    assert [r.url.rsplit("/", 1)[-1] for r in manifest.recordings] == [
        "station_status.json",
        "station_information.json",
    ]
    assert Manifest.load(connectors / "bicipalma" / "tests" / "fixtures").connector == "bicipalma"
