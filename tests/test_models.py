import itertools
import json
from datetime import UTC, date, datetime

import pytest

from core.config import available_regions, load_region
from core.models import Observation, RawPayload, TimeWindow


def test_last_days_ends_yesterday():
    window = TimeWindow.last_days(30, today=date(2026, 10, 24))
    assert window.end == date(2026, 10, 23)
    assert window.start == date(2026, 9, 24)
    assert window.n_days == 30


def test_last_days_is_deterministic_for_reruns():
    today = date(2026, 10, 24)
    assert TimeWindow.last_days(1, today) == TimeWindow.last_days(1, today)


@pytest.mark.parametrize("days", [0, -3])
def test_last_days_rejects_non_positive(days):
    with pytest.raises(ValueError, match="days must be >= 1"):
        TimeWindow.last_days(days)


def test_payload_roundtrip():
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 2))
    payload = RawPayload("src", "ds", window, {"url": "x"}, {"a": [1, None]})
    restored = RawPayload.from_json(payload.to_json())
    assert restored == payload
    assert payload.key == "src/ds/window=20261001_20261002/payload.json"


def test_partition_is_part_of_the_key_and_survives_roundtrip():
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 2))
    payload = RawPayload("src", "ds", window, {}, "a,b\n1,2", partition="station_a")

    assert payload.key == "src/ds/partition=station_a/window=20261001_20261002/payload.json"
    assert RawPayload.from_json(payload.to_json()) == payload


def test_payloads_written_without_partition_still_load():
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 1))
    legacy = json.loads(RawPayload("src", "ds", window, {}, {}).to_json())
    del legacy["partition"]

    assert RawPayload.from_json(json.dumps(legacy)).partition is None


def test_observation_requires_timezone():
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 - the naive datetime is what is under test
    with pytest.raises(ValueError, match="timezone-aware"):
        Observation("s", "e", "m", naive, 1.0, "u")


def test_observation_rejects_unknown_quality():
    with pytest.raises(ValueError, match="unknown quality label"):
        Observation("s", "e", "m", datetime(2026, 1, 1, tzinfo=UTC), 1.0, "u", quality="bad")


def test_split_covers_the_window_without_overlaps():
    window = TimeWindow(date(2026, 1, 1), date(2026, 3, 31))  # 90 days

    chunks = window.split(31)

    assert [c.n_days for c in chunks] == [31, 31, 28]
    assert chunks[0].start == window.start
    assert chunks[-1].end == window.end
    assert all(a.end.toordinal() + 1 == b.start.toordinal() for a, b in itertools.pairwise(chunks))


def test_split_shorter_window_is_unchanged():
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 2))
    assert window.split(31) == [window]


def test_split_rejects_non_positive_size():
    with pytest.raises(ValueError, match="max_days must be >= 1"):
        TimeWindow(date(2026, 10, 1), date(2026, 10, 2)).split(0)


def test_catch_up_recovers_days_after_the_last_successful_run():
    window = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))

    recovered = window.catch_up(last_loaded=date(2026, 10, 19), limit_days=31)

    assert recovered == TimeWindow(date(2026, 10, 20), date(2026, 10, 23))


@pytest.mark.parametrize("last_loaded", [None, date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 30)])
def test_catch_up_keeps_the_window_when_nothing_was_missed(last_loaded):
    window = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))

    assert window.catch_up(last_loaded, limit_days=31) == window


def test_catch_up_is_capped_and_never_shrinks_the_window():
    window = TimeWindow(date(2026, 10, 20), date(2026, 10, 23))

    assert window.catch_up(date(2026, 1, 1), limit_days=10) == TimeWindow(date(2026, 10, 14), date(2026, 10, 23))
    assert window.catch_up(date(2026, 1, 1), limit_days=2) == window  # requested 4 days > limit: unchanged


def test_mallorca_region_is_available():
    assert "mallorca" in available_regions()
    region = load_region("mallorca")
    assert len(region.locations) >= 1
    assert all(region.contains(loc.lat, loc.lon) for loc in region.locations)
    assert not region.contains(41.38, 2.17)  # Barcelona


def test_unknown_region_lists_available():
    with pytest.raises(ValueError, match="mallorca"):
        load_region("atlantis")
