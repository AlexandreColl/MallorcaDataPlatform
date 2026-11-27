from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import requests

from connectors.noaa_oisst.extractor import last_day, parse_csv, parse_opendap_grid
from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
FINAL = "ncdcOisst21Agg_LonPM180"
PRELIMINARY = "ncdcOisst21NrtAgg_LonPM180"
POINTS = 8


@pytest.fixture
def recorded():
    """The connector answering from the recordings of 26 November 2026: 2026-11-04..24, three weeks."""
    connector = registry.load("noaa_oisst", http=RecordedHttp(FIXTURES))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def _observations(connector, window, region):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def test_the_final_product_up_to_its_last_day_and_the_preliminary_one_after_it(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.dataset for p in payloads] == ["final", "preliminary"]
    assert [(p.request["start"], p.request["end"]) for p in payloads] == [
        ("2026-11-04", "2026-11-10"),  # the last final day on 26 November
        ("2026-11-11", "2026-11-24"),
    ]
    assert FINAL in payloads[0].request["url"]
    assert PRELIMINARY in payloads[1].request["url"]
    # One box for all the points, the 3 x 5 cells between their cells, asked at 12:00 UTC (where ERDDAP stamps days).
    box = "%5B(0.0)%5D%5B(39.375):1:(39.875)%5D%5B(2.375):1:(3.375)%5D"
    assert payloads[0].request["url"].endswith(f"sst%5B(2026-11-04T12:00:00Z):1:(2026-11-10T12:00:00Z)%5D{box}")


def test_one_value_per_point_and_day_stamped_at_midnight_utc(recorded):
    connector, window, region = recorded

    observations = _observations(connector, window, region)

    assert len(observations) == POINTS * window.n_days
    final = [o for o in observations if o.metric == "sea_surface_temperature"]
    preliminary = [o for o in observations if o.metric == "sea_surface_temperature_preliminary"]
    assert len(final) == POINTS * 7
    assert len(preliminary) == POINTS * 14
    assert all(o.quality == Quality.OK for o in observations), "every configured cell is sea"
    assert {o.ts.time() for o in observations} == {datetime.min.time()}
    palma = {o.ts: o for o in final if o.entity == "bahia_de_palma"}
    assert palma[datetime(2026, 11, 5, tzinfo=UTC)].value == pytest.approx(21.93)
    assert palma[datetime(2026, 11, 10, tzinfo=UTC)].value == pytest.approx(21.54)
    fifth = palma[datetime(2026, 11, 5, tzinfo=UTC)]
    assert (fifth.lat, fifth.lon) == (39.375, 2.625)
    assert {o.unit for o in observations} == {"degC"}


def test_the_names_of_the_points_come_from_the_config(recorded):
    connector, window, region = recorded

    names = {e.entity: e.name for p in connector.extract(window, region) for e in connector.describe(p, region)}

    assert len(names) == POINTS
    assert names["colonia_sant_jordi"] == "Colònia de Sant Jordi"


def test_parse_csv_reads_land_cells_as_none():
    text = (
        "time,zlev,latitude,longitude,sst\nUTC,m,degrees_north,degrees_east,degree_C\n"
        "2026-11-09T12:00:00Z,0.0,39.625,2.375,21.44\n2026-11-09T12:00:00Z,0.0,39.625,2.625,NaN\n"
    )

    assert parse_csv(text) == [(date(2026, 11, 9), 39.625, 2.375, 21.44), (date(2026, 11, 9), 39.625, 2.625, None)]


def test_parse_csv_rejects_another_variable():
    with pytest.raises(ConnectorError, match="header"):
        parse_csv("time,zlev,latitude,longitude,anom\n")


def test_last_day_needs_a_time_step():
    assert last_day("time\nUTC\n2026-11-10T12:00:00Z\n") == date(2026, 11, 10)
    with pytest.raises(ConnectorError, match="no time step"):
        last_day("time\nUTC\n")


# PSL's answer for 10-13 October 1992 at two latitudes and two longitudes of the box, as OPeNDAP ASCII (real
# values of 10 October; the other days are made up). 39.625 / 2.625 is land.
PSL_ANSWER = """Dataset {
    Grid {
     ARRAY:
        Float32 sst[time = 4][lat = 2][lon = 2];
    } sst;
} Datasets/noaa.oisst.v2.highres/sst.day.mean.1992.nc;
---------------------------------------------
sst.sst[4][2][2]
[0][0], 21.039999, 20.9
[0][1], -9.96921E36, 20.7
[1][0], 20.83, 20.8
[1][1], -9.96921E36, 20.6
[2][0], 20.88, 20.8
[2][1], -9.96921E36, 20.6
[3][0], 21.109999, 21.0
[3][1], -9.96921E36, 20.8

sst.time[4]
70409.0, 70410.0, 70411.0, 70412.0

sst.lat[2]
39.375, 39.625

sst.lon[2]
2.625, 2.875

"""


def test_parse_opendap_grid_reads_days_since_1800_and_land_as_none():
    rows = parse_opendap_grid(PSL_ANSWER)

    assert len(rows) == 4 * 2 * 2
    assert rows[0] == (date(1992, 10, 10), 39.375, 2.625, pytest.approx(21.04))
    assert rows[2] == (date(1992, 10, 10), 39.625, 2.625, None)
    assert rows[-1] == (date(1992, 10, 13), 39.625, 2.875, 20.8)
    with pytest.raises(ConnectorError, match="does not match"):
        parse_opendap_grid(PSL_ANSWER.replace("70412.0", "70412.0, 70413.0"))


