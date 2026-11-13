"""The warehouse writes against a real Postgres: the upsert behind idempotent reruns, run tracking and replacements.

Runs only with ``WAREHOUSE_INTEGRATION=1`` and the DDL of ``core/sql/warehouse.sql`` applied (CI runs it on the
dbt job's Postgres; locally it can point at the stack's warehouse). Every row uses the source ``test_warehouse`` and
is deleted afterwards.
"""

import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.models import Entity, Route, TimeWindow
from core.warehouse import ABANDONED_AFTER, INTERRUPTED_ERROR, Warehouse

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("WAREHOUSE_INTEGRATION") != "1", reason="needs WAREHOUSE_INTEGRATION=1 and a warehouse"
    ),
]

SOURCE = "test_warehouse"
LANDING = "observations_test_warehouse"
WINDOW = TimeWindow(date(2026, 10, 30), date(2026, 10, 31))
T0 = datetime(2026, 10, 30, 9)  # noqa: DTZ001 - Spark writes the landing table in UTC without a zone
T1 = datetime(2026, 10, 30, 10)  # noqa: DTZ001


@pytest.fixture
def warehouse():
    wh = Warehouse(Settings.from_env())
    wh.ensure_schema()
    yield wh
    with wh.connect() as conn:
        for table in (
            "silver.observations",
            "silver.entities",
            "silver.routes",
            "silver.anomalies",
            "ops.ingestion_runs",
            "quality.check_results",
        ):
            conn.execute(f"DELETE FROM {table} WHERE source = %s", (SOURCE,))  # noqa: S608 - fixed table names
        conn.execute(f"DROP TABLE IF EXISTS landing.{LANDING}")


def land(warehouse, *rows, run_id="run1"):
    """Write rows (ts, value, quality) to the landing table, as Spark's JDBC writer does, and upsert them."""
    with warehouse.connect() as conn:
        conn.execute(
            f"""
            DROP TABLE IF EXISTS landing.{LANDING};
            CREATE TABLE landing.{LANDING} (
                source text, entity text, metric text, ts timestamp, value double precision, unit text,
                quality text, quality_reasons text, lat double precision, lon double precision, run_id text,
                ingested_at timestamp
            )
            """
        )
        insert = (
            f"INSERT INTO landing.{LANDING} VALUES"  # noqa: S608 - a fixed table name
            " (%s, 'palma', 'temperature', %s, %s, 'C', %s, NULL, 39.5, 2.6, %s, now() AT TIME ZONE 'UTC')"
        )
        with conn.cursor() as cur:
            cur.executemany(insert, [(SOURCE, ts, value, quality, run_id) for ts, value, quality in rows])
    return warehouse.merge_observations(LANDING)


def stored(warehouse):
    with warehouse.connect() as conn:
        rows = conn.execute(
            "SELECT ts, value, quality, run_id, updated_at FROM silver.observations WHERE source = %s ORDER BY ts",
            (SOURCE,),
        ).fetchall()
    return {ts: (value, quality, run_id, updated_at) for ts, value, quality, run_id, updated_at in rows}


def test_a_rerun_with_the_same_content_writes_nothing(warehouse):
    assert land(warehouse, (T0, 20.0, "ok"), (T1, 21.0, "ok")) == 2
    before = stored(warehouse)

    assert land(warehouse, (T0, 20.0, "ok"), (T1, 21.0, "ok"), run_id="run2") == 0
    assert stored(warehouse) == before  # the rows keep the run that wrote them and their updated_at


def test_a_changed_value_or_quality_updates_only_its_row(warehouse):
    land(warehouse, (T0, 20.0, "ok"), (T1, 21.0, "ok"))
    before = stored(warehouse)

    assert land(warehouse, (T0, 20.0, "suspect"), (T1, 21.0, "ok"), run_id="run2") == 1

    after = stored(warehouse)
    t0 = T0.replace(tzinfo=UTC)
    t1 = T1.replace(tzinfo=UTC)
    assert after[t0][:3] == (20.0, "suspect", "run2")
    assert after[t0][3] > before[t0][3]  # dbt picks the row up again through updated_at
    assert after[t1] == before[t1]


