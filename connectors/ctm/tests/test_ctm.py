import base64
from datetime import UTC, date, datetime
from pathlib import Path

from core.connectors import registry
from core.models import Quality, Region, TimeWindow

# Real CTM GTFS (feed_version 2026.10.27) reduced to five lines, values kept verbatim: train T1, metro M1, bus 313
# (with the 8 and 25 December exceptions), summer bus 325 (until 31 October) and on-demand 343d. 240 trips, 82 stops.
FIXTURE = Path(__file__).parent / "fixtures" / "gtfs_t1_m1_313_325_343d.zip"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
STOPS = 82


class RecordedFeed:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_bytes(self, url, params=None, headers=None):
        self.calls.append(url)
        return FIXTURE.read_bytes()


def _normalize(window, region=MALLORCA):
    connector = registry.load("ctm", http=RecordedFeed())
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def _value(observations, stop, metric, day):
    # ts is local midnight (Europe/Madrid), so its date is the service day.
    return next(o.value for o in observations if o.entity == stop and o.metric == metric and o.ts.date() == day)


def test_the_zip_lands_in_bronze_untouched():
    http = RecordedFeed()
    connector = registry.load("ctm", http=http)
    window = TimeWindow(date(2026, 10, 27), date(2026, 10, 27))

    payloads = connector.extract(window, MALLORCA)

    assert len(payloads) == len(http.calls) == 1
    assert http.calls[0].startswith("https://www.tib.org/")
    assert payloads[0].key == "ctm/schedule/window=20261027_20261027/payload.json"
    assert base64.b64decode(payloads[0].body) == FIXTURE.read_bytes()


def test_every_trip_counts_once_at_each_stop():
    observations = _normalize(TimeWindow(date(2026, 10, 30), date(2026, 10, 30)))

    # Friday: stop 1025 is served by the T1 train and the M1 metro, 162 trips in all (no frequencies.txt).
    assert _value(observations, "stop_1025", "scheduled_departures", date(2026, 10, 30)) == 162
    assert _value(observations, "stop_1025", "lines_served", date(2026, 10, 30)) == 2
    assert {o.unit for o in observations if o.metric == "scheduled_departures"} == {"vehicles"}
    assert {o.quality for o in observations} == {Quality.OK}


def test_holidays_use_the_calendar_exceptions():
    observations = _normalize(TimeWindow(date(2026, 12, 7), date(2026, 12, 8)))

    # Inca bus station on line 313: 9 weekday buses on Monday, the 5 of the weekend service on 8 December.
    assert _value(observations, "stop_1386", "scheduled_departures", date(2026, 12, 7)) == 9
    assert _value(observations, "stop_1386", "scheduled_departures", date(2026, 12, 8)) == 5


def test_summer_lines_stop_at_the_end_of_their_season():
    observations = _normalize(TimeWindow(date(2026, 10, 31), date(2026, 11, 1)))

    served = {
        day: {o.entity for o in observations if o.metric == "scheduled_departures" and o.value and o.ts.day == day}
        for day in (31, 1)
    }
    # Saturday 31 October: last day of bus 325 (and no weekday train or metro); Sunday: only the weekend 313.
    assert len(served[31]) == 62
    assert len(served[1]) == 9
    assert _value(observations, "stop_1478", "scheduled_departures", date(2026, 11, 1)) == 5


def test_every_stop_gets_a_value_each_day_and_its_location():
    observations = _normalize(TimeWindow(date(2026, 11, 1), date(2026, 11, 2)))

    assert len(observations) == STOPS * 2 * 2  # stops x metrics x days, zero included
    assert _value(observations, "stop_1025", "scheduled_departures", date(2026, 11, 1)) == 0
    stop = next(o for o in observations if o.entity == "stop_1386")
    assert MALLORCA.contains(stop.lat, stop.lon)
    assert stop.ts == datetime(2026, 10, 31, 23, tzinfo=UTC)  # local midnight (CET) of 2026-11-01
