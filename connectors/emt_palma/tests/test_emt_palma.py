import base64
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import registry
from core.models import Quality, Region, TimeWindow

# Real EMT Palma GTFS reduced to lines 1 and CC (rows kept verbatim): 8 trips, 44 stops, valid 2026-09-08..12-31, plus
# the shapes.txt rows of their four shapes (from the 2026-11-08 feed).
FIXTURE = Path(__file__).parent / "fixtures" / "gtfs_l001_l002.zip"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
STOPS = 44
LINES = 2


class RecordedFeed:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_bytes(self, url, params=None, headers=None):
        self.calls.append(url)
        return FIXTURE.read_bytes()


def _normalize(window, region=MALLORCA):
    connector = registry.load("emt_palma", http=RecordedFeed())
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def _value(observations, stop, metric, day):
    # ts is local midnight (Europe/Madrid), so its date is the service day.
    return next(o.value for o in observations if o.entity == stop and o.metric == metric and o.ts.date() == day)


def test_the_zip_lands_in_bronze_untouched():
    http = RecordedFeed()
    connector = registry.load("emt_palma", http=http)
    window = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))

    payloads = connector.extract(window, MALLORCA)

    assert len(payloads) == len(http.calls) == 1
    assert payloads[0].key == "emt_palma/schedule/window=20261023_20261023/payload.json"
    archive = base64.b64decode(payloads[0].body)
    assert archive == FIXTURE.read_bytes()
    assert payloads[0].request["sha256"] == hashlib.sha256(archive).hexdigest()


def test_departures_follow_the_service_calendar():
    observations = _normalize(TimeWindow(date(2026, 10, 23), date(2026, 10, 26)))
    stop = "stop_19"  # passeig Mallorca: line 1 (outbound) and line CC

    # Friday: weekday service, line 1 every 15-30 min (50 buses) + CC every 35 min (24).
    assert _value(observations, stop, "scheduled_departures", date(2026, 10, 23)) == 74
    assert _value(observations, stop, "lines_served", date(2026, 10, 23)) == 2
    # Saturday: CC does not run.
    assert _value(observations, stop, "scheduled_departures", date(2026, 10, 24)) == 40
    assert _value(observations, stop, "lines_served", date(2026, 10, 24)) == 1
    assert {o.unit for o in observations if o.metric == "scheduled_departures"} == {"buses"}
    assert {o.quality for o in observations} == {Quality.OK}


def test_holidays_use_the_calendar_exceptions():
    observations = _normalize(TimeWindow(date(2026, 10, 12), date(2026, 10, 12)))

    # Monday 12 October: calendar_dates removes the weekday service and adds the Sunday one.
    assert _value(observations, "stop_19", "scheduled_departures", date(2026, 10, 12)) == 40
    assert _value(observations, "stop_19", "lines_served", date(2026, 10, 12)) == 1


def test_every_stop_gets_a_value_each_day_and_its_location():
    observations = _normalize(TimeWindow(date(2026, 10, 24), date(2026, 10, 25)))

    assert len(observations) == (STOPS * 2 + LINES) * 2  # (stops x metrics + lines) x days
    stop = next(o for o in observations if o.entity == "stop_19")
    assert (stop.lat, stop.lon) == (pytest.approx(39.574996), pytest.approx(2.644334))
    assert stop.ts == datetime(2026, 10, 23, 22, tzinfo=UTC)  # local midnight (CEST) of 2026-10-24


def test_days_outside_the_feed_validity_have_no_rows():
    observations = _normalize(TimeWindow(date(2026, 9, 1), date(2026, 9, 10)))

    days = {o.ts.date() for o in observations}
    assert len(days) == 3  # 8, 9 and 10 September: the feed starts on the 8th


def test_stops_outside_the_region_are_skipped():
    palma_east = Region("palma_east", 39.55, 2.65, 39.60, 2.70)

    observations = _normalize(TimeWindow(date(2026, 10, 23), date(2026, 10, 23)), palma_east)

    stops = [o for o in observations if o.entity.startswith("stop_")]
    assert stops
    assert all(palma_east.contains(o.lat, o.lon) for o in stops)
    assert len({o.entity for o in stops}) < STOPS


def test_stops_are_named_only_inside_the_region():
    palma_east = Region("palma_east", 39.55, 2.65, 39.60, 2.70)
    connector = registry.load("emt_palma", http=RecordedFeed())
    (payload,) = connector.extract(TimeWindow(date(2026, 10, 23), date(2026, 10, 23)), MALLORCA)

    names = {e.entity: e.name for e in connector.describe(payload, MALLORCA) if e.entity.startswith("stop_")}
    east = {e.entity for e in connector.describe(payload, palma_east) if e.entity.startswith("stop_")}

    assert len(names) == STOPS
    assert names["stop_6"] == "6-Sindicat - Àrea d'intercanvi Sindicat"
    assert east < set(names)


def test_every_line_counts_its_departures_each_day():
    observations = _normalize(TimeWindow(date(2026, 10, 23), date(2026, 10, 24)))

    # Friday: line 1 runs 99 buses (both directions, headways of frequencies.txt) and CC 48; on Saturday, no CC.
    assert _value(observations, "route_L001", "scheduled_trips", date(2026, 10, 23)) == 99
    assert _value(observations, "route_L002", "scheduled_trips", date(2026, 10, 23)) == 48
    assert _value(observations, "route_L001", "scheduled_trips", date(2026, 10, 24)) == 81
    assert _value(observations, "route_L002", "scheduled_trips", date(2026, 10, 24)) == 0
    line = next(o for o in observations if o.metric == "scheduled_trips")
    assert (line.unit, line.lat, line.lon) == ("trips", None, None)


def test_every_line_is_drawn_with_its_main_shape_in_each_direction():
    connector = registry.load("emt_palma", http=RecordedFeed())
    (payload,) = connector.extract(TimeWindow(date(2026, 10, 23), date(2026, 10, 23)), MALLORCA)

    routes = {r.route: r for r in connector.routes(payload, MALLORCA)}
    names = {e.entity: e.name for e in connector.describe(payload, MALLORCA)}

    assert set(routes) == {"route_L001", "route_L002"}
    line = routes["route_L001"]
    assert (line.short_name, line.name, line.kind, line.color) == ("1", "1 · Portopí - Sindicat", "bus", "#44743f")
    assert len(line.lines) == 2  # outbound and return
    assert line.lines[0][0] == (2.65602, 39.57135)  # (lon, lat), rounded to ~1 m
    assert all(len(path) < 100 for path in line.lines)  # simplified from hundreds of shape points
    assert names["route_L002"] == "CC · Circular Centre Ciutat"
