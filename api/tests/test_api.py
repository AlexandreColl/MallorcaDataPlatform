from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from api import __version__
from api.main import create_app
from api.settings import Settings

TS = datetime(2026, 10, 27, 10, tzinfo=UTC)
SOURCE = {
    "source": "aemet", "label": "AEMET", "kind": "observation", "last_status": "success", "last_run_at": TS,
    "last_success_at": TS, "last_loaded_day": date(2026, 10, 25), "runs_7d": 7, "failure_rate_7d": 0,
    "latest_observation_ts": TS, "data_age_hours": 26.5, "observations": 796474,
}  # fmt: skip
WATER = {
    "month": date(2026, 8, 1), "hydrological_year": 2026, "reserves_pct": 38.0, "change_1m_pts": -1.0,
    "change_12m_pts": -5.0, "same_month_mean_pct": 49.5, "anomaly_pts": -11.5, "aquifers": 18,
    "aquifers_below_30_pct": 7, "lowest_aquifer": "Son Real", "lowest_aquifer_pct": 9.0,
}  # fmt: skip

CORRECTION = {
    "source": "socib", "entity": "parcbit", "metric": "temperature_2m", "ts": TS, "unit": "degC",
    "original_quality": "missing", "original_value": None, "corrected_value": 17.4, "method": "support",
    "support_source": "open_meteo", "support_entity": "llucmajor", "bias": -1.2, "confidence": 0.71,
}  # fmt: skip


def observation(i):
    return {"source": "aemet", "entity": "B278", "metric": "temperature_2m_mean", "ts": TS, "value": 20.0 + i,
            "unit": "degC", "quality": "ok", "lat": 39.55, "lon": 2.73}  # fmt: skip


class FakeDatabase:
    """Answers by the table a query reads and records every query with its parameters."""

    def __init__(self, rows=None, *, up=True):
        self.rows = rows or {}
        self.up = up
        self.calls: list[tuple[str, dict]] = []

    def fetch_all(self, sql, params=None):
        self.calls.append((sql, dict(params or {})))
        for table, rows in self.rows.items():
            if table in sql:
                return rows(params) if callable(rows) else rows
        return []

    def ping(self):
        return self.up


def client(db, **settings):
    return TestClient(create_app(Settings(**settings), database=db))


@pytest.fixture
def db():
    return FakeDatabase({
        "gold.dim_sources": [{"?column?": 1}],
        "gold.source_health": lambda p: [SOURCE] if p["source"] in {None, "aemet"} else [],
        "gold.fct_water_reserves_monthly": [WATER],
        "gold.fct_observations": lambda p: [observation(i) for i in range(p["offset"], min(p["offset"] + p["limit"], 250))],  # noqa: E501
    })  # fmt: skip


def test_health_reports_the_warehouse(db):
    assert client(db).get("/v1/health").json() == {"status": "ok", "database": "ok", "version": __version__}

    down = client(FakeDatabase(up=False)).get("/v1/health")
    assert down.status_code == 503
    assert down.json() == {"error": {"code": "unavailable", "message": "warehouse unavailable"}}


def test_sources_and_one_source(db):
    api = client(db)

    assert api.get("/v1/sources").json()[0]["source"] == "aemet"
    assert api.get("/v1/sources/aemet").json()["observations"] == 796474
    missing = api.get("/v1/sources/nope")
    assert missing.status_code == 404
    assert missing.json()["error"] == {"code": "not_found", "message": "unknown source 'nope'"}


def test_locations_with_an_optional_source(db):
    location = {"source": "aemet", "label": "AEMET", "kind": "observation", "entity": "B278", "lat": 39.55,
                "lon": 2.73, "first_seen": TS, "last_seen": TS, "n_metrics": 10}  # fmt: skip
    db.rows = {"gold.dim_locations": [location], **db.rows}  # before gold.dim_sources, which the query joins
    api = client(db)

    assert api.get("/v1/locations").json()[0]["kind"] == "observation"
    assert db.calls[-1][1] == {"source": None}
    api.get("/v1/locations", params={"source": "aemet"})
    assert db.calls[-1][1] == {"source": "aemet"}


