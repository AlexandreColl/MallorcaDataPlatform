import io
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware import RateLimit, ResponseCache
from api.settings import Settings
from api.tests.test_api import WATER, FakeDatabase, client, observation


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _water(db_calls):
    def rows(params):
        db_calls.append(params)
        return [WATER]

    return rows


def _app(clock, **settings):
    calls = []
    db = FakeDatabase({"fct_water_reserves_monthly": _water(calls)})
    app = create_app(Settings(**settings), database=db)
    for middleware in app.user_middleware:  # the clock of the tests instead of the monotonic one
        if middleware.cls in {RateLimit, ResponseCache}:
            middleware.kwargs["clock"] = clock
    return TestClient(app), calls


def test_a_cached_mart_is_read_once_and_validated_with_its_etag():
    clock = Clock()
    api, calls = _app(clock)

    first = api.get("/v1/water/reserves", params={"from": "2025-01-01", "to": "2026-08-01"})
    second = api.get("/v1/water/reserves", params={"to": "2026-08-01", "from": "2025-01-01"})  # another order
    assert first.status_code == second.status_code == 200
    assert (first.headers["x-cache"], second.headers["x-cache"]) == ("MISS", "HIT")
    assert first.json() == second.json()
    assert len(calls) == 1
    assert first.headers["etag"] == second.headers["etag"]
    assert first.headers["cache-control"] == "public, max-age=3600"

    clock.now += 600
    unchanged = api.get(
        "/v1/water/reserves",
        params={"from": "2025-01-01", "to": "2026-08-01"},
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["cache-control"] == "public, max-age=3000"


def test_an_entry_expires_and_errors_are_not_cached():
    clock = Clock()
    api, calls = _app(clock, cache_seconds=60)

    api.get("/v1/water/reserves")
    clock.now += 61
    assert api.get("/v1/water/reserves").headers["x-cache"] == "MISS"
    assert len(calls) == 2

    for _ in range(2):
        assert api.get("/v1/water/reserves", params={"from": "not-a-date"}).status_code == 422
    assert "x-cache" not in api.get("/v1/sources").headers  # not a cached path


def test_the_cache_keeps_the_most_recently_used_entries():
    cache = ResponseCache(None, seconds=60, paths=["/a"], max_entries=2, clock=Clock())
    for key in ("/a?x=1", "/a?x=2"):
        cache.store(key, [], b"{}")
    cache.fresh("/a?x=1")
    cache.store("/a?x=3", [], b"{}")
    assert list(cache.entries) == ["/a?x=1", "/a?x=3"]


def test_a_client_over_its_limit_waits_and_the_health_check_is_never_limited():
    clock = Clock()
    api, _ = _app(clock, rate_limit_per_minute=3)

    answers = [api.get("/v1/water/reserves") for _ in range(4)]
    assert [a.status_code for a in answers] == [200, 200, 200, 429]
    assert [a.headers["ratelimit-remaining"] for a in answers] == ["2", "1", "0", "0"]
    assert answers[3].headers["retry-after"] == "20"  # one token every 20 s
    assert answers[3].json() == {"error": {"code": "rate_limited", "message": answers[3].json()["error"]["message"]}}
    assert all(api.get("/v1/health").status_code == 200 for _ in range(5))

    clock.now += 20
    assert api.get("/v1/water/reserves").status_code == 200


def test_each_client_has_its_own_bucket_and_idle_clients_are_forgotten():
    clock = Clock()
    limit = RateLimit(None, per_minute=2, clock=clock, max_clients=2)
    assert limit.take("a")[0]
    assert limit.take("a")[0]
    assert not limit.take("a")[0]
    assert limit.take("b")[0]

    clock.now += 60  # both buckets full again
    assert limit.take("c")[0]
    assert set(limit.buckets) == {"c"}


def test_the_cache_can_be_turned_off():
    api, calls = _app(Clock(), cache_seconds=0)
    answers = [api.get("/v1/water/reserves") for _ in range(2)]
    assert len(calls) == 2
    assert "x-cache" not in answers[0].headers


def test_the_rate_limit_can_be_turned_off():
    api, _ = _app(Clock(), rate_limit_per_minute=0)
    answers = [api.get("/v1/sources") for _ in range(3)]
    assert [a.status_code for a in answers] == [200, 200, 200]
    assert "ratelimit-limit" not in answers[0].headers


def _export_db(count=3):
    rows = [observation(i) for i in range(count)]
    rows[1] = {**rows[1], "value": None, "quality": "missing", "lat": None, "lon": None}
    return FakeDatabase(
        {
            "count(*)": [{"n": count}],
            "dim_sources": [{"?column?": 1}],
            "fct_observations": rows,
        }
    )


def test_export_streams_a_csv_with_the_columns_of_the_observations():
    db = _export_db()
    answer = client(db).get(
        "/v1/observations/export",
        params={"source": "aemet", "metric": "temperature_2m_mean", "start": "2026-10-20", "end": "2026-10-28"},
    )

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "text/csv; charset=utf-8"
    assert answer.headers["content-disposition"] == (
        'attachment; filename="aemet_temperature_2m_mean_20261020-20261028.csv"'
    )
    assert answer.headers["x-total-count"] == "3"
    lines = answer.text.splitlines()
    assert lines[0] == "source,entity,metric,ts,value,unit,quality,lat,lon"
    assert lines[1] == "aemet,B278,temperature_2m_mean,2026-10-27T10:00:00+00:00,20.0,degC,ok,39.55,2.73"
    assert lines[2] == "aemet,B278,temperature_2m_mean,2026-10-27T10:00:00+00:00,,degC,missing,,"
    assert len(lines) == 4
    sql, params = next(call for call in db.calls if "ORDER BY" in call[0])
    assert "LIMIT" not in sql
    assert params["metric"] == "temperature_2m_mean"


def test_export_writes_parquet_with_utc_timestamps():
    answer = client(_export_db()).get("/v1/observations/export", params={"source": "aemet", "format": "parquet"})

    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/vnd.apache.parquet"
    table = pq.read_table(io.BytesIO(answer.content))
    assert table.num_rows == 3
    assert table.column_names == ["source", "entity", "metric", "ts", "value", "unit", "quality", "lat", "lon"]
    assert table.column("ts")[0].as_py() == datetime(2026, 10, 27, 10, tzinfo=UTC)
    assert table.column("value").to_pylist() == [20.0, None, 22.0]


def test_an_empty_export_is_a_file_with_only_the_header():
    db = FakeDatabase({"count(*)": [{"n": 0}], "dim_sources": [{"?column?": 1}]})
    assert client(db).get("/v1/observations/export", params={"source": "aemet"}).text.splitlines() == [
        "source,entity,metric,ts,value,unit,quality,lat,lon"
    ]
    parquet = client(db).get("/v1/observations/export", params={"source": "aemet", "format": "parquet"})
    assert pq.read_table(io.BytesIO(parquet.content)).num_rows == 0


@pytest.mark.parametrize(
    ("params", "settings", "status", "message"),
    [
        ({"source": "aemet", "start": "2025-01-01", "end": "2026-10-01"}, {}, 422, "at most 366 days"),
        ({"source": "aemet"}, {"export_max_rows": 2}, 422, "3 values, more than the 2"),
        ({"source": "aemet", "format": "xlsx"}, {}, 422, "format"),
    ],
)
def test_export_limits(params, settings, status, message):
    answer = client(_export_db(), **settings).get("/v1/observations/export", params=params)
    assert answer.status_code == status
    assert message in answer.json()["error"]["message"]


def test_export_of_an_unknown_source_is_404():
    db = FakeDatabase({"count(*)": [{"n": 0}]})
    assert client(db).get("/v1/observations/export", params={"source": "nope"}).status_code == 404
