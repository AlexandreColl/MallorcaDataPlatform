"""Náyade against its pages recorded on 2026-11-28 for one municipality, Pollença.

The whole island is 53 list pages and two pages per bathing water (some 3 MB), so the fixtures keep the six bathing
waters of Pollença only: a single point (Formentor), several points (Albercuix and Tamarells, three each) and the
restrictions of August 2026 at Tamarells. The tests load the connector with that one municipality, as it was
recorded. Window 2023-01-01..2026-11-27: the four seasons Náyade showed.
"""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from connectors.nayade.extractor import parse_samples, point_code, title_case, utm_to_latlon
from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import RawPayload, TimeWindow
from core.quality.engine import GapRule, rules_for

FIXTURES = Path(__file__).parent / "fixtures"
POLLENCA = "07042"


def _connector(http=None):
    connector = registry.load("nayade", http=http or RecordedHttp(FIXTURES))
    options = dict(connector.config.options)
    options["municipalities"] = {POLLENCA: options["municipalities"][POLLENCA]}
    connector.config = dataclasses.replace(connector.config, options=options)
    return connector


@pytest.fixture
def recorded():
    """The connector answering from the recordings, with the window and region they were made for."""
    manifest = Manifest.load(FIXTURES)
    return _connector(), manifest.window, load_region(manifest.region)


@pytest.fixture
def observations(recorded):
    connector, window, region = recorded
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def _value(observations, entity, metric, day):
    matches = [o.value for o in observations if (o.entity, o.metric) == (entity, metric) and o.ts.date() == day]
    assert matches, (entity, metric, day)
    return matches[0]


def test_one_payload_with_every_bathing_water_of_the_municipality(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.dataset for p in payloads] == ["bathing_waters"]
    zones = json.loads(payloads[0].body)
    assert sorted(z["zone"] for z in zones) == ["1034", "1035", "1036", "1037", "1038", "1039"]
    assert {z["municipality"] for z in zones} == {POLLENCA}
    # bronze keeps the pages from their tabs on: the scripts and menus above them are the same on every page
    assert all(z["samples"].startswith("<table") and "function enviar" not in z["samples"] for z in zones)


def test_every_observation_fits_the_connector_yaml(recorded, observations):
    connector, window, _ = recorded

    for o in observations:
        spec = connector.config.metrics[o.metric]
        assert o.source == "nayade"
        assert o.unit == spec.unit
        assert window.start <= o.ts.date() <= window.end
        assert spec.min <= o.value <= spec.max, o
        assert 39.8 < o.lat < 40.0, o  # Pollença
        assert 2.9 < o.lon < 3.3, o


def test_every_sampling_point_is_an_entity_with_the_name_of_its_bathing_water(recorded):
    connector, window, region = recorded

    payload = connector.extract(window, region)[0]
    names = {e.entity: e.name for e in connector.describe(payload, region)}

    assert len(names) == 10  # six bathing waters, two of them with three points
    assert names["07042_1034_PM1"] == "Playa Formentor"  # one point: the name of the bathing water alone
    assert names["07042_1038_PM2"] == "Playa dels Tamarells (Port de Pollença) (PM2)"
    assert names["07042_1039_PM1"] == "Playa Llenaire (Port de Pollença)"  # "LLENAIRE(PORT DE POLLENÇA)"


def test_samples_of_four_seasons_with_their_results_and_advice(observations):
    seasons = {o.ts.year for o in observations if o.metric == "e_coli"}
    tamarells = "07042_1038_PM1"

    assert seasons == {2023, 2024, 2025, 2026}
    assert _value(observations, tamarells, "e_coli", date(2026, 8, 24)) == 1291
    assert _value(observations, tamarells, "enterococci", date(2026, 8, 24)) == 52
    assert _value(observations, tamarells, "bathing_advice", date(2026, 8, 24)) == 1  # bathing not advised
    assert _value(observations, "07042_1038_PM2", "bathing_advice", date(2026, 8, 24)) == 0  # 86 E. coli: fit


def test_a_restriction_is_its_length_and_level_on_its_opening_day(observations):
    tamarells = "07042_1038_PM1"

    assert _value(observations, tamarells, "incident_days", date(2026, 8, 24)) == 2  # 24 to 26 August
    assert _value(observations, tamarells, "incident_level", date(2026, 8, 24)) == 1


def test_values_are_stamped_on_the_sampling_day_at_local_midnight(observations):
    o = next(o for o in observations if o.entity == "07042_1038_PM1" and o.metric == "e_coli")

    assert o.ts.utcoffset().total_seconds() in {3600, 7200}
    assert (o.ts.hour, o.ts.minute) == (0, 0)


