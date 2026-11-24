from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from connectors.redmar.extractor import parse_ascii
from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
DAY = TimeWindow(date(2026, 11, 22), date(2026, 11, 22))


@pytest.fixture
def recorded():
    """The connector answering from the recordings of 22 November 2026, one day of both gauges."""
    connector = registry.load("redmar", http=RecordedHttp(FIXTURES))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def _observations(connector, window, region):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def test_one_sampled_request_per_station_and_day(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.request["station"] for p in payloads] == ["palma", "alcudia"]
    assert [p.partition for p in payloads] == ["palma", "alcudia"]
    assert list(payloads[0].body) == ["2026-11-22"]
    url = payloads[0].request["urls"]["2026-11-22"]
    assert url.endswith("tidegauge_mall/2026/11/MIR2Z_Mallorca_Mall_3851_20261122.nc4")


def test_every_hour_of_both_gauges_is_the_mean_of_its_good_minutes(recorded):
    connector, window, region = recorded

    observations = _observations(connector, window, region)

    assert len(observations) == 2 * 24
    assert {o.entity for o in observations} == {"palma", "alcudia"}
    assert min(o.ts for o in observations) == datetime(2026, 11, 22, 0, tzinfo=UTC)
    assert max(o.ts for o in observations) == datetime(2026, 11, 22, 23, tzinfo=UTC)
    ok = [o for o in observations if o.quality == Quality.OK]
    # In 2026 the files lose whole hours, the same at both gauges: 6 of the 24 of that day have no sample at all.
    missing = sorted({o.ts.hour for o in observations if o.quality == Quality.MISSING})
    assert missing == [1, 7, 11, 15, 20, 22]
    assert len(ok) == 2 * (24 - 6)
    assert all(3.5 < o.value < 5 for o in ok)  # about 4 m above the harbour datum, give or take the tide
    assert {o.unit for o in observations} == {"m"}
    palma = next(o for o in observations if o.entity == "palma")
    assert (palma.lat, palma.lon) == (39.56015, 2.63748)


def test_the_names_of_the_gauges_come_from_the_config(recorded):
    connector, window, region = recorded

    names = {e.entity: e.name for p in connector.extract(window, region) for e in connector.describe(p, region)}

    assert names == {"palma": "Mareógrafo de Palma", "alcudia": "Mareógrafo de Alcúdia"}


ANSWER = """Dataset {
    Float64 TIME[TIME = 4];
    Float32 SLEV[TIME = 4][DEPTH = 1];
    Byte SLEV_QC[TIME = 4][DEPTH = 1];
} tidegauge_mall/2026/11/x.nc4;
---------------------------------------------
TIME[4]
28084.0, 28084.01, 28084.042, 28084.05

SLEV[4][1]
[0], 4.2
[1], 4.4
[2], 99999.0
[3], 4.1

SLEV_QC[4][1]
[0], 1
[1], 2
[2], 9
[3], 4
"""


def test_parse_ascii_reads_one_and_two_dimensional_arrays():
    arrays = parse_ascii(ANSWER)

    assert arrays["TIME"] == [28084.0, 28084.01, 28084.042, 28084.05]
    assert arrays["SLEV"] == [4.2, 4.4, 99999.0, 4.1]
    assert arrays["SLEV_QC"] == [1, 2, 9, 4]


class FakeHttp:
    """Answers each day file from ``days`` (None: 404), and a file of another length with a 400 first."""

    def __init__(self, days, short=()):
        self.days, self.short, self.calls = days, set(short), []

    def get_text(self, url, params=None, headers=None):
        self.calls.append(url)
        name = url.split("/")[-1].split(".nc4")[0]
        day = name.rsplit("_", 1)[-1]
        if url.endswith(".dds"):
            return "Dataset {\n    Float64 TIME[TIME = 4];\n}"
        if day not in self.days or self.days[day] is None:
            raise _http_error(requests.codes.not_found)
        if day in self.short and "172799" in url:
            raise _http_error(requests.codes.bad_request)
        return self.days[day]


def _http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


PALMA_ONLY = Region("palma", 39.5, 2.6, 39.6, 2.7)


