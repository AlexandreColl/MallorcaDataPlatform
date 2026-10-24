import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.connectors import registry
from core.models import Location, Quality, Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))
REGION = Region(
    name="test",
    min_lat=39.25,
    min_lon=2.30,
    max_lat=39.97,
    max_lon=3.50,
    locations=(Location("palma", 39.5696, 2.6502), Location("inca", 39.7210, 2.9110)),
)


FIXTURE_BY_HOST = {"air-quality-api": "air_quality.json", "api.open-meteo.com": "weather.json"}


class RecordedHttp:
    """Serves the responses recorded in tests/fixtures instead of calling the API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, params))
        name = next(f for marker, f in FIXTURE_BY_HOST.items() if marker in url)
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def connector():
    return registry.load("open_meteo", http=RecordedHttp())


def test_extract_builds_one_request_per_dataset(connector):
    payloads = connector.extract(WINDOW, REGION)

    assert [p.dataset for p in payloads] == ["air_quality", "weather"]
    url, params = connector.http.calls[0]
    assert "air-quality" in url
    assert params["latitude"] == "39.5696,39.7210"
    assert params["start_date"] == params["end_date"] == "2026-10-23"
    assert params["hourly"].split(",") == [
        "pm10",
        "pm2_5",
        "nitrogen_dioxide",
        "ozone",
        "european_aqi",
    ]
    assert payloads[0].key == "open_meteo/air_quality/window=20261023_20261023/payload.json"


def test_normalize_emits_common_schema(connector):
    payloads = connector.extract(WINDOW, REGION)
    obs = [o for p in payloads for o in connector.normalize(p, REGION)]

    # 2 locations x 24 hours x (5 air quality + 5 weather metrics)
    assert len(obs) == 2 * 24 * 10
    assert {o.entity for o in obs} == {"palma", "inca"}
    assert all(o.source == "open_meteo" for o in obs)
    assert all(o.ts.tzinfo is UTC for o in obs)
    assert min(o.ts for o in obs) == datetime(2026, 10, 23, 0, tzinfo=UTC)
    assert max(o.ts for o in obs) == datetime(2026, 10, 23, 23, tzinfo=UTC)
    units = {o.metric: o.unit for o in obs}
    assert units["pm2_5"] == "ug/m3"
    assert units["temperature_2m"] == "degC"


def test_normalize_handles_single_location_and_nulls(connector):
    payload = connector.extract(WINDOW, REGION)[0]
    body = payload.body[0]
    body["hourly"]["pm10"][3] = None
    single = type(payload)(
        source=payload.source,
        dataset=payload.dataset,
        window=payload.window,
        request={**payload.request, "locations": ["palma"]},
        body=body,
    )
    obs = list(connector.normalize(single, REGION))
    missing = [o for o in obs if o.quality == Quality.MISSING]

    assert {o.entity for o in obs} == {"palma"}
    assert len(missing) == 1
    assert missing[0].metric == "pm10"
    assert missing[0].value is None
