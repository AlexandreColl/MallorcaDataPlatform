from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))
# Bounding box around Palma: contains ParcBit and the Bahía de Palma buoy, not Cala Millor or Muro.
PALMA = Region("palma_area", 39.40, 2.50, 39.70, 2.80)
FOLDER_TO_STATION = {"station_parcbit": "parcbit", "buoy_bahiadepalma": "bahia_de_palma_buoy"}
H00 = datetime(2026, 10, 23, 0, tzinfo=UTC)


class RecordedThredds:
    """Serves the recorded THREDDS catalog, metadata and CSV responses."""

    def __init__(self, csv_overrides: dict[str, str] | None = None) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.csv_overrides = csv_overrides or {}

    def get_text(self, url, params=None, headers=None):
        self.calls.append((url, params))
        station = next(s for folder, s in FOLDER_TO_STATION.items() if folder in url)
        if url.endswith("catalog.xml"):
            name = f"{station}_catalog.xml"
        elif url.endswith("dataset.xml"):
            name = f"{station}_dataset.xml"
        else:
            if station in self.csv_overrides:
                return self.csv_overrides[station]
            name = f"{station}.csv"
        return (FIXTURES / name).read_text(encoding="utf-8")


def _connector(http=None):
    return registry.load("socib", http=http or RecordedThredds())


def _by_key(observations):
    return {(o.entity, o.metric, o.ts): o for o in observations}


def _normalize_all(connector, window=WINDOW):
    return [o for p in connector.extract(window, PALMA) for o in connector.normalize(p, PALMA)]


def test_extract_one_csv_per_station_in_the_region():
    connector = _connector()

    payloads = connector.extract(WINDOW, PALMA)

    assert [p.partition for p in payloads] == ["parcbit", "bahia_de_palma_buoy"]
    assert len({p.key for p in payloads}) == 2
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


def test_window_older_than_the_latest_file_is_rejected_with_a_hint():
    window = TimeWindow(date(2026, 8, 20), date(2026, 10, 23))

    with pytest.raises(ConnectorError, match=r"starts on 2026-09-01; request at most 53 days"):
        _connector().extract(window, PALMA)


def test_region_without_stations_is_rejected():
    ibiza = Region("ibiza", 38.8, 1.1, 39.2, 1.6)

    with pytest.raises(ConnectorError, match="no SOCIB station"):
        _connector().extract(WINDOW, ibiza)
