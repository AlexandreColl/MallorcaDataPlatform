"""The silver lake as a Delta Lake table: ACID upserts with MERGE, a commit history and time travel.

Spark used to overwrite the ``source=…/date=…`` Parquet partitions of each run. The same directory is now a Delta
table (the Parquet files plus a ``_delta_log`` of JSON commits):

* each run MERGEs its rows on the key (source, entity, metric, ts), and rows whose content did not change are left
  alone, like the Postgres upsert: a rerun that changes nothing rewrites no file and commits no version;
* every commit is a version: ``history`` lists them with their row counts and ``snapshot`` reads the table as it was
  at a version or a time (time travel);
* the existing Parquet partitions are converted in place the first time (``CONVERT TO DELTA``), without rewriting
  them.

Delta on S3 has no atomic "put if absent" from Spark, so two drivers committing at once could overwrite each other's
commit. The pipeline runs two connectors at a time (two Spark drivers), so commits are serialised with a Postgres
advisory lock held around each write: the lock is the "single writer" that S3 lacks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pyspark.sql import functions as F

from core.warehouse import Warehouse

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from pyspark.sql import DataFrame, SparkSession

    from core.config import Settings

log = logging.getLogger(__name__)

DELTA_SPARK_CONFIG = {
    "spark.sql.extensions": "io.delta.sql.DeltaSparkSessionExtension",
    "spark.sql.catalog.spark_catalog": "org.apache.spark.sql.delta.catalog.DeltaCatalog",
}
# Advisory lock key of the silver writers (7302 is the DDL).
SILVER_LOCK = 7303
KEY = ("source", "entity", "metric", "ts")
PARTITIONS = ("source", "date")
# Columns whose change counts as a real update (run_id / ingested_at always differ), as in core/warehouse.py.
COMPARED = ("value", "unit", "quality", "quality_reasons", "lat", "lon")
# The commit metrics shown by `history` (Delta names them per operation).
_METRICS = {
    "inserted": ("numTargetRowsInserted", "numOutputRows"),
    "updated": ("numTargetRowsUpdated",),
    "files_added": ("numTargetFilesAdded", "numFiles", "numAddedFiles"),
    "files_removed": ("numTargetFilesRemoved", "numRemovedFiles"),
}


@dataclass(frozen=True)
class MergeResult:
    """What one MERGE committed."""

    version: int
    inserted: int
    updated: int


class SilverTable:
    """The Delta table of clean observations, partitioned by source and day."""

    def __init__(self, spark: SparkSession, path: str, lock: Callable[[], AbstractContextManager[Any]]) -> None:
        self.spark = spark
        self.path = path
        self._lock = lock

    @property
    def _table(self) -> str:
        return f"delta.`{self.path}`"

    def is_delta(self) -> bool:
        """True once the directory has a Delta transaction log."""
        jvm = self.spark._jvm  # noqa: SLF001 - the Delta Python package pins an older PySpark: use its JVM API
        return bool(jvm.io.delta.tables.DeltaTable.isDeltaTable(self.spark._jsparkSession, self.path))  # noqa: SLF001

    def _has_files(self) -> bool:
        jvm = self.spark._jvm  # noqa: SLF001
        path = jvm.org.apache.hadoop.fs.Path(self.path)
        fs = path.getFileSystem(self.spark._jsc.hadoopConfiguration())  # noqa: SLF001
        return bool(fs.exists(path))

    def ensure(self) -> None:
        """Convert the Parquet partitions written before Delta into a Delta table (once, in place)."""
        if self.is_delta() or not self._has_files():
            return
        log.warning("silver %s is plain Parquet: converting it to Delta", self.path)
        self.spark.sql(f"CONVERT TO DELTA parquet.`{self.path}` PARTITIONED BY (source STRING, date DATE)")

    def merge(self, df: DataFrame) -> MergeResult:
        """Upsert the rows of one connector run on the key; unchanged rows are not rewritten.

        Rows already in the table with the same content are dropped first: Delta rewrites every file holding a matched
        row, so a rerun would rewrite the window's files for nothing. A run that changes nothing commits no version.
        """
        rows = df.withColumn("date", F.to_date("ts"))
        with self._lock():
            self.ensure()
            if not self.is_delta():  # the first run creates the table
                rows.write.format("delta").partitionBy(*PARTITIONS).save(self.path)
                inserted = rows.count()
                log.info("silver: created Delta table %s with %d rows", self.path, inserted)
                return MergeResult(version=0, inserted=inserted, updated=0)
            pruning = self._pruning(rows)
            pending = self._changed_rows(rows, pruning).cache()
            if pending.isEmpty():
                pending.unpersist()
                version = self.history(limit=1)[0]["version"]
                log.info("silver: no row changed, the table stays at version %d", version)
                return MergeResult(version=version, inserted=0, updated=0)
            self._merge(pending, pruning)
            pending.unpersist()
            commit = self.history(limit=1)[0]
        log.info(
            "silver: version %d, %d rows inserted and %d updated",
            commit["version"],
            commit["inserted"],
            commit["updated"],
        )
        return MergeResult(version=commit["version"], inserted=commit["inserted"], updated=commit["updated"])

    @staticmethod
    def _pruning(rows: DataFrame) -> str:
        """Literal partition values of the run: Delta prunes the target files and other sources' writers stay apart."""
        bounds = rows.agg(F.min("date").alias("first"), F.max("date").alias("last")).first()
        sources = ", ".join(f"'{r['source']}'" for r in rows.select("source").distinct().collect())  # [a-z0-9_]
        return f"t.source IN ({sources}) AND t.date BETWEEN '{bounds['first']}' AND '{bounds['last']}'"

    def _changed_rows(self, rows: DataFrame, pruning: str) -> DataFrame:
        """The rows that are new or differ from the table in a compared column."""
        current = self.snapshot().alias("t").where(pruning)
        same = [F.col(f"s.{c}") == F.col(f"t.{c}") for c in KEY] + [
            F.col(f"s.{c}").eqNullSafe(F.col(f"t.{c}")) for c in COMPARED
        ]
        return rows.alias("s").join(current, on=same, how="left_anti")

    def _merge(self, rows: DataFrame, pruning: str) -> None:
        view = "silver_updates"
        rows.createOrReplaceTempView(view)
        on = " AND ".join(f"t.{c} = s.{c}" for c in (*KEY, "date"))
        self.spark.sql(
            f"""
            MERGE INTO {self._table} AS t
            USING {view} AS s
            ON {on} AND {pruning}
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        self.spark.catalog.dropTempView(view)

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        """The latest commits, newest first: version, time, operation and row and file counts."""
        rows = self.spark.sql(f"DESCRIBE HISTORY {self._table} LIMIT {int(limit)}").collect()
        return [
            {
                "version": r["version"],
                "timestamp": r["timestamp"],
                "operation": r["operation"],
                **{name: _metric(r["operationMetrics"] or {}, keys) for name, keys in _METRICS.items()},
            }
            for r in rows
        ]

    def snapshot(self, *, version: int | None = None, timestamp: str | None = None) -> DataFrame:
        """The table as it was at a version or a time (``YYYY-MM-DD[ HH:MM:SS]``, UTC)."""
        reader = self.spark.read.format("delta")
        if version is not None:
            reader = reader.option("versionAsOf", version)
        elif timestamp is not None:
            reader = reader.option("timestampAsOf", timestamp)
        return reader.load(self.path)

    def changes(self, version: int) -> DataFrame:
        """Rows that differ between a past version and now, by key: added, removed or changed."""
        before, now = self.snapshot(version=version).alias("b"), self.snapshot().alias("n")
        keys = [F.col(f"b.{c}") == F.col(f"n.{c}") for c in KEY]
        joined = before.join(now, on=keys, how="full_outer")
        change = (
            F.when(F.col("b.source").isNull(), "added")
            .when(F.col("n.source").isNull(), "removed")
            .when(~F.expr(" AND ".join(f"b.{c} <=> n.{c}" for c in COMPARED)), "changed")
        )
        return (
            joined.withColumn("change", change)
            .where(F.col("change").isNotNull())
            .select(
                *(F.coalesce(F.col(f"n.{c}"), F.col(f"b.{c}")).alias(c) for c in KEY),
                F.col("b.value").alias("value_before"),
                F.col("n.value").alias("value_now"),
                F.col("b.quality").alias("quality_before"),
                F.col("n.quality").alias("quality_now"),
                "change",
            )
        )

    def maintain(self, retain_hours: int = 168) -> None:
        """Compact the small files of each partition, then delete files unreferenced for ``retain_hours``.

        Time travel only reaches back as far as the files VACUUM keeps.
        """
        with self._lock():
            self.spark.sql(f"OPTIMIZE {self._table}")
            self.spark.sql(f"VACUUM {self._table} RETAIN {int(retain_hours)} HOURS")


def _metric(metrics: dict[str, str], keys: tuple[str, ...]) -> int:
    return next((int(metrics[k]) for k in keys if k in metrics), 0)


def open_silver(spark: SparkSession, settings: Settings) -> SilverTable:
    """The silver table of these settings, its writers serialised by the warehouse's advisory lock."""
    warehouse = Warehouse(settings)
    return SilverTable(spark, f"s3a://{settings.silver_bucket}/observations", lock=lambda: warehouse.lock(SILVER_LOCK))
