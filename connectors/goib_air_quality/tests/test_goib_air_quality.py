import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from connectors.goib_air_quality import extractor
from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

# Real files of the catalogue cut to a few days, in the three layouts it publishes:
# - Foners history: ";" and month-first dates (1-3 July 2019); the EEA verified file has the same hours.
# - Cases de Menut history: ";" and day-first dates, ozone only (1-3 July 2019).
# - Hospital Joan March 2020: ";", day-first, PERIODE without accent (1-2 July 2020).
# - Foners 2021: "," with a quoted "PM2,5" column (1-2 January 2021).
# The package_show answer of Foners is real; the other datasets get the same shape pointing to their fixture.
FIXTURES = Path(__file__).parent / "fixtures"
PREFIX = "mesuraments-estacio-control-qualitat-aire-illes-balears-estacio-"
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
JULY_2019 = TimeWindow(date(2019, 7, 2), date(2019, 7, 2))


class RecordedCatalogue:
    def __init__(self) -> None:
        self.datasets: list[str] = []
        self.downloads: list[str] = []

    def get_json(self, url, params=None, headers=None):
        name = params["id"]
        self.datasets.append(name)
        if name == f"{PREFIX}foners-mallorca":
            return json.loads((FIXTURES / "package_show_foners.json").read_text(encoding="utf-8"))
        return {"result": {"resources": [{"format": "CSV", "url": f"https://catalogue.test/{name}.csv"}]}}

    def get_bytes(self, url, params=None, headers=None):
        self.downloads.append(url)
        name = url.rsplit("/", 1)[-1]
        if not name.startswith(PREFIX):  # the real resource URL of Foners ends in its own file name
            name = f"{PREFIX}foners-mallorca.csv"
        path = FIXTURES / name
        # Stations without a fixture: a header and no rows.
        return path.read_bytes() if path.exists() else b"\xef\xbb\xbfDATA_HI;PERIODE_HI;NO2_HI;FL_NO2\n"


@pytest.fixture(autouse=True)
def _no_download_cache():
    extractor._DOWNLOADS.clear()
    yield
    extractor._DOWNLOADS.clear()


def _normalize(window=JULY_2019, http=None):
    connector = registry.load("goib_air_quality", http=http or RecordedCatalogue())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _value(observations, entity, metric, ts):
    return next(o.value for o in observations if o.entity == entity and o.metric == metric and o.ts == ts)


def test_history_only_and_off_the_daily_run():
    config = registry.discover()["goib_air_quality"]

    assert config.enabled is False
    assert "goib_air_quality" not in registry.runnable_names(env={})


def test_only_the_files_overlapping_the_window_are_downloaded():
    http = RecordedCatalogue()
    connector = registry.load("goib_air_quality", http=http)

    payloads = connector.extract(JULY_2019, MALLORCA)

    # 2019 lives in the history files only: no 2020 or 2021 dataset is asked for.
    assert all(not name.endswith(("-2020", "-2021")) for name in http.datasets)
    assert len(payloads) == 11
    foners = next(p for p in payloads if p.partition == "foners")
    assert foners.request["dataset"] == f"{PREFIX}foners-mallorca"
    assert foners.request["url"].startswith("https://intranet.caib.es/opendatacataleg/")
    assert foners.key == "goib_air_quality/hourly/partition=foners/window=20190702_20190702/payload.json"


def test_bronze_keeps_the_raw_lines_of_the_window_days():
    connector = registry.load("goib_air_quality", http=RecordedCatalogue())

    foners = next(p for p in connector.extract(JULY_2019, MALLORCA) if p.partition == "foners")

    raw = (FIXTURES / f"{PREFIX}foners-mallorca.csv").read_text(encoding="utf-8-sig").splitlines(keepends=True)
    assert foners.body == raw[0] + "".join(line for line in raw[1:] if line.startswith("07/02/2019"))
    assert foners.request["lines"] == 24
    assert foners.request["bytes"] == (FIXTURES / f"{PREFIX}foners-mallorca.csv").stat().st_size


