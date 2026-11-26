"""INE tourist dwellings against the answer recorded with `make record-fixtures CONNECTOR=ine_tourist_housing`.

Recorded 2026-11-26: DATOS_TABLA/39363 filtered to the 53 municipalities of Mallorca for 2023-11-27..2026-11-25, the
reference months February, August and November 2024, May and November 2025 and May 2026.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import RawPayload, Region, TimeWindow
from core.quality.engine import GapRule, rules_for

FIXTURES = Path(__file__).parent / "fixtures"
MENORCA = Region("menorca", 39.80, 3.79, 40.10, 4.33)
MADRID = ZoneInfo("Europe/Madrid")
FIRST_HALF_2026 = TimeWindow(date(2026, 1, 1), date(2026, 6, 30))


@pytest.fixture
def recorded():
    """The connector answering from the recordings, with the window and region they were made for."""
    connector = registry.load("ine_tourist_housing", http=RecordedHttp(FIXTURES))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def _observations(connector, window, region):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def _payload(body, window=FIRST_HALF_2026):
    return RawPayload("ine_tourist_housing", "municipalities", window, {}, json.dumps(body))


def test_one_request_filtered_to_the_municipalities_of_mallorca(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.dataset for p in payloads] == ["municipalities"]
    params = payloads[0].request["params"]
    assert params["date"] == f"{window.start:%Y%m%d}:{window.end:%Y%m%d}"
    assert len(params["tv"]) == 53  # one Tempus filter per municipality, never the 44 MB of the whole of Spain
    assert "19:5685" in params["tv"]  # Pollença


def test_every_observation_fits_the_connector_yaml(recorded):
    connector, window, region = recorded

    observations = _observations(connector, window, region)

    assert len(observations) == 53 * 3 * 6  # municipalities x concepts x reference months
    for o in observations:
        spec = connector.config.metrics[o.metric]
        assert o.source == "ine_tourist_housing"
        assert o.unit == spec.unit
        assert window.start <= o.ts.date() <= window.end
        assert spec.min <= o.value <= spec.max, o


def test_values_are_stamped_on_the_first_day_of_the_reference_month_at_local_midnight(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    def value(entity, metric, ts):
        return next(o.value for o in observations if (o.entity, o.metric, o.ts) == (entity, metric, ts))

    may_2026 = datetime(2026, 4, 30, 22, tzinfo=UTC)  # 1 May 00:00 in Madrid (CEST)
    assert value("07042", "tourist_dwellings", may_2026) == 2344  # Pollença, the municipality with the most
    assert value("07042", "tourist_beds", may_2026) == 14306
    assert value("07042", "beds_per_dwelling", may_2026) == pytest.approx(6.1)
    assert value("07042", "tourist_dwellings", datetime(2025, 10, 31, 23, tzinfo=UTC)) == 2385  # November (CET)
    pollenca = next(o for o in observations if o.entity == "07042")
    assert (pollenca.lat, pollenca.lon) == pytest.approx((39.8867, 3.0289))  # centre of its IGN boundary


def test_the_island_had_a_quarter_fewer_tourist_dwellings_in_may_2026_than_in_august_2024(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    def island(ts):
        return sum(o.value for o in observations if o.metric == "tourist_dwellings" and o.ts == ts)

    assert island(datetime(2024, 7, 31, 22, tzinfo=UTC)) == 18125
    assert island(datetime(2026, 4, 30, 22, tzinfo=UTC)) == 14756


def test_reference_months_outside_the_window_are_left_out(recorded):
    connector, _, region = recorded
    recorded_payload = connector.extract(Manifest.load(FIXTURES).window, region)[0]
    payload = _payload(json.loads(recorded_payload.body), TimeWindow(date(2025, 1, 1), date(2025, 12, 31)))

    months = {o.ts.astimezone(MADRID).date() for o in connector.normalize(payload, region)}

    assert months == {date(2025, 5, 1), date(2025, 11, 1)}


def test_another_region_asks_only_for_its_own_municipalities(recorded):
    _connector, window, _ = recorded

    class Recorder:
        params = None

        def get_json(self, url, params=None, headers=None):
            Recorder.params = params
            return []

    registry.load("ine_tourist_housing", http=Recorder()).extract(window, MENORCA)

    assert Recorder.params["tv"] == []  # the YAML lists the municipalities of Mallorca only


def test_an_answer_without_municipalities_is_an_error():
    connector = registry.load("ine_tourist_housing")
    region = load_region("mallorca")

    with pytest.raises(ConnectorError, match="no municipal series"):
        list(connector.normalize(_payload([{"MetaData": [], "Data": []}]), region))
    with pytest.raises(ConnectorError, match="unexpected answer"):
        list(connector.normalize(_payload({"error": "no table"}), region))


def test_a_data_point_that_is_not_monthly_is_an_error():
    connector = registry.load("ine_tourist_housing")
    series = [
        {
            "MetaData": [
                {"Id": 5685, "T3_Variable": "Municipios", "Codigo": "07042"},
                {"Id": 382508, "T3_Variable": "Concepto turístico", "Codigo": ""},
            ],
            "Data": [{"T3_Periodo": "S1", "Anyo": 2026, "Valor": 2344.0}],
        }
    ]

    with pytest.raises(ConnectorError, match="is not a month"):
        list(connector.normalize(_payload(series), load_region("mallorca")))


def test_irregular_reference_months_get_no_gaps_rule():
    config = registry.load("ine_tourist_housing").config

    assert config.is_event_source
    assert not [r for r in rules_for(config, TimeWindow(date(2024, 1, 1), date(2026, 6, 30))) if isinstance(r, GapRule)]
