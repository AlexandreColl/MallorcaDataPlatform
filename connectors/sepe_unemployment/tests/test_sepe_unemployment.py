"""SEPE registered unemployment against the files recorded with `make record-fixtures CONNECTOR=sepe_unemployment`.

Recorded 2026-11-28 for 2025-09-04..2026-10-08 (October 2025 to October 2026): the yearly files of 2025 and 2026,
trimmed to their title, header and the lines of Palma, Pollença, Escorca and Calvià, of Maó and Eivissa (other
islands) and of Abla (Almería, another province). The real files are ~10 MB each.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from connectors.sepe_unemployment.extractor import lines_of, month_of, parse_count
from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import RawPayload, TimeWindow
from core.quality.engine import GapRule, NotNullRule, rules_for

FIXTURES = Path(__file__).parent / "fixtures"
MADRID = ZoneInfo("Europe/Madrid")
MALLORCA_IN_FIXTURES = {"07040", "07042", "07019", "07011"}
HEADER = (
    "Código mes ;mes;Código de CA;Comunidad Autónoma;Codigo Provincia;Provincia;Codigo Municipio; Municipio;"
    "total Paro Registrado;Paro hombre edad < 25;Paro hombre edad 25 -45 ;Paro hombre edad >=45;Paro mujer edad < 25;"
    "Paro mujer edad 25 -45 ;Paro mujer edad >=45;Paro Agricultura;Paro Industria;Paro Construcción;Paro Servicios;"
    "Paro Sin empleo Anterior\n"
)


@pytest.fixture
def recorded():
    """The connector answering from the recordings, with the window and region they were made for."""
    connector = registry.load("sepe_unemployment", http=RecordedHttp(FIXTURES))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def _observations(connector, window, region):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def _value(observations, entity, metric, month):
    ts = datetime(month.year, month.month, 1, tzinfo=MADRID)
    return next(o.value for o in observations if (o.entity, o.metric, o.ts) == (entity, metric, ts))


def test_one_payload_per_yearly_file_with_the_lines_of_the_province(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.partition for p in payloads] == ["2025", "2026"]
    first = payloads[0]
    assert first.request["url"].endswith("/Paro_por_municipios_2025_csv.csv")
    assert len(first.request["sha256"]) == 64
    # October to December 2025 for the 6 Balearic municipalities of the fixture; Abla (Almería) is left out.
    assert first.request["lines"] == 3 * 6
    assert "Abla" not in first.body
    assert first.body.startswith(";;;;PARO REGISTRADO POR MUNICIPIOS")


def test_every_observation_fits_the_connector_yaml(recorded):
    connector, window, region = recorded

    observations = _observations(connector, window, region)

    assert len(observations) == len(MALLORCA_IN_FIXTURES) * 12 * 13  # municipalities x columns x months
    assert {o.entity for o in observations} == MALLORCA_IN_FIXTURES  # Maó and Eivissa are other islands
    for o in observations:
        spec = connector.config.metrics[o.metric]
        assert o.unit == spec.unit == "people"
        assert window.start <= o.ts.date() <= window.end
        assert o.value is None or spec.min <= o.value <= spec.max, o


def test_months_are_stamped_on_their_first_day_at_local_midnight(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    january = datetime(2025, 12, 31, 23, tzinfo=UTC)  # 1 January 2026 00:00 in Madrid (CET)
    palma = {o.metric: o.value for o in observations if o.entity == "07040" and o.ts == january}
    assert palma["unemployed"] == 12571
    assert palma["unemployed_services"] == 9552
    assert palma["unemployed_no_previous_job"] == 1136
    bands = [k for k in palma if k.startswith(("unemployed_men", "unemployed_women"))]
    sectors = ["agriculture", "industry", "construction", "services", "no_previous_job"]
    assert sum(palma[k] for k in bands) == palma["unemployed"]  # the six bands of sex and age add up to the total
    assert sum(palma[f"unemployed_{s}"] for s in sectors) == palma["unemployed"]  # and so do the sectors
    pollenca = next(o for o in observations if o.entity == "07042")
    assert (pollenca.lat, pollenca.lon) == pytest.approx((39.8867, 3.0289))  # centre of its IGN boundary


def test_pollenca_has_fewer_unemployed_in_the_season_than_in_winter(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    assert _value(observations, "07042", "unemployed", date(2026, 1, 1)) == 275
    assert _value(observations, "07042", "unemployed", date(2026, 7, 1)) < 200


def test_suppressed_counts_are_null_never_five(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    escorca = [o for o in observations if o.entity == "07019" and o.metric == "unemployed"]
    assert len(escorca) == 13
    assert all(o.value is None or o.value == 0 or o.value >= 5 for o in escorca)  # nothing from 1 to 4
    assert _value(observations, "07019", "unemployed", date(2026, 10, 1)) is None  # "<5" in the file
    assert _value(observations, "07019", "unemployed_men_under_25", date(2026, 10, 1)) == 0  # zeros stay zeros
    assert _value(observations, "07042", "unemployed_agriculture", date(2026, 10, 1)) is None


def test_the_quality_rules_do_not_count_suppressed_values_as_missing_or_gaps(recorded):
    connector, window, _ = recorded

    rules = rules_for(connector.config, window)

    not_null = next(r for r in rules if isinstance(r, NotNullRule))
    gaps = next(r for r in rules if isinstance(r, GapRule))
    assert not_null.suppressed == gaps.suppressed == frozenset(connector.config.metrics)
    assert gaps.expected_steps == 13  # one per month, so a month SEPE left out of the file is still a gap


def test_codes_of_four_digits_before_2019_are_padded():
    connector = registry.load("sepe_unemployment")
    window = TimeWindow(date(2012, 1, 1), date(2012, 1, 31))
    line = "201201;Enero de 2012;4;Balears, Illes;7;Balears, Illes;7040;Palma;40509" + ";1" * 11 + "\n"
    body = ";;;;PARO REGISTRADO\n" + HEADER + line
    payload = RawPayload("sepe_unemployment", "municipalities", window, {}, body, partition="2012")

    observations = list(connector.normalize(payload, load_region("mallorca")))

    assert {o.entity for o in observations} == {"07040"}
    assert next(o.value for o in observations if o.metric == "unemployed") == 40509


def test_a_header_without_a_mapped_column_is_an_error():
    connector = registry.load("sepe_unemployment")
    window = TimeWindow(date(2026, 1, 1), date(2026, 1, 31))
    body = ";;;;PARO REGISTRADO\n" + HEADER.replace("Paro Servicios", "Paro Turismo")
    payload = RawPayload("sepe_unemployment", "municipalities", window, {}, body, partition="2026")

    with pytest.raises(ConnectorError, match="Paro Servicios"):
        list(connector.normalize(payload, load_region("mallorca")))


def test_years_before_the_first_file_are_not_asked_for():
    urls = []

    class Recorder:
        def get_bytes(self, url, params=None, headers=None):
            urls.append(url)
            return (";;;;PARO REGISTRADO\n" + HEADER).encode("latin-1")

    connector = registry.load("sepe_unemployment", http=Recorder())
    connector.extract(TimeWindow(date(2005, 1, 1), date(2006, 2, 15)), load_region("mallorca"))

    assert [u.rsplit("/", 1)[1] for u in urls] == ["Paro_por_municipios_2006_csv.csv"]


def test_cells_and_months():
    assert parse_count(" 12 ") == 12
    assert parse_count("<5") is None
    assert parse_count("0") == 0
    with pytest.raises(ConnectorError, match="unexpected count"):
        parse_count("n.d.")
    assert month_of("202610") == date(2026, 10, 1)
    with pytest.raises(ConnectorError, match="YYYYMM"):
        month_of("202613")
    lines = ["202601;x;4;B;7;B;07040;Palma;1", "202602;x;4;B;7;B;07040;Palma;2", "202601;x;1;A;4;A;04001;Abla;3"]
    text = ";;;;T\n" + HEADER + "\n".join(lines) + "\n"
    assert [line.split(";")[0] for line in lines_of(text, "7", {date(2026, 1, 1)})[2:]] == ["202601"]
