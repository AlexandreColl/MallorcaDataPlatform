"""End-to-end pipeline for one connector: API -> bronze -> silver (+quality) -> warehouse.

Each stage is a separate function so that silver can be rebuilt from bronze
without calling the APIs again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from core.config import Settings, load_region
from core.connectors import BaseConnector, registry
from core.models import Observation, Region, TimeWindow
from core.quality import QualityEngine, RuleResult, rules_for
from core.spark import SILVER_SCHEMA, build_spark
from core.storage import BronzeStore, ensure_bucket
from core.warehouse import Warehouse

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    run_id: str
    source: str
    region: str
    window_start: str
    window_end: str
    payloads: int
    rows_silver: int
    rows_upserted: int
    checks_failed: int

    def as_dict(self) -> dict:
        return asdict(self)


def new_run_id() -> str:
    return f"manual__{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def extract_to_bronze(
    connector: BaseConnector, window: TimeWindow, region: Region, store: BronzeStore
) -> list[str]:
    payloads = connector.extract(window, region)
    return [store.put(p) for p in payloads]


def bronze_to_observations(
    connector: BaseConnector, keys: list[str], region: Region, store: BronzeStore
) -> list[Observation]:
    observations: list[Observation] = []
    for key in keys:
        observations.extend(connector.normalize(store.get(key), region))
    return observations


def to_dataframe(spark: SparkSession, observations: list[Observation], run_id: str) -> DataFrame:
    rows = [o.as_row() for o in observations]
    df = spark.createDataFrame(rows, schema=SILVER_SCHEMA)
    return df.withColumn("run_id", F.lit(run_id)).withColumn("ingested_at", F.current_timestamp())


def deduplicate(df: DataFrame) -> DataFrame:
    """Keep one row per key; prefer a non-null value."""
    w = Window.partitionBy("source", "entity", "metric", "ts").orderBy(
        F.col("value").isNull().asc()
    )
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def apply_quality(
    df: DataFrame, connector: BaseConnector, window: TimeWindow
) -> tuple[DataFrame, list[RuleResult]]:
    flagged, results = QualityEngine(rules_for(connector.config, window)).run(df)
    return deduplicate(flagged), results


def write_silver(df: DataFrame, settings: Settings, landing_table: str) -> None:
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


def run_connector(
    name: str,
    days: int,
    region_name: str = "mallorca",
    run_id: str | None = None,
    settings: Settings | None = None,
    spark: SparkSession | None = None,
) -> RunSummary:
    settings = settings or Settings.from_env()
    run_id = run_id or new_run_id()
    region = load_region(region_name, settings.regions_dir)
    window = TimeWindow.last_days(days)
    connector = registry.load(name, connectors_dir=settings.connectors_dir)
    connector.validate_window(window)

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    warehouse.start_run(run_id, name, region.name, window)
    log.info("run %s: %s %s..%s (%s)", run_id, name, window.start, window.end, region.name)

    try:
        store = BronzeStore(settings)
        store.ensure()
        keys = extract_to_bronze(connector, window, region, store)
        observations = bronze_to_observations(connector, keys, region, store)
        if not observations:
            raise RuntimeError(f"connector '{name}' returned no observations for {window}")

        spark = spark or build_spark(settings, app_name=f"mdp-{name}")
        ensure_bucket(store.client, settings.silver_bucket)
        df = to_dataframe(spark, observations, run_id)
        silver, results = apply_quality(df, connector, window)
        silver = silver.cache()
        rows_silver = silver.count()

        landing_table = f"observations_{name}"
        write_silver(silver, settings, landing_table)
        upserted = warehouse.merge_observations(landing_table)
        warehouse.record_quality(run_id, name, window, results)
        silver.unpersist()

        failed_checks = sum(1 for r in results if not r.passed)
        warehouse.finish_run(run_id, name, "success", len(keys), rows_silver, upserted)
        summary = RunSummary(
            run_id=run_id,
            source=name,
            region=region.name,
            window_start=window.start.isoformat(),
            window_end=window.end.isoformat(),
            payloads=len(keys),
            rows_silver=rows_silver,
            rows_upserted=upserted,
            checks_failed=failed_checks,
        )
        log.info("run summary: %s", summary.as_dict())
        return summary
    except Exception as exc:
        warehouse.finish_run(run_id, name, "failed", error=str(exc)[:2000])
        raise
