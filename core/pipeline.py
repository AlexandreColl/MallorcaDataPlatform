"""End-to-end pipeline for one connector: API -> bronze -> silver (+quality) -> warehouse.

Each stage is a separate function so that silver can be rebuilt from bronze
without calling the APIs again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from core.config import Settings, load_region
from core.connectors import BaseConnector, registry
from core.models import Observation, Region, TimeWindow
from core.quality import QualityEngine, RuleResult, rules_for
from core.spark import SILVER_SCHEMA, build_spark
from core.storage import BronzeStore, ensure_bucket
from core.warehouse import RunStats, Warehouse

log = logging.getLogger(__name__)


class NoObservationsError(RuntimeError):
    """A connector produced no observations for the requested window."""


@dataclass
class RunSummary:
    """Outcome of one connector run, returned to Airflow as XCom."""

    run_id: str
    source: str
    region: str
    window_start: str
    window_end: str
    payloads: int
    rows_silver: int
    rows_upserted: int
    checks_failed: int

    def as_dict(self) -> dict[str, Any]:
        """Plain dict (JSON-serialisable)."""
        return asdict(self)


def new_run_id() -> str:
    """Run id for executions launched outside Airflow."""
    return f"manual__{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def extract_to_bronze(connector: BaseConnector, window: TimeWindow, region: Region, store: BronzeStore) -> list[str]:
    """Call the source API and land every raw response in bronze. Returns the object keys."""
    payloads = connector.extract(window, region)
    return [store.put(p) for p in payloads]


def bronze_to_observations(
    connector: BaseConnector, keys: list[str], region: Region, store: BronzeStore
) -> list[Observation]:
    """Read raw payloads back from bronze and normalise them to the common schema."""
    return [obs for key in keys for obs in connector.normalize(store.get(key), region)]


def to_dataframe(spark: SparkSession, observations: list[Observation], run_id: str) -> DataFrame:
    """Build the silver DataFrame with lineage columns (`run_id`, `ingested_at`)."""
    rows = [o.as_row() for o in observations]
    df = spark.createDataFrame(rows, schema=SILVER_SCHEMA)
    return df.withColumn("run_id", F.lit(run_id)).withColumn("ingested_at", F.current_timestamp())


def deduplicate(df: DataFrame) -> DataFrame:
    """Keep one row per key; prefer a non-null value."""
    w = Window.partitionBy("source", "entity", "metric", "ts").orderBy(F.col("value").isNull().asc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def apply_quality(df: DataFrame, connector: BaseConnector, window: TimeWindow) -> tuple[DataFrame, list[RuleResult]]:
    """Label rows with the connector's rule set, then collapse duplicates."""
    flagged, results = QualityEngine(rules_for(connector.config, window)).run(df)
    return deduplicate(flagged), results


def write_silver(df: DataFrame, settings: Settings, landing_table: str) -> None:
    """Write silver to the Parquet lake and to a Postgres landing table."""
    # 1) Parquet lake (S3A -> MinIO). Dynamic partition overwrite = idempotent per day.
    (
        df.withColumn("date", F.to_date("ts"))
        .write.mode("overwrite")
        .partitionBy("source", "date")
        .parquet(f"s3a://{settings.silver_bucket}/observations")
    )
    # 2) Landing table in Postgres via JDBC; merged into silver.observations afterwards.
    (
        df.write.format("jdbc")
        .option("url", settings.jdbc_url)
        .option("dbtable", f"landing.{landing_table}")
        .option("user", settings.warehouse_user)
        .option("password", settings.warehouse_password)
        .option("driver", "org.postgresql.Driver")
        .option("truncate", "true")
        .mode("overwrite")
        .save()
    )


def _load_observations(
    connector: BaseConnector, window: TimeWindow, region: Region, store: BronzeStore
) -> tuple[list[str], list[Observation]]:
    keys = extract_to_bronze(connector, window, region, store)
    observations = bronze_to_observations(connector, keys, region, store)
    if not observations and not connector.config.is_event_source:
        msg = f"connector '{connector.name}' returned no observations for {window}"
        raise NoObservationsError(msg)
    return keys, observations


def _load_silver(
    connector: BaseConnector, observations: list[Observation], window: TimeWindow, run_id: str, warehouse: Warehouse
) -> tuple[int, int, list[RuleResult]]:
    """Quality-label the observations and load them into silver. Returns (rows, upserted, rule results)."""
    settings = warehouse.settings
    spark = build_spark(settings, app_name=f"mdp-{connector.name}")
    silver, results = apply_quality(to_dataframe(spark, observations, run_id), connector, window)
    silver = silver.cache()
    rows_silver = silver.count()

    landing_table = f"observations_{connector.name}"
    write_silver(silver, settings, landing_table)
    upserted = warehouse.merge_observations(landing_table)
    silver.unpersist()
    return rows_silver, upserted, results


def run_connector(  # noqa: PLR0913 - everything after `days` is keyword-only
    name: str,
    days: int,
    *,
    region_name: str = "mallorca",
    run_id: str | None = None,
    settings: Settings | None = None,
    catch_up: bool = True,
) -> RunSummary:
    """Run one connector end to end and record the run in ``ops.ingestion_runs``.

    With ``catch_up`` the window grows back to the day after the last successful run (up to the
    connector's ``catch_up_days``), so a source that was down is recovered by its next run.
    """
    settings = settings or Settings.from_env()
    run_id = run_id or new_run_id()
    region = load_region(region_name, settings.regions_dir)
    window = TimeWindow.last_days(days)
    connector = registry.load(name, connectors_dir=settings.connectors_dir)
    connector.validate_window(window)

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    if catch_up:
        requested = window
        window = window.catch_up(warehouse.last_loaded_day(name, region.name), connector.config.catch_up_days)
        if window != requested:
            log.warning("run %s: %s catching up missed days, window %s..%s", run_id, name, window.start, window.end)
    warehouse.start_run(run_id, name, region.name, window)
    log.info("run %s: %s %s..%s (%s)", run_id, name, window.start, window.end, region.name)

    try:
        store = BronzeStore(settings)
        store.ensure()
        keys, observations = _load_observations(connector, window, region, store)
        if observations:
            ensure_bucket(store.client, settings.silver_bucket)
            rows_silver, upserted, results = _load_silver(connector, observations, window, run_id, warehouse)
            warehouse.record_quality(run_id, name, window, results)
        else:  # event source with no events in the window: raw response kept in bronze, nothing to load
            log.info("run %s: no %s events in %s..%s", run_id, name, window.start, window.end)
            rows_silver, upserted, results = 0, 0, []
    except Exception as exc:
        # The exception type lets readers tell an upstream outage (ConnectTimeout, HTTPError 503...) from a bug.
        warehouse.finish_run(run_id, name, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])
        raise
    else:
        stats = RunStats(payloads=len(keys), rows_silver=rows_silver, rows_upserted=upserted)
        warehouse.finish_run(run_id, name, "success", stats=stats)
        summary = RunSummary(
            run_id=run_id,
            source=name,
            region=region.name,
            window_start=window.start.isoformat(),
            window_end=window.end.isoformat(),
            payloads=stats.payloads,
            rows_silver=stats.rows_silver,
            rows_upserted=stats.rows_upserted,
            checks_failed=sum(1 for r in results if not r.passed),
        )
        log.info("run summary: %s", summary.as_dict())
        return summary
