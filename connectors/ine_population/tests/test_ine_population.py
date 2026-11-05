import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded 2026-11-05 from DATOS_TABLA/2860?tip=AM&date=20240101:20251231, cut down to the Balearic total and five
# municipalities: Alaró (07001), Escorca (07019) and Palma (07040) in Mallorca, Alaior (07002, Menorca) and
# Eivissa (07026, Ibiza).
WINDOW = TimeWindow(date(2024, 1, 1), date(2025, 12, 31))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)


class RecordedIne:
    def __init__(self, body=None):
        self.body = body if body is not None else json.loads((FIXTURES / "2860_2024_2025.json").read_text("utf-8"))
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        return self.body


def _observations(window=WINDOW, http=None):
    connector = registry.load("ine_population", http=http or RecordedIne())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def test_one_request_for_the_years_of_the_window_with_the_series_metadata():
    http = RecordedIne()

    payloads = registry.load("ine_population", http=http).extract(WINDOW, MALLORCA)

    assert [p.dataset for p in payloads] == ["municipalities"]
    assert http.calls == [
        ("https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/2860", {"tip": "AM", "date": "20240101:20251231"})
    ]


def test_only_the_municipalities_of_mallorca_and_never_the_balearic_total():
    observations = _observations()

    assert {o.entity for o in observations} == {"07001", "07019", "07040"}  # not Alaior, Eivissa or the total
    assert {o.metric for o in observations} == {"population", "population_men", "population_women"}
    assert len(observations) == 3 * 3 * 2  # municipalities x sexes x years
    palma = next(o for o in observations if o.entity == "07040")
    assert (palma.lat, palma.lon) == pytest.approx((39.5831, 2.6988))  # centre of its IGN boundary


def test_values_are_stamped_on_the_first_of_january_at_local_midnight():
    observations = _observations()

    def value(entity, metric, year):
        ts = datetime(year - 1, 12, 31, 23, tzinfo=UTC)  # 1 January 00:00 in Madrid (CET)
        return next(o.value for o in observations if (o.entity, o.metric, o.ts) == (entity, metric, ts))

    assert value("07040", "population", 2025) == 434786
    assert value("07040", "population_men", 2025) + value("07040", "population_women", 2025) == 434786
    assert value("07019", "population", 2024) == 203  # Escorca, the smallest municipality
    assert {o.unit for o in observations} == {"people"}


def test_years_whose_first_of_january_is_outside_the_window_are_left_out():
    observations = _observations(TimeWindow(date(2024, 6, 1), date(2025, 6, 1)))

    assert {o.ts.astimezone(UTC).year + 1 for o in observations} == {2025}


def test_a_run_reads_the_last_three_published_years():
    config = registry.load("ine_population").config

    window = config.window(1, today=date(2026, 11, 5))

    assert [d.year for d in window.year_starts()] == [2023, 2024, 2025]  # 1 Jan 2026 is published in December
    assert [d.year for d in config.window(1, today=date(2026, 12, 20)).year_starts()] == [2024, 2025, 2026]


def test_a_missing_value_is_kept_as_missing():
    body = json.loads((FIXTURES / "2860_2024_2025.json").read_text("utf-8"))
    for series in body:
        for point in series["Data"]:
            point["Valor"] = None

    observations = _observations(http=RecordedIne(body))

    assert observations
    assert {(o.value, o.quality) for o in observations} == {(None, Quality.MISSING)}


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ({"status": "error"}, "unexpected answer"),
        ([{"COD": "X", "Nombre": "Balears, Illes. Total", "MetaData": [], "Data": []}], "no municipal series"),
    ],
)
def test_a_bad_answer_fails(body, match):
    with pytest.raises(ConnectorError, match=match):
        _observations(http=RecordedIne(body))
