from contextlib import contextmanager
from datetime import datetime

import pytest
from pyspark.sql import functions as F

from core.lake import SilverTable

pytestmark = pytest.mark.spark

T0 = datetime(2026, 10, 30, 9)  # noqa: DTZ001 - the session time zone is UTC
T1 = datetime(2026, 10, 31, 9)  # noqa: DTZ001


def _rows(spark, *rows, run_id="run1"):
    data = [
        (source, "palma", metric, ts, value, "C", quality, None, 39.5, 2.6, run_id)
        for source, metric, ts, value, quality in rows
    ]
    return spark.createDataFrame(
        data,
        "source string, entity string, metric string, ts timestamp, value double, unit string, quality string,"
        " quality_reasons string, lat double, lon double, run_id string",
    )


@pytest.fixture
def table(spark, tmp_path):
    locks = []

    @contextmanager
    def lock():
        locks.append("held")
        yield

    silver = SilverTable(spark, str(tmp_path / "observations"), lock=lock)
    silver.locks = locks
    return silver


def _values(df):
    return {(r["source"], r["metric"], r["ts"]): r["value"] for r in df.collect()}


def test_the_first_run_creates_the_table_partitioned_by_source_and_day(table, spark):
    result = table.merge(
        _rows(spark, ("aemet", "temperature", T0, 20.0, "ok"), ("aemet", "temperature", T1, 21.0, "ok"))
    )

    assert (result.version, result.inserted, result.updated) == (0, 2, 0)
    assert table.is_delta()
    detail = spark.sql(f"DESCRIBE DETAIL delta.`{table.path}`").first()
    assert detail["partitionColumns"] == ["source", "date"]
    assert table.locks == ["held"]


def test_a_rerun_with_the_same_values_updates_nothing(table, spark):
    rows = _rows(spark, ("aemet", "temperature", T0, 20.0, "ok"))
    table.merge(rows)

    result = table.merge(_rows(spark, ("aemet", "temperature", T0, 20.0, "ok"), run_id="run2"))

    assert (result.version, result.inserted, result.updated) == (1, 0, 0)
    assert table.snapshot().count() == 1
    assert table.snapshot().first()["run_id"] == "run1"  # an unchanged row keeps the run that wrote it


def test_changed_values_are_updated_and_new_keys_inserted(table, spark):
    table.merge(_rows(spark, ("aemet", "temperature", T0, 20.0, "ok"), ("socib", "temperature", T0, 18.0, "ok")))

    result = table.merge(
        _rows(spark, ("aemet", "temperature", T0, 20.5, "ok"), ("aemet", "temperature", T1, 21.0, "ok"))
    )

    assert (result.inserted, result.updated) == (1, 1)
    assert _values(table.snapshot()) == {
        ("aemet", "temperature", T0): 20.5,
        ("aemet", "temperature", T1): 21.0,
        ("socib", "temperature", T0): 18.0,  # another source's partition is never touched
    }


def test_time_travel_reads_a_past_version_and_lists_the_changes(table, spark):
    table.merge(_rows(spark, ("aemet", "temperature", T0, 20.0, "ok")))
    table.merge(_rows(spark, ("aemet", "temperature", T0, None, "missing"), ("aemet", "temperature", T1, 21.0, "ok")))

    assert _values(table.snapshot(version=0)) == {("aemet", "temperature", T0): 20.0}
    changes = {(r["ts"], r["change"]): (r["value_before"], r["value_now"]) for r in table.changes(0).collect()}
    assert changes == {(T0, "changed"): (20.0, None), (T1, "added"): (None, 21.0)}


def test_history_lists_the_commits_newest_first(table, spark):
    table.merge(_rows(spark, ("aemet", "temperature", T0, 20.0, "ok")))
    table.merge(_rows(spark, ("aemet", "temperature", T0, 19.0, "ok")))

    history = table.history()

    assert [(h["version"], h["operation"]) for h in history] == [(1, "MERGE"), (0, "WRITE")]
    assert (history[0]["inserted"], history[0]["updated"]) == (0, 1)
    assert history[1]["inserted"] == 1


def test_parquet_partitions_written_before_delta_are_converted_in_place(table, spark):
    old = _rows(spark, ("aemet", "temperature", T0, 20.0, "ok")).withColumn("date", F.to_date("ts"))
    old.write.partitionBy("source", "date").parquet(table.path)
    assert not table.is_delta()

    result = table.merge(
        _rows(spark, ("aemet", "temperature", T0, 20.0, "ok"), ("aemet", "temperature", T1, 21.0, "ok"))
    )

    assert table.is_delta()
    assert [h["operation"] for h in table.history()] == ["MERGE", "CONVERT"]
    assert (result.inserted, result.updated) == (1, 0)  # the converted row is matched, not duplicated
    assert table.snapshot().count() == 2


def test_maintenance_compacts_and_keeps_the_current_rows(table, spark):
    for value in (20.0, 20.5, 21.0):
        table.merge(_rows(spark, ("aemet", "temperature", T0, value, "ok")))

    table.maintain(retain_hours=168)

    assert "VACUUM END" in [h["operation"] for h in table.history()]
    assert _values(table.snapshot()) == {("aemet", "temperature", T0): 21.0}
    assert len(table.locks) == 4
