import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))
# Bounding box around Palma: contains ParcBit and the Bahía de Palma buoy, not Cala Millor or Muro.
PALMA = Region("palma_area", 39.40, 2.50, 39.70, 2.80)
# Only Parc Bit: the archive tests need its recordings alone.
PARCBIT = Region("parcbit_area", 39.60, 2.60, 39.70, 2.66)
FOLDER_TO_STATION = {
    "station_parcbit": "parcbit",
    "buoy_bahiadepalma-scb_met029": "bahia_de_palma_buoy",
    "buoy_bahiadepalma-scb_wave006": "bahia_de_palma_waves",
}
H00 = datetime(2026, 10, 23, 0, tzinfo=UTC)


class RecordedThredds:
    """Serves the recorded THREDDS catalog, metadata and CSV responses."""

    def __init__(self, csv_overrides: dict[str, str] | None = None, no_features: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.csv_overrides = csv_overrides or {}
        self.no_features = no_features  # archive months that answer "No features in the requested subset"

    def get_text(self, url, params=None, headers=None):
        self.calls.append((url, params))
        station = next(s for folder, s in FOLDER_TO_STATION.items() if folder in url)
        year = re.search(r"/L1/(\d{4})/catalog\.xml$", url)
        month = re.search(r"_L1_(\d{4}-\d{2})\.nc$", url)
        if year:
            name = f"{station}_{year.group(1)}_catalog.xml"
        elif url.endswith("catalog.xml"):
            name = f"{station}_catalog.xml"
        elif "/ncml/" in url:
            name = f"{station}_ncml.xml"
        elif month and month.group(1) in self.no_features:
            raise _http_error(400, "No features are in the requested subset")
        elif month:
            name = f"{station}_{month.group(1)}.csv"
        else:
            if station in self.csv_overrides:
                return self.csv_overrides[station]
            name = f"{station}.csv"
        if not (FIXTURES / name).exists():
            raise _http_error(404, "Not Found")
        return (FIXTURES / name).read_text(encoding="utf-8")


def _http_error(status: int, text: str) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()
    return requests.HTTPError(f"{status}", response=response)


def _connector(http=None):
    return registry.load("socib", http=http or RecordedThredds())


def _by_key(observations):
    return {(o.entity, o.metric, o.ts): o for o in observations}


def _normalize_all(connector, window=WINDOW, region=PALMA):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def test_extract_one_csv_per_station_in_the_region():
    connector = _connector()

    payloads = connector.extract(WINDOW, PALMA)

    assert [(p.dataset, p.partition) for p in payloads] == [
        ("weather", "parcbit"),
        ("weather", "bahia_de_palma_buoy"),
        ("waves", "bahia_de_palma_buoy"),  # the same buoy, its wave recorder
    ]
    assert len({p.key for p in payloads}) == 3
    assert payloads[0].key == "socib/weather/partition=parcbit/window=20261023_20261023/payload.json"
    params = payloads[0].request["params"]
    assert params["time_start"] == "2026-10-23T00:00:00Z"
    assert params["time_end"] == "2026-10-23T23:59:59Z"
    assert {"AIR_TEM", "QC_AIR_TEM", "WIN_SPE_GUS", "QC_WIN_SPE_GUS"} <= set(params["var"])


def test_the_newest_deployment_file_is_used():
    connector = _connector()

    payloads = connector.extract(WINDOW, PALMA)

    buoy_url = payloads[1].request["url"]
    assert buoy_url.endswith("/dep0002_buoy-bahiadepalma_scb-met029_L1_latest.nc")  # catalog lists dep0001 too
    # The point service: the plain /ncss/ path answers 404 since November 2026.
    assert buoy_url.startswith("https://thredds.socib.es/thredds/ncss/point/mooring/")


def test_minute_samples_are_aggregated_to_hourly_values():
    observations = _normalize_all(_connector())
    parcbit = _by_key(o for o in observations if o.entity == "parcbit")

    assert len(parcbit) == 24 * 5  # 24 hours x 5 metrics
    assert parcbit["parcbit", "temperature_2m", H00].value == pytest.approx(15.4567, abs=1e-3)
    assert parcbit["parcbit", "wind_speed_10m", H00].value == pytest.approx(6.714, abs=1e-3)  # m/s -> km/h
    assert parcbit["parcbit", "wind_gusts_10m", H00].value == pytest.approx(10.44, abs=1e-3)  # hourly max
    assert {o.quality for o in parcbit.values()} == {Quality.OK}
    assert {o.unit for o in parcbit.values() if o.metric == "temperature_2m"} == {"degC"}


def test_hours_with_few_good_samples_are_suspect():
    observations = _normalize_all(_connector())
    buoy = _by_key(o for o in observations if o.entity == "bahia_de_palma_buoy")

    # 00h: 4 of the 6 ten-minute samples are NaN with QC 9 -> 2/6 good, below the 50 % threshold.
    assert buoy["bahia_de_palma_buoy", "temperature_2m", H00].quality == Quality.SUSPECT
    # 11h: 3 of 6 missing -> exactly 50 % good, still ok.
    assert buoy["bahia_de_palma_buoy", "temperature_2m", H00.replace(hour=11)].quality == Quality.OK
    suspect_hours = {o.ts.hour for o in buoy.values() if o.quality == Quality.SUSPECT}
    assert suspect_hours == {0}


def test_samples_flagged_bad_by_the_source_are_excluded():
    lines = (FIXTURES / "parcbit.csv").read_text(encoding="utf-8").splitlines()
    header, rows = lines[0], lines[1:]
    tampered = []
    for i, row in enumerate(rows):
        cells = row.split(",")
        if i < 40:  # first 40 minutes of 00h: absurd value flagged bad (QC 4) by the source
            cells[4], cells[5] = "99.9", "4"
        tampered.append(",".join(cells))
    connector = _connector(RecordedThredds({"parcbit": "\n".join([header, *tampered])}))

    temperature = _by_key(_normalize_all(connector))["parcbit", "temperature_2m", H00]

    assert temperature.quality == Quality.SUSPECT  # 20/60 good samples
    assert temperature.value < 30  # the 99.9 readings never reach the hourly mean


def test_days_before_the_latest_file_come_from_the_monthly_archive():
    payloads = _connector().extract(TimeWindow(date(2026, 8, 31), date(2026, 9, 1)), PARCBIT)

    assert [(p.request["file"], p.partition) for p in payloads] == [
        ("2026-08_dep0001", "parcbit-2026-08_dep0001"),
        ("latest", "parcbit"),
    ]
    archive, latest = (p.request for p in payloads)
    assert archive["url"].endswith("/L1/2026/dep0001_station-parcbit_scb-met023_L1_2026-08.nc")
    assert (archive["params"]["time_start"], archive["params"]["time_end"]) == (
        "2026-08-31T00:00:00Z",
        "2026-08-31T23:59:59Z",
    )
    assert latest["params"]["time_start"] == "2026-09-01T00:00:00Z"  # the latest file starts there


def test_an_archive_day_is_aggregated_like_a_recent_one():
    connector = _connector()
    window = TimeWindow(date(2026, 8, 31), date(2026, 8, 31))

    observations = _by_key(_normalize_all(connector, window, PARCBIT))

    assert len(observations) == 24 * 5
    first = observations["parcbit", "temperature_2m", datetime(2026, 8, 31, tzinfo=UTC)]
    assert first.quality == Quality.OK
    assert 20 < first.value < 25
    assert not any("/L1/2025/" in url for url, _ in connector.http.calls)  # only the years of the window


def test_a_month_without_samples_on_those_days_is_skipped():
    http = RecordedThredds(no_features=frozenset({"2026-08"}))

    payloads = registry.load("socib", http=http).extract(TimeWindow(date(2026, 8, 31), date(2026, 9, 1)), PARCBIT)

    assert [p.request["file"] for p in payloads] == ["latest"]


def test_a_year_the_station_did_not_exist_gives_nothing():
    payloads = _connector().extract(TimeWindow(date(2024, 12, 31), date(2025, 1, 1)), PARCBIT)

    assert payloads == []  # no recorded 2024 or 2025 catalog: they answer 404


def test_wave_heights_are_hourly_from_the_half_hour_records():
    waves = _by_key(o for o in _normalize_all(_connector()) if o.metric.startswith("wave_"))

    assert {o.entity for o in waves.values()} == {"bahia_de_palma_buoy"}
    assert len(waves) == 24 * 2
    # 00:00 has QC 9 (missing), 00:30 is good: the hour takes the one good record, half of them, still ok.
    assert waves["bahia_de_palma_buoy", "wave_height", H00].value == pytest.approx(0.31)
    assert waves["bahia_de_palma_buoy", "wave_height", H00].quality == Quality.OK
    assert waves["bahia_de_palma_buoy", "wave_height_max", H00].value == pytest.approx(0.52)
    assert {o.unit for o in waves.values()} == {"m"}


def test_region_without_stations_is_rejected():
    ibiza = Region("ibiza", 38.8, 1.1, 39.2, 1.6)

    with pytest.raises(ConnectorError, match="no SOCIB station"):
        _connector().extract(WINDOW, ibiza)


def test_stations_are_named_from_the_config():
    connector = _connector()

    names = {e.entity: e.name for p in connector.extract(WINDOW, PALMA) for e in connector.describe(p, PALMA)}

    assert names == {"parcbit": "Parc Bit (Palma)", "bahia_de_palma_buoy": "Boya de la bahía de Palma"}