def test_the_last_loaded_day_comes_from_successful_runs_only(warehouse):
    assert warehouse.last_loaded_day(SOURCE, "mallorca") is None
    warehouse.start_run("run1", SOURCE, "mallorca", WINDOW)
    warehouse.finish_run("run1", SOURCE, "success")
    later = TimeWindow(date(2026, 11, 1), date(2026, 11, 2))
    warehouse.start_run("run2", SOURCE, "mallorca", later)
    warehouse.finish_run("run2", SOURCE, "unavailable", error="ConnectTimeout: upstream down")  # the source was down
    warehouse.start_run("run3", SOURCE, "mallorca", later)
    warehouse.finish_run("run3", SOURCE, "failed", error="KeyError: 'fecha'")  # our side

    assert warehouse.last_loaded_day(SOURCE, "mallorca") == WINDOW.end


def test_missing_days_are_the_ones_no_successful_run_covered(warehouse):
    week = TimeWindow(date(2026, 10, 26), date(2026, 11, 1))
    warehouse.start_run("run1", SOURCE, "mallorca", TimeWindow(date(2026, 10, 26), date(2026, 10, 27)))
    warehouse.finish_run("run1", SOURCE, "success")
    warehouse.start_run("run2", SOURCE, "mallorca", TimeWindow(date(2026, 10, 30), date(2026, 10, 30)))
    warehouse.finish_run("run2", SOURCE, "success")
    warehouse.start_run("run3", SOURCE, "mallorca", TimeWindow(date(2026, 10, 28), date(2026, 10, 29)))
    warehouse.finish_run("run3", SOURCE, "failed", error="ConnectTimeout: upstream down")

    missing = warehouse.missing_days(SOURCE, "mallorca", week)

    assert missing == [date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 31), date(2026, 11, 1)]
    assert warehouse.missing_days(SOURCE, "menorca", WINDOW) == [WINDOW.start, WINDOW.end]  # another region


def test_a_retried_run_starts_again_from_running(warehouse):
    warehouse.start_run("run1", SOURCE, "mallorca", WINDOW)
    warehouse.finish_run("run1", SOURCE, "failed", error="ConnectTimeout: upstream down")
    warehouse.start_run("run1", SOURCE, "mallorca", WINDOW)

    with warehouse.connect() as conn:
        status, error, finished = conn.execute(
            "SELECT status, error, finished_at FROM ops.ingestion_runs WHERE run_id = 'run1' AND source = %s",
            (SOURCE,),
        ).fetchone()
    assert (status, error, finished) == ("running", None, None)


def test_a_run_left_running_is_closed_as_failed_by_the_next_one(warehouse):
    warehouse.start_run("old", SOURCE, "mallorca", WINDOW)  # the computer was turned off during this one
    warehouse.start_run("recent", SOURCE, "mallorca", WINDOW)  # still going (another task of the same source)
    with warehouse.connect() as conn:
        conn.execute(
            "UPDATE ops.ingestion_runs SET started_at = now() - %s WHERE run_id = 'old' AND source = %s",
            (ABANDONED_AFTER + timedelta(minutes=1), SOURCE),
        )

    warehouse.start_run("new", SOURCE, "mallorca", WINDOW)

    with warehouse.connect() as conn:
        found = conn.execute(
            "SELECT run_id, status, error, finished_at IS NOT NULL FROM ops.ingestion_runs WHERE source = %s",
            (SOURCE,),
        ).fetchall()
    rows = {run_id: tuple(rest) for run_id, *rest in found}
    assert rows["old"] == ("failed", INTERRUPTED_ERROR, True)
    assert rows["recent"] == ("running", None, False)
    assert rows["new"] == ("running", None, False)


def test_quality_results_of_a_rerun_overwrite_the_previous_ones(warehouse):
    def result(failed):
        return SimpleNamespace(
            rule="range", target="temperature", checked=24, failed=failed, passed=not failed, details=None
        )

    warehouse.record_quality("run1", SOURCE, WINDOW, [result(3)])
    warehouse.record_quality("run1", SOURCE, WINDOW, [result(0)])

    with warehouse.connect() as conn:
        rows = conn.execute("SELECT failed, passed FROM quality.check_results WHERE source = %s", (SOURCE,)).fetchall()
    assert rows == [(0, True)]


