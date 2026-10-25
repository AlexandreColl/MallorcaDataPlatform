import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded 2026-10-24: daily values of B278 (Palma airport), B228 (Palma port) and B051A (Port de Sóller) for
# 2026-10-19..21, and the answer for a day AEMET had not published yet.
WINDOW = TimeWindow(date(2026, 10, 19), date(2026, 10, 21))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
SECRETS = {"AEMET_API_KEY": "test-key"}


def _text(name):
    return (FIXTURES / name).read_bytes().decode("iso-8859-15")  # what requests decodes from AEMET's charset


class RecordedAemet:
    """Serves the recorded two-step answers: metadata JSON for API paths, then the data for the `datos` URL."""

    def __init__(self, daily_meta="daily_meta.json"):
        self.daily_meta = daily_meta
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, headers))
        if "inventarioestaciones" in url:
            return {"descripcion": "exito", "estado": 200, "datos": "https://datos.test/inventory"}
        meta = json.loads(_text(self.daily_meta))
        if "datos" in meta:
            meta["datos"] = "https://datos.test/daily"
        return meta

    def get_text(self, url, params=None, headers=None):
        self.calls.append((url, headers))
        return _text("inventory.json" if url.endswith("inventory") else "daily.json")


def _connector(http=None):
    return registry.load("aemet", http=http or RecordedAemet(), secrets=SECRETS)


def _normalize(http=None):
    connector = _connector(http)
    return [o for p in connector.extract(WINDOW, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _value(observations, station, metric, day):
    return next(o for o in observations if o.entity == station and o.metric == metric and o.ts.date() == day)


def test_two_step_requests_with_the_key_header_for_every_mallorca_station():
    http = RecordedAemet()

    payloads = _connector(http).extract(WINDOW, MALLORCA)

    assert [p.dataset for p in payloads] == ["stations", "daily", "daily"]  # 33 stations: groups of 25 and 8
    api_calls = [(url, headers) for url, headers in http.calls if url.startswith("https://opendata.aemet.es")]
    assert all(headers == {"api_key": "test-key"} for _, headers in api_calls)
    daily_path = payloads[1].request["path"]
    assert "fechaini/2026-10-19T00:00:00UTC/fechafin/2026-10-21T23:59:59UTC" in daily_path
    groups = [p.request["stations"] for p in payloads[1:]]
    assert [len(g) for g in groups] == [25, 8]  # 33 Mallorca stations (Cabrera, Menorca, Ibiza are out)
    assert [p.partition for p in payloads[1:]] == ["B013X-B640X", "B644B-B780X"]
    assert len({p.key for p in payloads}) == 3
    stations = groups[0]
    assert {"B278", "B228", "B051A"} <= set(stations)
    assert stations["B278"]["lat"] == pytest.approx(39.560833)  # 393339N
    assert "test-key" not in json.dumps([p.request for p in payloads])  # the key never lands in bronze


def test_values_are_parsed_and_converted():
    observations = _normalize()
    oct19 = date(2026, 10, 19)

    assert _value(observations, "B228", "precipitation_sum", oct19).value == pytest.approx(57.4)  # the 19 Oct storm
    assert _value(observations, "B278", "temperature_2m_mean", oct19).value == pytest.approx(20.6)
    assert _value(observations, "B051A", "wind_gusts_10m_max", oct19).value == pytest.approx(23.9 * 3.6)
    point = _value(observations, "B278", "temperature_2m_mean", oct19)
    assert point.ts == datetime(2026, 10, 18, 22, tzinfo=UTC)  # local midnight (CEST)
    assert {o.quality for o in observations} == {Quality.OK}


def test_variables_a_station_does_not_measure_are_skipped():
    observations = _normalize()

    sunshine = {o.entity for o in observations if o.metric == "sunshine_duration"}
    assert sunshine == {"B228", "B278"}  # Port de Sóller has no sunshine recorder
    assert len(observations) == 3 * (10 + 10 + 7)  # days x variables per station


def test_unpublished_days_are_an_empty_answer():
    connector = _connector(RecordedAemet(daily_meta="daily_meta_no_data.json"))

    payloads = connector.extract(WINDOW, MALLORCA)

    assert payloads[1].body == "[]"
    assert list(connector.normalize(payloads[1], MALLORCA)) == []


def test_aemet_errors_are_reported():
    class Unauthorized(RecordedAemet):
        def get_json(self, url, params=None, headers=None):
            return {"descripcion": "API key invalido", "estado": 401}

    with pytest.raises(ConnectorError, match="AEMET estado 401"):
        _connector(Unauthorized()).extract(WINDOW, MALLORCA)


def test_window_ends_three_days_before_yesterday():
    config = registry.discover()["aemet"]

    assert config.window(1, today=date(2026, 10, 24)) == TimeWindow(date(2026, 10, 20), date(2026, 10, 20))