def test_observations_are_paginated_with_one_extra_row(db):
    api = client(db)

    page = api.get("/v1/observations", params={"source": "aemet", "limit": 100}).json()

    assert len(page["items"]) == 100
    assert page["next_offset"] == 100
    sql, params = db.calls[-1]
    assert "gold.fct_observations" in sql
    assert params["limit"] == 101  # one more than asked: tells whether there is a next page
    last = api.get("/v1/observations", params={"source": "aemet", "limit": 100, "offset": 200}).json()
    assert len(last["items"]) == 50
    assert last["next_offset"] is None  # the fake has 250 rows: rows 200-249 are the last page


def test_observation_filters_and_default_window(db):
    client(db).get("/v1/observations", params={"source": "aemet", "metric": "temperature_2m_mean", "entity": "B278"})

    _, params = db.calls[-1]
    assert (params["metric"], params["entity"]) == ("temperature_2m_mean", "B278")
    assert (params["end"] - params["start"]).days == 7
    assert params["start"].tzinfo is not None


def test_naive_instants_are_utc(db):
    client(db).get("/v1/observations", params={"source": "aemet", "start": "2026-10-01T00:00", "end": "2026-10-02"})

    _, params = db.calls[-1]
    assert params["start"] == datetime(2026, 10, 1, tzinfo=UTC)
    assert params["end"] == datetime(2026, 10, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"source": "aemet", "limit": 0}, "limit: Input should be greater than or equal to 1"),
        ({"source": "aemet", "limit": 5000}, "`limit` must be at most 1000"),
        ({"source": "aemet", "start": "2026-10-02", "end": "2026-10-01"}, "`start` must be before `end`"),
        ({"source": "aemet", "start": "yesterday"}, "start: Input should be a valid datetime"),
        ({}, "source: Field required"),
    ],
)
def test_invalid_requests_share_one_error_shape(db, query, message):
    response = client(db).get("/v1/observations", params=query)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["message"].startswith(message)


def test_unknown_source_is_404_before_querying_observations():
    db = FakeDatabase()  # dim_sources answers nothing

    response = client(db).get("/v1/observations", params={"source": "nope"})

    assert response.status_code == 404
    assert not any("gold.fct_observations" in sql for sql, _ in db.calls)


def test_page_size_limit_comes_from_settings(db):
    assert (
        client(db, max_page_size=50).get("/v1/observations", params={"source": "aemet", "limit": 60}).status_code == 422
    )


def test_monthly_marts_filter_by_month(db):
    response = client(db).get("/v1/water/reserves", params={"from": "2026-01-01", "to": "2026-08-01"})

    assert response.json()[0]["anomaly_pts"] == -11.5
    sql, params = db.calls[-1]
    assert "gold.fct_water_reserves_monthly" in sql
    assert params == {"start": date(2026, 1, 1), "end": date(2026, 8, 1)}


@pytest.mark.parametrize("path", ["/v1/climate/monthly", "/v1/tourism/monthly", "/v1/resources/monthly"])
def test_every_monthly_mart_answers(db, path):
    response = client(db).get(path)

    assert response.status_code == 200
    assert response.json() == []


def test_anomalies_filters(db):
    client(db).get("/v1/anomalies", params={"source": "open_meteo", "detector": "robust_zscore"})

    sql, params = db.calls[-1]
    assert "silver.anomalies" in sql
    assert (params["source"], params["detector"], params["limit"]) == ("open_meteo", "robust_zscore", 101)


