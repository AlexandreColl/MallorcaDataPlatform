import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import ConnectorError, registry
from core.models import Location, Quality, Region, TimeWindow

# Real response for the 8 configured points on 2026-10-23 (same request the connector builds).
FIXTURE = Path(__file__).parent / "fixtures" / "marine.json"
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))
# The region's locations are inland towns: the marine connector must ignore them and use its sea points.
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50, (Location("inca", 39.7210, 2.9110),))
METRICS = 7
# Latitudes of the recorded request, in order (the API answers with the nearest model cell, not these values).
RECORDED_LATITUDES = ("39.5000", "39.5800", "39.8000", "39.9000", "39.8200", "39.6000", "39.4100", "39.3000")


class RecordedMarine:
    """Serves the recorded points that were requested, in request order (like the real API)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.recorded = dict(zip(RECORDED_LATITUDES, json.loads(FIXTURE.read_text(encoding="utf-8")), strict=True))

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        cells = [self.recorded[lat] for lat in params["latitude"].split(",")]
        return cells if len(cells) > 1 else cells[0]


def _connector(http=None):
    return registry.load("open_meteo_marine", http=http or RecordedMarine())


def _normalize(region=MALLORCA):
    connector = _connector()
    return [o for p in connector.extract(WINDOW, region) for o in connector.normalize(p, region)]


def test_queries_the_sea_points_not_the_region_towns():
    http = RecordedMarine()

    payloads = _connector(http).extract(WINDOW, MALLORCA)

    assert len(payloads) == 1
    url, params = http.calls[0]
    assert url == "https://marine-api.open-meteo.com/v1/marine"
    assert len(params["latitude"].split(",")) == 8
    assert "39.7210" not in params["latitude"]  # inca
    assert payloads[0].request["locations"][0] == "bahia_de_palma"
    assert "sea_surface_temperature" in params["hourly"]


def test_hourly_values_per_point_and_metric():
    observations = _normalize()
    by_key = {(o.entity, o.metric, o.ts): o for o in observations}
    midnight = datetime(2026, 10, 23, tzinfo=UTC)

    assert len(observations) == 8 * METRICS * 24
    assert by_key["bahia_de_palma", "wave_height", midnight].value == pytest.approx(0.42)
    assert by_key["bahia_de_palma", "sea_surface_temperature", midnight].unit == "degC"
    point = by_key["bahia_de_palma", "wave_height", midnight]
    assert (point.lat, point.lon) == (39.50, 2.68)  # the configured point, not the model cell
    assert {o.quality for o in observations} == {Quality.OK}


def test_only_points_inside_the_region_are_queried():
    north = Region("north", 39.70, 2.50, 39.97, 3.30)

    entities = {o.entity for o in _normalize(north)}

    assert entities == {"soller", "pollenca", "alcudia"}


def test_region_without_sea_points_is_rejected():
    inland = Region("inland", 39.65, 2.85, 39.75, 2.95)

    with pytest.raises(ConnectorError, match="no Open-Meteo Marine point"):
        _connector().extract(WINDOW, inland)