def test_periods_are_hours_starting_in_utc_plus_one():
    observations = _normalize()

    # Period 1 of 2 July (01:00-02:00 UTC+01) is 00:00 UTC; the EEA verified file has the same values.
    assert _value(observations, "foners", "nitrogen_dioxide", datetime(2019, 7, 2, 0, tzinfo=UTC)) == 25.0
    assert _value(observations, "foners", "nitrogen_dioxide", datetime(2019, 7, 2, 5, tzinfo=UTC)) == 80.0
    # Period 24 is midnight UTC+01: the last hour of the UTC day.
    assert _value(observations, "foners", "nitrogen_dioxide", datetime(2019, 7, 2, 23, tzinfo=UTC)) == 29.0
    hours = {o.ts for o in observations if o.entity == "foners" and o.metric == "nitrogen_dioxide"}
    assert len(hours) == 24
    assert min(hours) == datetime(2019, 7, 2, tzinfo=UTC)


def test_only_the_valid_flag_is_a_value():
    observations = _normalize()

    # Period 7 is flagged C (no value) and period 8 N (not valid).
    for hour in (6, 7):
        obs = next(
            o
            for o in observations
            if o.entity == "foners"
            and o.metric == "nitrogen_dioxide"
            and o.ts == datetime(2019, 7, 2, hour, tzinfo=UTC)
        )
        assert obs.value is None
        assert obs.quality is Quality.MISSING


def test_co_comes_in_mg_and_is_stored_in_ug():
    observations = _normalize()

    assert _value(observations, "foners", "carbon_monoxide", datetime(2019, 7, 2, 5, tzinfo=UTC)) == 500.0


def test_day_first_files_and_ozone_only_stations():
    observations = _normalize()

    menut = {o.metric for o in observations if o.entity == "menut"}
    assert menut == {"ozone"}
    # 03/07/2019 is the 3rd of July (outside the window), not the 7th of March.
    assert all(o.ts.date() == date(2019, 7, 2) for o in observations if o.entity == "menut")
    assert len([o for o in observations if o.entity == "menut"]) == 24


def test_yearly_files_with_comma_delimiter_and_quoted_columns():
    window = TimeWindow(date(2021, 1, 1), date(2021, 1, 1))
    http = RecordedCatalogue()

    observations = _normalize(window, http)

    assert f"{PREFIX}foners-mallorca-2021" in http.datasets
    # Sa Vinyeta (Inca) has no yearly files.
    assert not any(name.startswith(f"{PREFIX}sa-vinyeta-d-inca-mallorca-") for name in http.datasets)
    assert _value(observations, "foners", "ozone", datetime(2021, 1, 1, 0, tzinfo=UTC)) == 66.0
    metrics = {o.metric for o in observations if o.entity == "foners"}
    assert {"nitrogen_dioxide", "ozone", "pm10", "pm2_5", "sulphur_dioxide", "carbon_monoxide"} == metrics


def test_2020_files_without_accent_in_the_period_column():
    window = TimeWindow(date(2020, 7, 1), date(2020, 7, 1))

    observations = _normalize(window)

    hjm = [o for o in observations if o.entity == "hospital_joan_march" and o.metric == "ozone"]
    assert len(hjm) == 24
    assert all(o.ts.date() == date(2020, 7, 1) for o in hjm)


def test_downloads_once_per_process():
    http = RecordedCatalogue()
    connector = registry.load("goib_air_quality", http=http)

    connector.extract(TimeWindow(date(2019, 7, 1), date(2019, 7, 1)), MALLORCA)
    connector.extract(TimeWindow(date(2019, 7, 2), date(2019, 7, 2)), MALLORCA)

    assert len(http.downloads) == len(set(http.downloads)) == 11


def test_window_after_the_history_fails():
    connector = registry.load("goib_air_quality", http=RecordedCatalogue())

    with pytest.raises(ConnectorError, match="no file"):
        connector.extract(TimeWindow(date(2022, 1, 1), date(2022, 1, 2)), MALLORCA)
