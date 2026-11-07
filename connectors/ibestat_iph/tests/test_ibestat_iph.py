import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded 2026-11-07 (dataset version 1.33, published 4 November) for Mallorca (ES532) and Menorca (ES533) from
# 25 August to 2 September 2026: August is out (status E, estimated), September is not (blank values and status).
WINDOW = TimeWindow(date(2026, 8, 25), date(2026, 9, 2))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)


def _answer():
    return json.loads((FIXTURES / "iph_20260825_20260902.json").read_text("utf-8"))


class RecordedIbestat:
    def __init__(self, body=None):
        self.body = body if body is not None else _answer()
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        return self.body


def _observations(window=WINDOW, http=None):
    connector = registry.load("ibestat_iph", http=http or RecordedIbestat())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def test_asks_only_for_the_islands_of_the_region_and_the_days_of_the_window():
    http = RecordedIbestat()

    payloads = registry.load("ibestat_iph", http=http).extract(WINDOW, MALLORCA)

    assert len(payloads) == len(http.calls) == 1
    url, params = http.calls[0]
    assert url.startswith("https://ibestat.es/edatos/apis/statistical-resources/v1.0/datasets/IBESTAT/")
    assert url.endswith("/000011A_000002/~latest.json")
    assert params["fields"] == "-metadata"  # the cube without its 3 MB of metadata
    assert params["dim"].startswith("TERRITORIO:ES532:TIME_PERIOD:2026-08-25|2026-08-26|")
    assert params["dim"].endswith("|2026-09-02")


def test_a_long_window_is_split_into_requests_of_a_year():
    http = RecordedIbestat()

    registry.load("ibestat_iph", http=http).extract(TimeWindow(date(2024, 1, 1), date(2026, 8, 31)), MALLORCA)

    assert len(http.calls) == 3  # 366 + 366 + 241 days
    assert http.calls[0][1]["dim"].count("|") == 365


def test_one_value_per_published_day_of_mallorca_at_local_midnight():
    observations = _observations()

    assert {o.entity for o in observations} == {"mallorca"}  # not Menorca
    assert len(observations) == 7  # 25 to 31 August; 1 and 2 September are not published yet
    last = observations[-1]
    assert last.ts == datetime(2026, 8, 30, 22, tzinfo=UTC)  # 31 August 00:00 in Madrid (CEST)
    assert (last.value, last.unit, last.quality) == (1401167.0, "people", Quality.OK)
    assert (last.lat, last.lon) == pytest.approx((39.6157, 2.9882))


def test_a_value_with_status_o_is_missing():
    answer = _answer()
    status = answer["data"]["attributes"]["attribute"][0]
    status["value"] = "O" + status["value"][1:]  # the first cell: Mallorca on 25 August

    observations = _observations(http=RecordedIbestat(answer))

    first = observations[0]
    assert first.ts == datetime(2026, 8, 24, 22, tzinfo=UTC)  # 25 August in Madrid
    assert (first.value, first.quality) == (None, Quality.MISSING)


def test_the_island_is_named():
    connector = registry.load("ibestat_iph", http=RecordedIbestat())
    (payload,) = connector.extract(WINDOW, MALLORCA)

    assert [(e.entity, e.name) for e in connector.describe(payload, MALLORCA)] == [("mallorca", "Mallorca")]


def test_an_answer_that_is_not_a_dataset_is_an_error():
    with pytest.raises(ConnectorError, match="not an eDatos dataset"):
        _observations(http=RecordedIbestat({"error": "nope"}))


def test_observations_that_do_not_fill_the_cube_are_an_error():
    answer = _answer()
    answer["data"]["observations"] = "1 | 2 | 3"

    with pytest.raises(ConnectorError, match="3 observations"):
        _observations(http=RecordedIbestat(answer))


def test_no_island_in_the_region_is_an_error():
    elsewhere = Region("menorca", 39.8, 3.8, 40.1, 4.4)

    with pytest.raises(ConnectorError, match="no Ibestat territory"):
        registry.load("ibestat_iph", http=RecordedIbestat()).extract(WINDOW, elsewhere)


def test_the_window_ends_95_days_before_yesterday_and_rereads_120_days():
    connector = registry.load("ibestat_iph", http=RecordedIbestat())

    window = connector.config.window(1, today=date(2026, 11, 7))

    assert window.end == date(2026, 8, 3)  # the day before 7 November minus 95 days: published on 4 November
    assert window.n_days == 120
