"""The warehouse writes against a real Postgres: the upsert behind idempotent reruns, run tracking and replacements.

Runs only with ``WAREHOUSE_INTEGRATION=1`` and the DDL of ``core/sql/warehouse.sql`` applied (CI runs it on the
dbt job's Postgres; locally it can point at the stack's warehouse). Every row uses the source ``test_warehouse`` and
is deleted afterwards.
"""

import os
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.models import TimeWindow
from core.warehouse import Warehouse

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
        for table in ("silver.observations", "silver.anomalies", "ops.ingestion_runs", "quality.check_results"):
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
    warehouse.finish_run("run2", SOURCE, "failed", error="ConnectTimeout: upstream down")

    assert warehouse.last_loaded_day(SOURCE, "mallorca") == WINDOW.end


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