def test_an_hour_with_few_good_samples_is_suspect_and_a_bad_value_is_left_out():
    connector = registry.load("redmar", http=FakeHttp({"20261122": ANSWER}))
    observations = _observations(connector, DAY, PALMA_ONLY)

    first, second = observations  # 00:00-00:59 has 3 samples, 01:00-01:59 has 1
    assert (first.ts, first.value, first.quality) == (datetime(2026, 11, 22, 0, tzinfo=UTC), 4.3, Quality.OK)
    assert second.ts == datetime(2026, 11, 22, 1, tzinfo=UTC)
    assert (second.value, second.quality) == (None, Quality.MISSING)  # its only sample is flagged bad (4)


def test_a_day_without_a_file_is_skipped_and_a_window_without_files_gives_no_payload():
    window = TimeWindow(date(2026, 11, 21), date(2026, 11, 22))
    connector = registry.load("redmar", http=FakeHttp({"20261121": None, "20261122": ANSWER}))

    payloads = connector.extract(window, PALMA_ONLY)
    assert list(payloads[0].body) == ["2026-11-22"]

    assert registry.load("redmar", http=FakeHttp({})).extract(window, PALMA_ONLY) == []


def test_a_file_of_another_length_is_asked_again_with_its_size():
    http = FakeHttp({"20261122": ANSWER}, short={"20261122"})

    payloads = registry.load("redmar", http=http).extract(DAY, PALMA_ONLY)

    assert payloads[0].body["2026-11-22"] == ANSWER
    assert http.calls[1].endswith(".nc4.dds")
    assert "%5B0:120:3%5D" in http.calls[2]


class Unreadable(FakeHttp):
    """Answers ``error`` for the days in ``broken``, like a file the server cannot read."""

    def __init__(self, days, broken, error):
        super().__init__(days)
        self.broken, self.error = set(broken), error

    def get_text(self, url, params=None, headers=None):
        if any(day in url for day in self.broken):
            self.calls.append(url)
            raise self.error
        return super().get_text(url, params, headers)


def test_a_day_the_server_cannot_read_is_skipped():
    window = TimeWindow(date(2026, 11, 20), date(2026, 11, 22))
    for error in (_http_error(requests.codes.internal_server_error), requests.exceptions.RetryError()):
        http = Unreadable({"20261120": ANSWER, "20261122": ANSWER}, broken={"20261121"}, error=error)

        payloads = registry.load("redmar", http=http).extract(window, PALMA_ONLY)

        assert list(payloads[0].body) == ["2026-11-20", "2026-11-22"]


def test_the_server_down_for_more_days_in_a_row_fails():
    days = [f"202611{d:02}" for d in range(18, 23)]
    error = _http_error(requests.codes.internal_server_error)
    three = TimeWindow(date(2026, 11, 20), date(2026, 11, 22))
    assert registry.load("redmar", http=Unreadable({}, days, error)).extract(three, PALMA_ONLY) == []

    four = TimeWindow(date(2026, 11, 19), date(2026, 11, 22))
    with pytest.raises(requests.HTTPError):
        registry.load("redmar", http=Unreadable({}, days, error)).extract(four, PALMA_ONLY)

    # a day read between them starts the count again
    five = TimeWindow(date(2026, 11, 18), date(2026, 11, 22))
    http = Unreadable({"20261120": ANSWER}, [d for d in days if d != "20261120"], error)
    assert list(registry.load("redmar", http=http).extract(five, PALMA_ONLY)[0].body) == ["2026-11-20"]


def test_other_errors_and_arrays_of_different_lengths_fail():
    forbidden = Unreadable({}, ["20261122"], _http_error(requests.codes.forbidden))
    with pytest.raises(requests.HTTPError):
        registry.load("redmar", http=forbidden).extract(DAY, PALMA_ONLY)

    connector = registry.load("redmar", http=FakeHttp({"20261122": ANSWER.replace("[3], 4\n", "")}))
    with pytest.raises(ConnectorError, match="4 times, 4 levels and 3 flags"):
        _observations(connector, DAY, PALMA_ONLY)


def test_a_region_without_gauges_is_an_error():
    with pytest.raises(ConnectorError, match="no REDMAR tide gauge"):
        registry.load("redmar", http=FakeHttp({})).extract(DAY, Region("menorca", 39.8, 3.8, 40.1, 4.4))
