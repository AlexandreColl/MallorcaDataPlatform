import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Location, Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_BY_PATH = {
    "demanda/evolucion": "demand.json",
    "generacion/estructura-generacion": "generation.json",
    "generacion/no-renovables-detalle-emisiones-CO2": "emissions.json",
}
WINDOW = TimeWindow(date(2026, 10, 22), date(2026, 10, 23))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50, (Location("palma", 39.5696, 2.6502),))


class RecordedHttp:
    """Serves the responses recorded in tests/fixtures instead of calling the API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        name = next(f for path, f in FIXTURE_BY_PATH.items() if url.endswith(path))
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def connector():
    return registry.load("redata", http=RecordedHttp())


def _observations(connector, window=WINDOW):
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def test_extract_requests_each_dataset_with_its_granularity(connector):
    payloads = connector.extract(WINDOW, MALLORCA)

    assert [p.dataset for p in payloads] == ["demand", "generation", "emissions"]
    by_path = {url.rsplit("/datos/", 1)[1]: params for url, params in connector.http.calls}
    assert by_path["demanda/evolucion"]["time_trunc"] == "hour"
    assert by_path["generacion/estructura-generacion"]["time_trunc"] == "day"
    params = by_path["demanda/evolucion"]
    assert params["start_date"] == "2026-10-22T00:00"
    assert params["end_date"] == "2026-10-23T23:59"
    assert params["geo_ids"] == "8743"
    assert all(url.startswith("https://apidatos.ree.es/en/datos/") for url, _ in connector.http.calls)


def test_long_hourly_windows_are_split_into_28_day_requests(connector):
    window = TimeWindow(date(2026, 7, 1), date(2026, 9, 8))  # 70 days

    payloads = connector.extract(window, MALLORCA)

    demand = [p.window for p in payloads if p.dataset == "demand"]
    assert [w.n_days for w in demand] == [28, 28, 14]
    assert demand[0].start == window.start
    assert demand[-1].end == window.end
    assert len({p.key for p in payloads}) == len(payloads)  # one bronze object per chunk
    assert [p.window for p in payloads if p.dataset == "generation"] == [window]


def test_normalize_converts_local_timestamps_to_utc(connector):
    demand = [o for o in _observations(connector) if o.metric == "electricity_demand"]

    assert len(demand) == 48  # 2 days x 24 hours
    # REData uses local (CEST, +02:00) days: local midnight is 22:00 UTC the day before.
    assert min(o.ts for o in demand) == datetime(2026, 10, 21, 22, tzinfo=UTC)
    assert all(o.ts.tzinfo is UTC for o in demand)
    assert {o.entity for o in demand} == {"baleares"}
    assert {o.unit for o in demand} == {"MWh"}


def test_every_series_is_mapped_or_explicitly_ignored(connector, caplog):
    with caplog.at_level(logging.WARNING):
        observations = _observations(connector)

    assert "unmapped series" not in caplog.text
    generation = {o.metric for o in observations if o.metric.startswith("generation_")}
    assert generation == {m.name for m in connector.config.metrics_for("generation")}
    emissions = [o for o in observations if o.metric.startswith("co2_")]
    assert {o.metric for o in emissions} == {"co2_emissions", "co2_intensity"}
    assert len(emissions) == 4  # 2 days x 2 metrics, per-technology detail ignored


def test_unknown_series_is_reported_not_dropped_silently(connector, caplog):
    payload = connector.extract(WINDOW, MALLORCA)[1]
    payload.body["included"][0]["attributes"]["title"] = "Offshore wind"

    with caplog.at_level(logging.WARNING):
        metrics = {o.metric for o in connector.normalize(payload, MALLORCA)}

    assert "unmapped series 'Offshore wind'" in caplog.text
    assert "generation_diesel_engines" not in metrics


def test_null_values_are_missing(connector):
    payload = connector.extract(WINDOW, MALLORCA)[0]
    payload.body["included"][0]["attributes"]["values"][5]["value"] = None

    missing = [o for o in connector.normalize(payload, MALLORCA) if o.quality == Quality.MISSING]

    assert len(missing) == 1
    assert missing[0].value is None


def test_api_errors_are_raised(connector):
    payload = connector.extract(WINDOW, MALLORCA)[0]
    error = type(payload)(payload.source, payload.dataset, payload.window, payload.request, {"errors": [{}]})

    with pytest.raises(ConnectorError, match="REData error"):
        list(connector.normalize(error, MALLORCA))


def test_regions_outside_the_balearic_system_are_rejected(connector):
    madrid = Region("madrid", 40.0, -4.0, 41.0, -3.0)

    with pytest.raises(ConnectorError, match="does not cover region 'madrid'"):
        connector.extract(WINDOW, madrid)