def test_corrections_filters_and_page(db):
    db.rows = {"gold.fct_observations_corrected": [CORRECTION], **db.rows}  # before gold.fct_observations
    response = client(db).get("/v1/corrections", params={"source": "socib", "method": "support", "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["method"] == "support"
    assert body["items"][0]["original_value"] is None
    sql, params = db.calls[-1]
    assert "gold.fct_observations_corrected" in sql
    assert "is_corrected" in sql
    assert (params["source"], params["entity"], params["method"], params["limit"]) == ("socib", None, "support", 11)


def test_corrections_reject_an_unknown_method(db):
    response = client(db).get("/v1/corrections", params={"method": "magic"})

    assert response.status_code == 422
    assert db.calls == []


def test_openapi_documents_every_endpoint(db):
    paths = client(db).get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/v1/health", "/v1/sources", "/v1/sources/{source}", "/v1/observations", "/v1/anomalies", "/v1/corrections",
        "/v1/water/reserves", "/v1/water/aquifers", "/v1/climate/monthly", "/v1/tourism/monthly",
        "/v1/resources/monthly", "/v1/locations", "/v1/mobility/daily", "/v1/mobility/stops", "/v1/weather/daily",
        "/v1/weather/episodes", "/v1/weather/model-bias", "/v1/weather/stations", "/v1/air-quality/latest",
        "/v1/sea/hourly", "/v1/earthquakes", "/v1/warnings", "/v1/warnings/zones",
        "/v1/quality/rules", "/v1/anomalies/daily",
    }  # fmt: skip


def test_only_get_is_allowed(db):
    response = client(db).post("/v1/sources")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_settings_from_environment():
    settings = Settings.from_env({"WAREHOUSE_HOST": "postgres", "API_DB_USER": "reader", "API_CORS_ORIGINS": "a, b"})

    assert (settings.host, settings.user, settings.cors_origins) == ("postgres", "reader", ("a", "b"))
    assert "default_transaction_read_only=on" in settings.conninfo


@pytest.mark.parametrize(
    ("path", "table"),
    [
        ("/v1/mobility/daily", "gold.fct_island_transit_daily"),
        ("/v1/mobility/stops", "gold.fct_observations"),
        ("/v1/weather/daily", "gold.fct_weather_daily"),
        ("/v1/weather/stations", "gold.fct_weather_daily"),
        ("/v1/warnings", "gold.fct_weather_warnings"),
        ("/v1/warnings/zones", "gold.dim_warning_zones"),
        ("/v1/weather/episodes", "gold.fct_weather_episodes"),
        ("/v1/weather/model-bias", "gold.agg_model_bias_by_station"),
        ("/v1/air-quality/latest", "gold.air_quality_hourly"),
        ("/v1/sea/hourly", "gold.fct_sea_conditions_hourly"),
        ("/v1/earthquakes", "gold.fct_earthquakes"),
        ("/v1/quality/rules", "gold.data_quality_summary"),
        ("/v1/anomalies/daily", "silver.anomalies"),
    ],
)
def test_every_dashboard_endpoint_reads_its_mart(path, table):
    db = FakeDatabase()

    response = client(db).get(path)

    assert response.status_code == 200
    assert response.json() == []
    assert table in db.calls[-1][0]


def test_day_ranges_default_to_the_last_days_and_are_validated():
    db = FakeDatabase()
    api = client(db)

    api.get("/v1/weather/daily")
    start, end = db.calls[-1][1]["start"], db.calls[-1][1]["end"]
    assert (end - start).days == 29  # 30 days, both included
    api.get("/v1/mobility/daily", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert db.calls[-1][1] == {"start": date(2026, 10, 1), "end": date(2026, 10, 31)}

    response = api.get("/v1/earthquakes", params={"from": "2026-11-02", "to": "2026-11-01"})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "`from` must not be after `to`"


def test_stops_filter_by_network_and_reject_an_unknown_one():
    db = FakeDatabase({"gold.fct_observations": [
        {"network": "ctm", "stop": "stop_1", "lat": 39.6, "lon": 2.9, "local_date": date(2026, 11, 4),
         "departures": 1028.0, "lines": 31.0},
    ]})  # fmt: skip
    api = client(db)

    assert api.get("/v1/mobility/stops", params={"network": "ctm"}).json()[0]["departures"] == 1028.0
    assert db.calls[-1][1] == {"network": "ctm"}
    assert api.get("/v1/mobility/stops", params={"network": "tram"}).status_code == 422


def test_warnings_default_to_the_next_days_and_zones_come_with_their_polygon():
    zone = {"zone": "645403", "name": "Interior de Mallorca", "kind": "land", "polygon": "[[2.93,39.81],[2.95,39.76]]"}
    db = FakeDatabase({"gold.dim_warning_zones": [zone]})
    api = client(db)

    api.get("/v1/warnings")
    params = db.calls[-1][1]
    assert round((params["end"] - params["start"]).total_seconds() / 86400) == 3
    assert api.get("/v1/warnings/zones").json()[0]["polygon"] == [[2.93, 39.81], [2.95, 39.76]]