def test_anomalies_are_replaced_only_inside_the_window_and_for_the_detector(warehouse):
    def anomaly(ts, detector="robust_zscore"):
        return (SOURCE, "palma", "temperature", ts.replace(tzinfo=UTC), detector, 30.0, 20.0, 5.0, 3.5)

    outside = datetime(2026, 10, 29, 9, tzinfo=UTC)
    warehouse.replace_anomalies("robust_zscore", [SOURCE], WINDOW, [anomaly(outside), anomaly(T0)], "run1")
    warehouse.replace_anomalies("isolation_forest", [SOURCE], WINDOW, [anomaly(T0, "isolation_forest")], "run1")

    warehouse.replace_anomalies("robust_zscore", [SOURCE], WINDOW, [anomaly(T1)], "run2")

    with warehouse.connect() as conn:
        rows = conn.execute(
            "SELECT detector, ts FROM silver.anomalies WHERE source = %s ORDER BY detector, ts", (SOURCE,)
        ).fetchall()
    assert rows == [
        ("isolation_forest", T0.replace(tzinfo=UTC)),
        ("robust_zscore", outside),
        ("robust_zscore", T1.replace(tzinfo=UTC)),
    ]


def names(warehouse):
    with warehouse.connect() as conn:
        rows = conn.execute("SELECT entity, name, run_id FROM silver.entities WHERE source = %s", (SOURCE,)).fetchall()
    return {entity: (name, run_id) for entity, name, run_id in rows}


def test_entity_names_are_upserted_and_only_a_rename_counts(warehouse):
    stops = [Entity(SOURCE, "stop_1", "Plaça d'Espanya"), Entity(SOURCE, "stop_2", "Sindicat")]
    assert warehouse.merge_entities(stops, "run1") == 2

    renamed = [Entity(SOURCE, "stop_1", "Plaça d'Espanya"), Entity(SOURCE, "stop_2", "Sindicat - intercanvi")]
    assert warehouse.merge_entities(renamed, "run2") == 1
    assert names(warehouse) == {"stop_1": ("Plaça d'Espanya", "run1"), "stop_2": ("Sindicat - intercanvi", "run2")}


def heights(warehouse):
    with warehouse.connect() as conn:
        rows = conn.execute("SELECT entity, elevation_m FROM silver.entities WHERE source = %s", (SOURCE,)).fetchall()
    return dict(rows)


def test_entity_heights_are_kept_when_a_payload_has_none(warehouse):
    assert warehouse.merge_entities([Entity(SOURCE, "lluc", "Lluc", 490.0)], "run1") == 1

    # A payload that does not publish heights neither erases the stored one nor counts as a change.
    assert warehouse.merge_entities([Entity(SOURCE, "lluc", "Lluc")], "run2") == 0
    assert heights(warehouse) == {"lluc": 490.0}

    assert warehouse.merge_entities([Entity(SOURCE, "lluc", "Lluc", 491.0)], "run3") == 1
    assert heights(warehouse) == {"lluc": 491.0}


def route(name, path=((2.65, 39.57), (2.66, 39.58)), color="#44743f"):
    return Route(SOURCE, f"route_{name}", name, f"{name} · Portopí - Sindicat", "bus", color, (path,))


def routes(warehouse):
    with warehouse.connect() as conn:
        rows = conn.execute(
            "SELECT route, color, geometry, run_id FROM silver.routes WHERE source = %s ORDER BY route", (SOURCE,)
        ).fetchall()
    return {r: (color, geometry["coordinates"], run_id) for r, color, geometry, run_id in rows}


def test_routes_are_replaced_and_only_a_change_counts(warehouse):
    assert warehouse.replace_routes(SOURCE, [route("1"), route("2")], "run1") == 2

    # Line 1 unchanged, line 2 recoloured, line 3 new: two changes.
    assert warehouse.replace_routes(SOURCE, [route("1"), route("2", color="#b78dba"), route("3")], "run2") == 2
    assert routes(warehouse)["route_1"] == ("#44743f", [[[2.65, 39.57], [2.66, 39.58]]], "run1")
    assert routes(warehouse)["route_2"][0::2] == ("#b78dba", "run2")

    # Line 3 no longer runs: the next feed without it removes it.
    assert warehouse.replace_routes(SOURCE, [route("1"), route("2", color="#b78dba")], "run3") == 1
    assert set(routes(warehouse)) == {"route_1", "route_2"}
