import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.connectors.live import MANIFEST, instant_of
from core.connectors.recording import RecordedHttp
from core.live import poll_connector
from core.models import Quality, RawPayload, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Real snapshots kept by the poller on 2026-11-26, at the same bronze keys, cut down to five stations (values kept
# verbatim): every station_status of 16:00-17:00 UTC plus the two around it, and the station_information of 16:00.
SNAPSHOTS = FIXTURES / "snapshots"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
# The recorded poll: GBFS answered at 2026-11-26 15:50:39 UTC with the 106 stations.
POLLED_AT = datetime(2026, 11, 26, 15, 50, 39, tzinfo=UTC)
TODAY = TimeWindow(date(2026, 11, 26), date(2026, 11, 26))


class FakeBronze:
    """Bronze in memory, with the listing calls of core.storage.BronzeStore."""

    def __init__(self) -> None:
        self.objects: dict[str, str] = {}

    def put(self, payload, key=None):
        key = key or payload.key
        self.objects[key] = payload.to_json()
        return key

    def get(self, key):
        return RawPayload.from_json(self.objects[key])

    def keys(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def folders(self, prefix):
        return sorted(
            {prefix + k[len(prefix) :].split("/", 1)[0] + "/" for k in self.keys(prefix) if "/" in k[len(prefix) :]}
        )


class NoNetwork:
    def get_json(self, url, params=None, headers=None):
        pytest.fail(f"a run must read bronze, not call {url}")


def _connector(http=None, store=None):
    connector = registry.load("bicipalma", http=http or RecordedHttp(FIXTURES))
    connector.store = store if store is not None else FakeBronze()
    return connector


def _kept_snapshots() -> FakeBronze:
    store = FakeBronze()
    for path in sorted(SNAPSHOTS.rglob("*.json")):
        store.objects[path.relative_to(SNAPSHOTS).as_posix()] = path.read_text(encoding="utf-8")
    return store


def _run(connector, window):
    """What the pipeline does with a live connector: the manifest, then its observations and names."""
    (manifest,) = connector.extract(window, MALLORCA)
    return manifest, list(connector.normalize(manifest, MALLORCA)), list(connector.describe(manifest, MALLORCA))


def _value(observations, station, metric, hour):
    return next(o.value for o in observations if o.entity == station and o.metric == metric and o.ts == hour)


# --- the poller's half --------------------------------------------------------------------------------------------


def test_a_poll_keeps_the_feed_untouched_under_its_own_timestamp():
    connector = _connector()

    payload = connector.poll("station_status", MALLORCA)

    recorded = json.loads((FIXTURES / "01_station_status_json.json").read_text(encoding="utf-8"))
    assert payload.body == recorded
    assert connector.instant(payload) == POLLED_AT  # last_updated, not when it was fetched
    assert connector.snapshot_key(payload) == "bicipalma/snapshots/station_status/day=2026-11-26/20261126T155039Z.json"


def test_the_poller_keeps_the_status_every_time_and_the_stations_once_an_hour(tmp_path):
    store = FakeBronze()

    first = poll_connector("bicipalma", store=store, now=POLLED_AT, http=RecordedHttp(FIXTURES))
    second = poll_connector("bicipalma", store=store, now=POLLED_AT + timedelta(minutes=5), http=RecordedHttp(FIXTURES))
    next_hour = poll_connector(
        "bicipalma", store=store, now=POLLED_AT + timedelta(minutes=10), http=RecordedHttp(FIXTURES)
    )

    assert sorted(first.kept) == ["station_information", "station_status"]
    assert (sorted(second.kept), second.not_due) == (["station_status"], ["station_information"])
    assert "station_information" in next_hour.kept  # 16:00: a new hour
    # The recording always answers the same feed: polling it again keeps the same snapshot, not a copy.
    assert len(store.keys("bicipalma/snapshots/station_status/")) == 1


def test_an_answer_without_stations_is_not_kept():
    class Broken:
        def get_json(self, url, params=None, headers=None):
            return {"error": "maintenance"}

    with pytest.raises(ConnectorError, match="not a GBFS feed"):
        _connector(http=Broken()).poll("station_status", MALLORCA)


# --- the daily run's half -----------------------------------------------------------------------------------------


def test_a_run_reads_the_snapshots_of_its_window_from_bronze_without_calling_the_source():
    store = _kept_snapshots()
    connector = _connector(http=NoNetwork(), store=store)

    manifest, _, _ = _run(connector, TODAY)

    assert manifest.dataset == MANIFEST
    assert manifest.key == "bicipalma/manifest/window=20261126_20261126/payload.json"
    status = manifest.body["snapshots"]["station_status"]
    assert status == store.keys("bicipalma/snapshots/station_status/day=2026-11-26/")
    assert len(manifest.body["snapshots"]["station_information"]) == 1
    assert connector.first_day() == date(2026, 11, 26)
    assert manifest.body["first_snapshot"] == instant_of(status[0]).isoformat()


def test_each_station_gets_the_mean_minimum_and_maximum_of_its_hour():
    _, observations, _ = _run(_connector(http=NoNetwork(), store=_kept_snapshots()), TODAY)

    hour = datetime(2026, 11, 26, 16, tzinfo=UTC)
    station = "station_91733840"  # 01 PARC DE SES VELES: 11, 11, 12, 11, 9, 10 and six more 11 bikes of 20
    metrics = ("bikes_available", "bikes_available_min", "bikes_available_max", "docks_available",
               "docks_available_min", "docks_available_max", "occupancy")  # fmt: skip
    assert [_value(observations, station, m, hour) for m in metrics] == [10.83, 9, 12, 9.17, 8, 11, 54.17]
    # 18 JOSEP DARDER METGE ran out of free docks twice in the hour (16:21 and 16:26): its minimum says so.
    assert _value(observations, "station_91737907", "docks_available_min", hour) == 0
    assert {o.unit for o in observations if o.metric.startswith("docks")} == {"docks"}
    assert {o.quality for o in observations} == {Quality.OK}
    assert {o.ts.minute for o in observations} == {0}  # stamped on the hour


def test_only_hours_with_snapshots_get_values_and_the_station_its_place():
    _, observations, _ = _run(_connector(http=NoNetwork(), store=_kept_snapshots()), TODAY)

    hours = sorted({o.ts for o in observations})
    assert hours == [datetime(2026, 11, 26, h, tzinfo=UTC) for h in (15, 16, 17)]
    stations = {o.entity for o in observations}
    assert len(stations) == 5
    first = next(o for o in observations if o.entity == "station_91733840")
    assert (first.lat, first.lon) == (39.566056, 2.659389)


def test_stations_are_named_as_bicipalma_numbers_them():
    _, _, names = _run(_connector(http=NoNetwork(), store=_kept_snapshots()), TODAY)

    assert {e.entity: e.name for e in names}["station_91733840"] == "01 PARC DE SES VELES"
    assert {e.source for e in names} == {"bicipalma"}


def test_the_recorded_poll_is_one_snapshot_of_the_whole_system():
    store = FakeBronze()
    connector = _connector(store=store)
    for dataset in connector.polled_datasets():
        payload = connector.poll(dataset, MALLORCA)
        store.put(payload, key=connector.snapshot_key(payload))

    _, observations, names = _run(connector, TODAY)

    assert len(names) == 106
    assert {o.ts for o in observations} == {datetime(2026, 11, 26, 15, tzinfo=UTC)}
    hour = datetime(2026, 11, 26, 15, tzinfo=UTC)
    # One snapshot: the mean, the minimum and the maximum are its value. 10 bikes (one electric) and 10 free docks.
    assert [
        _value(observations, "station_91733840", m, hour)
        for m in (
            "bikes_available",
            "bikes_available_min",
            "bikes_available_max",
            "ebikes_available",
            "docks_available",
            "occupancy",
        )
    ] == [10, 10, 10, 1, 10, 50]


# --- what a live source cannot have -------------------------------------------------------------------------------


def test_before_the_first_poll_there_is_no_first_day():
    connector = _connector(store=FakeBronze())

    assert connector.first_day() == date.max  # every window is before it: the run is skipped


def test_hours_before_the_first_snapshot_or_after_the_read_are_not_expected():
    connector = _connector(http=NoNetwork(), store=_kept_snapshots())
    (manifest,) = connector.extract(TODAY, MALLORCA)
    read = RawPayload.from_json(
        manifest.to_json().replace(
            manifest.fetched_at.isoformat(), datetime(2026, 11, 26, 18, 7, tzinfo=UTC).isoformat()
        )
    )

    start, end = connector.observed_span(read)

    assert start == datetime(2026, 11, 26, 15, tzinfo=UTC)  # the hour of the first snapshot
    assert end == datetime(2026, 11, 26, 19, tzinfo=UTC)  # the hour in progress when it was read counts
