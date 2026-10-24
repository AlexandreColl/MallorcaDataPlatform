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


def test_observation_requires_timezone():
    naive = datetime(2026, 1, 1)  # noqa: DTZ001 - the naive datetime is what is under test
    with pytest.raises(ValueError, match="timezone-aware"):
        Observation("s", "e", "m", naive, 1.0, "u")


def test_observation_rejects_unknown_quality():
    with pytest.raises(ValueError, match="unknown quality label"):
        Observation("s", "e", "m", datetime(2026, 1, 1, tzinfo=UTC), 1.0, "u", quality="bad")


def test_mallorca_region_is_available():
    assert "mallorca" in available_regions()
    region = load_region("mallorca")
    assert len(region.locations) >= 1
    assert all(region.contains(loc.lat, loc.lon) for loc in region.locations)
    assert not region.contains(41.38, 2.17)  # Barcelona


def test_unknown_region_lists_available():
    with pytest.raises(ValueError, match="mallorca"):
        load_region("atlantis")
