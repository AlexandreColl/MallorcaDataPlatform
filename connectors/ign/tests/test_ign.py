from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded with the bbox below (Mallorca + 1 degree) for 2025-07-01..2025-09-30.
WINDOW = TimeWindow(date(2025, 7, 1), date(2025, 9, 30))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)


class RecordedFdsn:
    """Serves the recorded FDSN text response, or an empty body like the real ``204 No Content``."""

    def __init__(self, body: str | None = None) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.body = body

    def get_text(self, url, params=None, headers=None):
        self.calls.append((url, params))
        if self.body is not None:
            return self.body
        return (FIXTURES / "events_2025q3.txt").read_text(encoding="utf-8")


def _connector(http=None):
    return registry.load("ign", http=http or RecordedFdsn())


def _normalize_all(connector, window=WINDOW):
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def test_one_request_with_the_widened_region_box():
    http = RecordedFdsn()

    payloads = _connector(http).extract(WINDOW, MALLORCA)

    assert len(payloads) == 1
    assert payloads[0].key == "ign/earthquakes/window=20250701_20250930/payload.json"
    _, params = http.calls[0]
    assert (params["minlat"], params["maxlat"], params["minlon"], params["maxlon"]) == (
        "38.25",
        "40.97",
        "1.30",
        "4.50",
    )
    assert (params["starttime"], params["endtime"]) == ("2025-07-01T00:00:00", "2025-09-30T23:59:59")
    assert params["format"] == "text"


def test_each_ign_event_becomes_magnitude_and_depth():
    observations = _normalize_all(_connector())
    by_key = {(o.entity, o.metric): o for o in observations}

    assert len(observations) == 5 * 2  # 5 IGN events x 2 metrics
    quake = "20250816_0000066"  # closest to Mallorca: off the north-east coast
    assert by_key[quake, "magnitude"].value == pytest.approx(1.8)
    assert by_key[quake, "magnitude"].unit == "M"
    assert by_key[quake, "depth_km"].value == pytest.approx(14.5)
    assert by_key[quake, "depth_km"].ts == datetime(2025, 8, 16, 1, 43, 31, 200000, tzinfo=UTC)
    assert (by_key[quake, "depth_km"].lat, by_key[quake, "depth_km"].lon) == (39.7649, 3.2621)
    assert {o.quality for o in observations} == {Quality.OK}


def test_events_located_by_other_agencies_are_skipped():
    entities = {o.entity for o in _normalize_all(_connector())}

    assert "20250703_0000215" not in entities  # EMSC's own solution, kept only in bronze


def test_no_events_is_an_empty_result_not_an_error():
    connector = _connector(RecordedFdsn(body=""))  # the service answers 204 No Content

    payloads = connector.extract(WINDOW, MALLORCA)

    assert len(payloads) == 1  # the empty response is still landed in bronze
    assert list(connector.normalize(payloads[0], MALLORCA)) == []
    assert connector.config.is_event_source