def test_the_window_filters_the_four_seasons(recorded):
    connector, _, region = recorded
    summer = TimeWindow(date(2026, 8, 1), date(2026, 8, 31))

    payload = connector.extract(summer, region)[0]
    days = {o.ts.date() for o in connector.normalize(payload, region)}

    assert days
    assert all(date(2026, 8, 1) <= d <= date(2026, 8, 31) for d in days)


def test_no_gaps_rule_for_the_months_without_samples(recorded):
    connector, window, _ = recorded

    assert connector.config.is_event_source
    assert not any(isinstance(rule, GapRule) for rule in rules_for(connector.config, window))


def test_an_unknown_advice_fails_instead_of_being_dropped(recorded):
    connector, window, region = recorded
    payload = connector.extract(window, region)[0]
    zones = json.loads(payload.body)
    zones[0]["samples"] = zones[0]["samples"].replace("Zona Apta para el ba", "Zona cerrada por obras para el ba", 1)
    changed = RawPayload("nayade", "bathing_waters", window, {}, json.dumps(zones))

    with pytest.raises(ConnectorError, match="unknown advice"):
        list(connector.normalize(changed, region))


def test_a_page_without_its_tabs_fails(recorded):
    _, window, region = recorded

    class Moved:
        def get_text(self, url, params=None, headers=None):
            del params, headers
            return "<a href=\"javascript:verZona('1')\">x</a>" if "Lista" in url else "<html>maintenance</html>"

    with pytest.raises(ConnectorError, match="without its content"):
        _connector(Moved()).extract(window, region)


def test_a_region_without_bathing_waters_fails(recorded):
    _, window, _ = recorded

    class Empty:
        def get_text(self, url, params=None, headers=None):
            del url, params, headers
            return "<html>no zones</html>"

    with pytest.raises(ConnectorError, match="no bathing water"):
        _connector(Empty()).extract(window, load_region("mallorca"))


def test_two_samples_the_same_day_keep_the_worst_value():
    html = """<table><tr><td>Punto Muestreo:</td><td>PLAYA X PM1</td></tr>
    <tr><td>Muestreos:</td></tr>
    <tr><td>02/07/2026</td><td>30 NMP/100 mL</td><td>500 UFC/100 mL</td><td>Zona Apta para el baño</td></tr>
    <tr><td>02/07/2026</td><td>900 NMP/100 mL</td><td>10 NMP/100 mL</td><td>Recomendación de no baño</td></tr>
    </table>"""
    location = """<table class="tituloMenuActivo"><tr><td>Zona Agua Baño:</td><td>PLAYA X</td></tr>
    <tr><td>Denominación:</td><td>PLAYA X PM1</td></tr>
    <tr><td>X:</td><td>500000</td><td>Y:</td><td>4400000</td><td>Huso:</td><td>31</td></tr></table>"""
    connector = _connector()
    body = json.dumps([{"municipality": POLLENCA, "zone": "9", "location": location, "samples": html}])
    window = TimeWindow(date(2026, 7, 1), date(2026, 7, 31))
    payload = RawPayload("nayade", "bathing_waters", window, {}, body)

    values = {o.metric: o.value for o in connector.normalize(payload, load_region("mallorca"))}

    assert parse_samples(html)["PLAYA X PM1"]["samples"][1][1] == "900 NMP/100 mL"
    assert values == {"e_coli": 900, "enterococci": 500, "bathing_advice": 1}


def test_utm_coordinates_of_the_points_become_latitude_and_longitude():
    lat, lon = utm_to_latlon(475293.08, 4376164.44, 31)  # Cala Estància (Palma), checked against the IGN viewer

    assert lat == pytest.approx(39.5348, abs=1e-4)
    assert lon == pytest.approx(2.7125, abs=1e-4)
    assert utm_to_latlon(500000, 0, 31) == pytest.approx((0, 3))  # the origin of zone 31


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("PLAYA DE PALMA", "Playa de Palma"),
        ("PLAYA S'ARENAL", "Playa s'Arenal"),
        ("CALA D'OR", "Cala d'Or"),
        ("PLAYA ES TRENC", "Playa es Trenc"),
    ],
)
def test_names_are_written_as_titles(name, title):
    assert title_case(name) == title


def test_points_without_a_code_are_numbered():
    assert point_code("PLAYA DE PALMA PM3", 1) == "PM3"
    assert point_code("PLAYA DE PALMA", 2) == "PM2"
