import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from connectors.open_meteo.extractor import OpenMeteoConnector
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
        "olive_pollen",
        "grass_pollen",
        "dust",
        "uv_index",
    ]
    assert payloads[0].key == "open_meteo/air_quality/window=20261023_20261023/payload.json"


def test_old_windows_ask_the_archive_of_the_weather_forecasts(connector):
    payloads = connector.extract(TimeWindow(date(2017, 3, 22), date(2017, 12, 31)), REGION)

    urls = {p.dataset: p.request["url"] for p in payloads}
    assert urls == {
        "air_quality": "https://air-quality-api.open-meteo.com/v1/air-quality",  # CAMS serves any window
        "weather": "https://historical-forecast-api.open-meteo.com/v1/forecast",
    }
    assert [url for url, _ in connector.http.calls] == list(urls.values())


def test_recent_windows_ask_the_live_forecast(connector):
    today = datetime.now(UTC).date()
    payloads = connector.extract(TimeWindow(today - timedelta(days=92), today - timedelta(days=1)), REGION)

    assert payloads[1].request["url"] == "https://api.open-meteo.com/v1/forecast"


def test_the_history_starts_the_day_the_live_api_stops_serving():
    spec = {"url": "live", "history_url": "history", "past_days": 92}
    today = date(2026, 11, 23)

    assert OpenMeteoConnector.url_for(spec, TimeWindow(date(2026, 8, 23), date(2026, 8, 23)), today) == "live"
    assert OpenMeteoConnector.url_for(spec, TimeWindow(date(2026, 8, 22), date(2026, 11, 22)), today) == "history"
    assert OpenMeteoConnector.url_for({"url": "live"}, TimeWindow(date(2017, 1, 1), date(2017, 1, 1)), today) == "live"


def test_normalize_emits_common_schema(connector):
    payloads = connector.extract(WINDOW, REGION)
    obs = [o for p in payloads for o in connector.normalize(p, REGION)]

    # 2 locations x 24 hours x (9 air quality + 5 weather metrics)
    assert len(obs) == 2 * 24 * 14
    assert {o.entity for o in obs} == {"palma", "inca"}
    assert all(o.source == "open_meteo" for o in obs)
    assert all(o.ts.tzinfo is UTC for o in obs)
    assert min(o.ts for o in obs) == datetime(2026, 10, 23, 0, tzinfo=UTC)
    assert max(o.ts for o in obs) == datetime(2026, 10, 23, 23, tzinfo=UTC)
    units = {o.metric: o.unit for o in obs}
    assert units["pm2_5"] == "ug/m3"
    assert units["temperature_2m"] == "degC"
    assert units["olive_pollen"] == units["grass_pollen"] == "grains/m3"
    assert units["dust"] == "ug/m3"
    assert units["uv_index"] == "uvi"


def test_windows_before_a_metric_existed_do_not_ask_for_it(connector):
    connector.extract(TimeWindow(date(2017, 1, 1), date(2017, 12, 31)), REGION)
    connector.extract(TimeWindow(date(2021, 1, 1), date(2021, 12, 31)), REGION)

    old, newer = (params["hourly"].split(",") for url, params in connector.http.calls if "air-quality" in url)
    assert old == ["pm10", "pm2_5", "nitrogen_dioxide", "ozone", "european_aqi"]
    assert newer == [*old, "olive_pollen", "grass_pollen", "dust"]  # UV starts in August 2022


def test_hours_before_a_metric_existed_are_dropped_not_missing(connector):
    payload = connector.extract(WINDOW, REGION)[0]
    known = connector.available_since()
    connector.available_since = lambda: {**known, "dust": date(2026, 10, 24)}  # dust starts the day after the window

    obs = list(connector.normalize(payload, REGION))

    assert not [o for o in obs if o.metric == "dust"]
    assert {o.metric for o in obs} >= {"pm10", "olive_pollen", "uv_index"}


def test_normalize_reads_only_the_metrics_the_request_asked_for(connector):
    payload = connector.extract(WINDOW, REGION)[0]
    payload.request["params"]["hourly"] = "pm10,pm2_5"  # a bronze payload from before the metric existed

    assert {o.metric for o in connector.normalize(payload, REGION)} == {"pm10", "pm2_5"}


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


def test_describe_names_the_points_that_have_a_label():
    pollenca = Location("pollenca", 39.877, 3.016, "Pollença")
    region = Region("test", 39.25, 2.30, 39.97, 3.50, (pollenca, *REGION.locations))
    connector = registry.load("open_meteo", http=RecordedHttp())
    payload = connector.extract(WINDOW, REGION)[0]
    payload.request["locations"] = ["pollenca", "palma"]

    assert [(e.entity, e.name) for e in connector.describe(payload, region)] == [("pollenca", "Pollença")]


def test_describe_takes_the_height_of_the_model_cell_from_the_weather_forecast():
    points = (Location("palma", 39.5696, 2.6502, "Palma"), Location("inca", 39.7210, 2.9110, "Inca"))
    region = Region("test", 39.25, 2.30, 39.97, 3.50, points)
    connector = registry.load("open_meteo", http=RecordedHttp())
    payloads = {p.dataset: p for p in connector.extract(WINDOW, region)}

    weather = {e.entity: e.elevation_m for e in connector.describe(payloads["weather"], region)}
    air = {e.entity: e.elevation_m for e in connector.describe(payloads["air_quality"], region)}

    assert weather == {"palma": 32.0, "inca": 129.0}
    assert air == {"palma": None, "inca": None}  # the air quality grid is another model: it names the points only