class FakeErddap:
    """ERDDAP and PSL: the given last days, a box with a row per day of ``days`` (or a 404) and PSL_ANSWER."""

    def __init__(
        self, last: dict[str, date], not_published: frozenset[str] = frozenset(), days: list[date] | None = None
    ) -> None:
        self.last = last
        self.not_published = not_published
        self.days = days
        self.urls: list[str] = []

    def get_text(self, url, params=None, headers=None):
        self.urls.append(url)
        if "psl.noaa.gov" in url:
            return PSL_ANSWER
        dataset = FINAL if FINAL in url else PRELIMINARY
        if url.endswith("time%5Blast%5D"):
            return f"time\nUTC\n{self.last[dataset].isoformat()}T12:00:00Z\n"
        if dataset in self.not_published:
            response = requests.Response()
            response.status_code = 404
            response._content = b'Error {\n    message="... \\"Stop\\" is greater than the axis maximum=...";\n}\n'
            raise requests.HTTPError(response=response)
        header = "time,zlev,latitude,longitude,sst\nUTC,m,degrees_north,degrees_east,degree_C\n"
        return header + "".join(f"{day}T12:00:00Z,0.0,39.375,2.625,21.0\n" for day in self.days or [])


MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)


def _every_day(window):
    return [window.start + timedelta(days=i) for i in range(window.n_days)]


def test_the_days_erddap_lacks_come_from_psl():
    window = TimeWindow(date(1992, 10, 9), date(1992, 10, 14))
    erddap_days = [date(1992, 10, 9), date(1992, 10, 10), date(1992, 10, 14)]  # its time axis skips 11-13 October
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, days=erddap_days)
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(window, MALLORCA)

    assert [(p.dataset, p.partition) for p in payloads] == [("final", None), ("final", "psl_19921011")]
    psl = payloads[1]
    assert psl.request["days"] == ["1992-10-11", "1992-10-12", "1992-10-13"]
    # Day 284-286 of the 1992 file (from 0), rows 517-519 (39.375-39.875) and columns 9-13 (2.375-3.375) of the grid.
    assert psl.request["url"].endswith("sst.day.mean.1992.nc.ascii?sst%5B284:1:286%5D%5B517:1:519%5D%5B9:1:13%5D")
    observations = list(connector.normalize(psl, MALLORCA))
    palma = sorted((o.ts.date(), o.value) for o in observations if o.entity == "bahia_de_palma")
    assert palma == [(date(1992, 10, 11), 20.83), (date(1992, 10, 12), 20.88), (date(1992, 10, 13), 21.109999)]
    assert {o.metric for o in observations} == {"sea_surface_temperature"}


def test_a_psl_failure_leaves_the_gap_without_failing_the_run():
    class Down(FakeErddap):
        def get_text(self, url, params=None, headers=None):
            if "psl.noaa.gov" in url:
                raise requests.ConnectionError(url)
            return super().get_text(url, params, headers)

    http = Down({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, days=[date(1992, 10, 9)])
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(TimeWindow(date(1992, 10, 9), date(1992, 10, 14)), MALLORCA)

    assert [p.partition for p in payloads] == [None]


def test_a_window_inside_the_record_asks_only_the_final_product():
    window = TimeWindow(date(1995, 1, 1), date(1999, 12, 31))
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, days=_every_day(window))
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(window, MALLORCA)

    assert [(p.dataset, p.request["start"], p.request["end"]) for p in payloads] == [
        ("final", "1995-01-01", "1999-12-31")
    ]
    assert not any(PRELIMINARY in url or "psl" in url for url in http.urls)


def test_the_days_before_the_record_are_not_asked_for():
    days = _every_day(TimeWindow(date(1981, 9, 1), date(1981, 12, 31)))
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, days=days)
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(TimeWindow(date(1981, 1, 1), date(1981, 12, 31)), MALLORCA)

    assert [(p.request["start"], p.request["end"]) for p in payloads] == [("1981-09-01", "1981-12-31")]
    assert connector.extract(TimeWindow(date(1980, 1, 1), date(1980, 12, 31)), MALLORCA) == []


def test_days_no_product_has_yet_are_left_for_the_next_run():
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 20)})
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(TimeWindow(date(2026, 11, 15), date(2026, 11, 24)), MALLORCA)

    assert [(p.dataset, p.request["start"], p.request["end"]) for p in payloads] == [
        ("preliminary", "2026-11-15", "2026-11-20")
    ]


def test_a_404_past_the_last_day_is_not_published_yet_not_a_failure():
    days = _every_day(TimeWindow(date(2026, 11, 4), date(2026, 11, 10)))
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, frozenset({PRELIMINARY}), days)
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(TimeWindow(date(2026, 11, 4), date(2026, 11, 24)), MALLORCA)

    assert [p.dataset for p in payloads] == ["final"]


def test_no_point_outside_the_region():
    connector = registry.load("noaa_oisst", http=FakeErddap({}))

    with pytest.raises(ConnectorError, match="no OISST point"):
        connector.extract(TimeWindow(date(2026, 11, 4), date(2026, 11, 4)), Region("ibiza", 38.8, 1.2, 39.1, 1.6))


def test_psl_is_asked_in_spans_of_a_month_inside_one_year():
    window = TimeWindow(date(1992, 12, 1), date(1993, 2, 28))
    http = FakeErddap({FINAL: date(2026, 11, 10), PRELIMINARY: date(2026, 11, 25)}, days=[date(1993, 2, 28)])
    connector = registry.load("noaa_oisst", http=http)

    payloads = connector.extract(window, MALLORCA)

    spans = [(p.request["days"][0], p.request["days"][-1]) for p in payloads[1:]]
    assert spans == [("1992-12-01", "1992-12-31"), ("1993-01-01", "1993-01-31"), ("1993-02-01", "1993-02-27")]
