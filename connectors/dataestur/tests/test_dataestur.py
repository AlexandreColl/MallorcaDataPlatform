import base64
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from connectors.dataestur.extractor import read_sheet
from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

# Real Dataestur sheets for August 2025 to August 2026 (hotel occupancy is published up to July 2026), and the
# empty sheet the API returns with HTTP 200 for a misspelt filter ("Baleares" instead of "Balears, Illes").
FIXTURES = Path(__file__).parent / "fixtures"
SHEETS = {
    "FRONTUR_DL": "frontur",
    "EGATUR_DL": "egatur",
    "EOH_PROV_DL": "hotels",
    "AENA_DESTINOS_DL": "airport",
}
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
# What a run on 2026-10-28 asks for: 365 days ending 62 days before yesterday, so September 2025 to August 2026.
WINDOW = TimeWindow(date(2025, 8, 27), date(2026, 8, 26))


class RecordedApi:
    def __init__(self, *, empty: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.empty = empty

    def get_bytes(self, url, params=None, headers=None):
        self.calls.append((url, params))
        name = "empty" if self.empty else SHEETS[url.rsplit("/", 1)[-1]]
        return (FIXTURES / f"{name}_2025-08_2026-08.xlsx").read_bytes()


def _normalize(window=WINDOW, http=None):
    connector = registry.load("dataestur", http=http or RecordedApi())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _value(observations, metric, month):
    return next(o.value for o in observations if o.metric == metric and o.ts.date() == month)


def test_one_sheet_per_table_lands_in_bronze_untouched():
    http = RecordedApi()
    connector = registry.load("dataestur", http=http)

    payloads = connector.extract(WINDOW, MALLORCA)

    assert [p.dataset for p in payloads] == ["frontur", "egatur", "hotels", "airport"]
    url, params = http.calls[0]
    assert url == "https://www.dataestur.es/API-SEGITTUR-v2/FRONTUR_DL"
    assert params == {
        "desde (año)": "2025",
        "desde (mes)": "8",
        "hasta (año)": "2026",
        "hasta (mes)": "8",
        "CCAA de destino": "Balears, Illes",
    }
    assert base64.b64decode(payloads[3].body) == (FIXTURES / "airport_2025-08_2026-08.xlsx").read_bytes()
    assert payloads[0].key == "dataestur/frontur/window=20250827_20260826/payload.json"


def test_the_sheet_reader_keeps_types_and_empty_cells():
    rows = read_sheet((FIXTURES / "airport_2025-08_2026-08.xlsx").read_bytes())

    assert rows[0] == {"AÑO": "2025", "MES": "8", "AEROPUERTO": "P. Mallorca", "PASAJEROS_POR_DESTINO": "4700495"}
    assert read_sheet((FIXTURES / "empty_2025-08_2026-08.xlsx").read_bytes()) == []


def test_countries_are_added_up_and_excursionists_left_out():
    observations = _normalize()

    # August 2026: 2.6 M international tourists (15 countries of residence), 4,065 M EUR spent.
    assert _value(observations, "international_tourists", date(2026, 8, 1)) == 2_596_458
    assert _value(observations, "international_tourist_spending", date(2026, 8, 1)) == pytest.approx(4_065_354_203.80)
    assert _value(observations, "international_tourist_nights", date(2026, 8, 1)) == 16_729_092


def test_hotel_occupancy_uses_the_total_row():
    observations = _normalize()

    assert _value(observations, "hotel_guests", date(2026, 7, 1)) == 2_050_150
    assert _value(observations, "hotel_bed_occupancy", date(2026, 7, 1)) == pytest.approx(87.37)
    # January: most hotels are closed.
    assert _value(observations, "hotels_open", date(2026, 1, 1)) == 146
    assert _value(observations, "hotels_open", date(2025, 9, 1)) == 1378


def test_one_value_per_month_starting_in_the_window():
    observations = _normalize()

    months = {o.metric: set() for o in observations}
    for o in observations:
        months[o.metric].add(o.ts.date())
    # August 2025 starts before the window: requested (whole months) but not loaded.
    assert months["airport_passengers"] == set(WINDOW.month_starts())
    assert len(WINDOW.month_starts()) == 12
    # Hotel occupancy is one month later: no August 2026 yet, so the gaps rule reports it.
    assert max(months["hotel_guests"]) == date(2026, 7, 1)
    assert len(observations) == 12 * 4 + 11 * 5  # airport, FRONTUR and EGATUR metrics; hotel metrics
    first = next(o for o in observations if o.metric == "airport_passengers")
    assert first.entity == "palma_airport"
    assert first.ts == datetime(2025, 8, 31, 22, tzinfo=UTC)  # 1 September 2025, local midnight (CEST)
    assert {o.quality for o in observations} == {Quality.OK}


def test_an_empty_sheet_is_an_error_not_an_empty_month():
    with pytest.raises(ConnectorError, match="empty sheet"):
        _normalize(http=RecordedApi(empty=True))


def test_other_regions_are_rejected():
    connector = registry.load("dataestur", http=RecordedApi())
    with pytest.raises(ConnectorError, match="do not cover"):
        connector.extract(WINDOW, Region("ibiza", 38.8, 1.2, 39.2, 1.7))
