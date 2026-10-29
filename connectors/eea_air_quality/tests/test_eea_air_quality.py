import base64
import io
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

# The EEA search listing for 10-20 October 2026 (the Balearic lines and three from Madrid) and five real files,
# reduced to those days: Bellver NO2, Foners PM10, PM2.5 and CO (mg/m3) and Menut O3. The source has no data
# from 15 October 09:00 to 18 October and marks a few hours as not valid (value -999).
FIXTURES = Path(__file__).parent / "fixtures"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
WINDOW = TimeWindow(date(2026, 10, 12), date(2026, 10, 13))


def _empty_parquet() -> bytes:
    """A file with the EEA columns and no rows, for the sampling points without a fixture."""
    table = pq.read_table(FIXTURES / "SP_07040003_8_8.parquet").slice(0, 0)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


EMPTY = _empty_parquet()


class RecordedEea:
    def __init__(self) -> None:
        self.searches: list[dict] = []
        self.downloads: list[str] = []

    def post_text(self, url, json, headers=None):
        self.searches.append(json)
        return (FIXTURES / "urls.txt").read_text(encoding="utf-8")

    def get_bytes(self, url, params=None, headers=None):
        self.downloads.append(url)
        name = url.rsplit("/", 1)[-1]
        path = FIXTURES / name
        return path.read_bytes() if path.exists() else EMPTY


def _normalize(window=WINDOW, http=None):
    connector = registry.load("eea_air_quality", http=http or RecordedEea())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _value(observations, entity, metric, ts):
    return next(o.value for o in observations if o.entity == entity and o.metric == metric and o.ts == ts)


def test_search_and_only_the_configured_stations_are_downloaded():
    http = RecordedEea()
    connector = registry.load("eea_air_quality", http=http)

    payloads = connector.extract(WINDOW, MALLORCA)

    search = http.searches[0]
    assert search["countries"] == ["ES"]
    assert search["dataset"] == 1
    assert (search["dateTimeStart"], search["dateTimeEnd"]) == ("2026-10-12T00:00:00Z", "2026-10-13T23:59:59Z")
    assert "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/6001" in search["pollutants"]
    stations = {p.request["station"] for p in payloads}
    # Menorca, Ibiza, Madrid and the station without a known location (07040007) are left out.
    assert stations == {"07040002", "07040003", "07040004", "07040006", "07010001", "07044001", "07003001", "07003004", "07019001"}
    assert all("/SP_07" in url for url in http.downloads)
    bellver = next(p for p in payloads if p.partition == "07040003_8_8")
    assert base64.b64decode(bellver.body) == (FIXTURES / "SP_07040003_8_8.parquet").read_bytes()
    assert bellver.key == "eea_air_quality/hourly/partition=07040003_8_8/window=20261012_20261013/payload.json"


def test_utc_plus_one_timestamps_become_utc():
    observations = _normalize()

    # File row 2026-10-12 10:00 (UTC+01) is 09:00 UTC.
    assert _value(observations, "bellver", "nitrogen_dioxide", datetime(2026, 10, 12, 9, tzinfo=UTC)) == 21.0
    assert _value(observations, "menut", "ozone", datetime(2026, 10, 12, 9, tzinfo=UTC)) == 86.0
    bellver_no2 = [o for o in observations if o.entity == "bellver" and o.metric == "nitrogen_dioxide"]
    assert len(bellver_no2) == 48  # every hour of the two-day window
    assert min(o.ts for o in bellver_no2) == datetime(2026, 10, 12, tzinfo=UTC)
    assert {type(o.ts) for o in observations} == {datetime}  # not pandas.Timestamp: Spark rejects it


def test_carbon_monoxide_is_converted_to_micrograms():
    observations = _normalize()

    co = _value(observations, "foners", "carbon_monoxide", datetime(2026, 10, 12, 9, tzinfo=UTC))
    assert co == 600.0  # 0.6 mg/m3
    assert {o.unit for o in observations} == {"ug/m3"}


def test_not_valid_hours_are_missing_not_minus_999():
    observations = _normalize(TimeWindow(date(2026, 10, 14), date(2026, 10, 15)))

    menut = {o.ts: o for o in observations if o.entity == "menut"}
    flagged = menut[datetime(2026, 10, 14, 8, tzinfo=UTC)]  # file row 14 Oct 09:00, validity -1
    assert (flagged.value, flagged.quality) == (None, Quality.MISSING)
    assert all(o.value is None or o.value >= 0 for o in observations)


def test_station_metadata_and_metric_names_match_open_meteo():
    observations = _normalize()

    foners = next(o for o in observations if o.entity == "foners")
    assert (foners.lat, foners.lon) == (pytest.approx(39.57125), pytest.approx(2.657028))
    assert {o.metric for o in observations if o.entity == "foners"} == {"pm10", "pm2_5", "carbon_monoxide"}


def test_no_station_in_the_region_is_an_error():
    connector = registry.load("eea_air_quality", http=RecordedEea())
    with pytest.raises(ConnectorError, match="no EEA air quality station"):
        connector.extract(WINDOW, Region("ibiza", 38.8, 1.2, 39.2, 1.7))
