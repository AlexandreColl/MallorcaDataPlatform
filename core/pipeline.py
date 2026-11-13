"""End-to-end pipeline for one connector: API -> bronze -> silver (+quality) -> warehouse.

Each stage is a separate function so that silver can be rebuilt from bronze
without calling the APIs again.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from core.config import Settings, load_region
from core.connectors import BaseConnector, is_outage, registry
from core.lake import open_silver
from core.models import KEY, TimeWindow
from core.quality import QualityEngine, RuleResult, rules_for
from core.spark import SILVER_SCHEMA, build_spark
from core.storage import BronzeStore, ensure_bucket
from core.warehouse import RunStats, Warehouse

if TYPE_CHECKING:
    from datetime import date

    from core.models import Entity, Observation, Region, Route

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
    # True when every day of the window was already loaded (only_missing): nothing was downloaded.
    skipped: bool = False
    # Days of an older gap loaded first, in runs of their own (catch-up beyond catch_up_days, up to recover_days).
    recovered_days: int = 0

    @classmethod
    def of(  # noqa: PLR0913 - the outcome of a run, keyword-only after the window
        cls,
        run_id: str,
        source: str,
        region: str,
        window: TimeWindow,
        *,
        stats: RunStats | None = None,
        checks_failed: int = 0,
        skipped: bool = False,
    ) -> RunSummary:
        """The summary of a run of ``window``; without ``stats`` nothing was downloaded."""
        stats = stats or RunStats(payloads=0, rows_silver=0, rows_upserted=0)
        return cls(
            run_id=run_id,
            source=source,
            region=region,
            window_start=window.start.isoformat(),
            window_end=window.end.isoformat(),
            payloads=stats.payloads,
            rows_silver=stats.rows_silver,
            rows_upserted=stats.rows_upserted,
            checks_failed=checks_failed,
            skipped=skipped,
        )

    def as_dict(self) -> dict[str, Any]:
        """Plain dict (JSON-serialisable)."""
        return asdict(self)


def remaining_window(window: TimeWindow, missing: list[date], *, rereads: bool) -> TimeWindow | None:
    """What is left to download of ``window`` when ``missing`` (sorted) are its days without a successful load.

    None when nothing is missing. Otherwise the window from its first missing day, so the days already loaded at its
    start are not asked for again. A source that re-reads on purpose (``rereads``: its ``min_days`` window picks
    up the publisher's revisions) keeps its whole window as soon as one day is missing.
    """
    if not missing:
        return None
    if rereads:
        return window
    return TimeWindow(max(window.start, missing[0]), window.end)


def recovery_windows(
    window: TimeWindow, last_loaded: date | None, recover_days: int, chunk_days: int
) -> list[TimeWindow]:
    """The gap between ``last_loaded`` and ``window`` that the catch-up did not reach, in chunks of ``chunk_days``.

    The catch-up grows a run's window back to ``catch_up_days``: one request, which most APIs cap. When the source
    was down longer (or the computer off), the days before that window are loaded first, oldest first, but no
    further back than ``recover_days`` from the end of the window. A source that never loaded has no gap: its
    history is a backfill.
    """
    if last_loaded is None:
        return []
    start = max(last_loaded + timedelta(days=1), window.end - timedelta(days=recover_days - 1))
    if start >= window.start:
        return []
    return TimeWindow(start, window.start - timedelta(days=1)).split(chunk_days)


def _to_download(
    warehouse: Warehouse, connector: BaseConnector, region: Region, window: TimeWindow, run_id: str
) -> TimeWindow | None:
    """The part of ``window`` that no successful run of the connector has loaded yet (None: all of it is loaded)."""
    name = connector.config.name
    missing = warehouse.missing_days(name, region.name, window)
    remaining = remaining_window(window, missing, rereads=connector.config.min_days > 1)
    if remaining is None:
        log.info("run %s: %s already loaded for %s..%s, nothing to download", run_id, name, window.start, window.end)
    elif remaining != window:
        log.info("run %s: %s already loaded until %s, window %s..%s", run_id, name,
                 remaining.start - timedelta(days=1), remaining.start, remaining.end)  # fmt: skip
    return remaining


def new_run_id() -> str:
    """Run id for executions launched outside Airflow."""
    return f"manual__{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def extract_to_bronze(connector: BaseConnector, window: TimeWindow, region: Region, store: BronzeStore) -> list[str]:
    """Call the source API and land every raw response in bronze. Returns the object keys."""
    payloads = connector.extract(window, region)
    return [store.put(p) for p in payloads]


@dataclass
class Normalized:
    """What the payloads of a run hold: the observations, the names of their entities and the transit lines."""

    observations: list[Observation]
    entities: list[Entity]
    routes: list[Route]


def bronze_to_silver(connector: BaseConnector, keys: list[str], region: Region, store: BronzeStore) -> Normalized:
    """Read raw payloads back from bronze (once each) and normalise them: observations, entity names and routes."""
    observations: list[Observation] = []
    names: dict[str, Entity] = {}  # one name per entity: the same station is in several payloads
    routes: dict[str, Route] = {}  # one path per line: the latest payload wins
    for key in keys:
        payload = store.get(key)
        observations.extend(connector.normalize(payload, region))
        names.update((e.entity, e) for e in connector.describe(payload, region))
        routes.update((r.route, r) for r in connector.routes(payload, region))
    return Normalized(observations, list(names.values()), list(routes.values()))


def to_dataframe(spark: SparkSession, observations: list[Observation], run_id: str) -> DataFrame:
    """Build the silver DataFrame with lineage columns (`run_id`, `ingested_at`)."""
    rows = [o.as_row() for o in observations]
    df = spark.createDataFrame(rows, schema=SILVER_SCHEMA)
    return df.withColumn("run_id", F.lit(run_id)).withColumn("ingested_at", F.current_timestamp())


def deduplicate(df: DataFrame) -> DataFrame:
    """Keep one row per key; prefer a non-null value."""
    w = Window.partitionBy(*KEY).orderBy(F.col("value").isNull().asc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def apply_quality(df: DataFrame, connector: BaseConnector, window: TimeWindow) -> tuple[DataFrame, list[RuleResult]]:
    """Label rows with the connector's rule set, then collapse duplicates."""
    flagged, results = QualityEngine(rules_for(connector.config, window)).run(df)
    return deduplicate(flagged), results


def write_silver(df: DataFrame, settings: Settings, landing_table: str) -> None:
    """Upsert silver into the Delta lake and write it to a Postgres landing table."""
    # 1) Delta table (S3A -> MinIO), partitioned by source. MERGE on the key = idempotent reruns.
    open_silver(df.sparkSession, settings).merge(df)
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
) -> tuple[list[str], Normalized]:
    keys = extract_to_bronze(connector, window, region, store)
    normalized = bronze_to_silver(connector, keys, region, store)
    if not normalized.observations and not connector.config.is_event_source:
        msg = f"connector '{connector.name}' returned no observations for {window}"
        raise NoObservationsError(msg)
    return keys, normalized


def _load_silver(
    connector: BaseConnector, observations: list[Observation], window: TimeWindow, run_id: str, warehouse: Warehouse
) -> tuple[int, int, list[RuleResult]]:
    """Quality-label the observations and load them into silver. Returns (rows, upserted, rule results)."""
    settings = warehouse.settings
    spark = build_spark(settings, app_name=f"mdp-{connector.name}")
    silver, results = apply_quality(to_dataframe(spark, observations, run_id), connector, window)
    silver = silver.cache()
    try:
        rows_silver = silver.count()
        landing_table = f"observations_{connector.name}"
        write_silver(silver, settings, landing_table)
        upserted = warehouse.merge_observations(landing_table)
    finally:  # a failed write must not leave the rows cached in the next run of the same Spark session
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
    window: TimeWindow | None = None,
    only_missing: bool = False,
) -> RunSummary:
    """Run one connector end to end and record the run in ``ops.ingestion_runs``.

    With ``only_missing`` the days already covered by a successful load are not downloaded again: the window starts
    at its first missing day, and a window with nothing missing is skipped without calling the source (nor
    recording a run). With ``catch_up`` the window grows back to the day after the last successful run (up to the
    connector's ``catch_up_days``), so a source that was down is recovered by its next run; an older gap, up to
    ``recover_days``, is loaded first in runs of its own (see :func:`recovery_windows`).
    A ``window`` (backfills) replaces the last ``days``.
    """
    settings = settings or Settings.from_env()
    run_id = run_id or new_run_id()
    region = load_region(region_name, settings.regions_dir)
    connector = registry.load(name, connectors_dir=settings.connectors_dir)
    # An explicit window (backfills) replaces the last `days`, which end `lag_days` before yesterday.
    window = window or connector.config.window(days)
    connector.validate_window(window)

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    if only_missing:
        remaining = _to_download(warehouse, connector, region, window, run_id)
        if remaining is None:
            return RunSummary.of(run_id, name, region.name, window, skipped=True)
        window = remaining
    recovered_days = 0
    if catch_up:
        last_loaded = warehouse.last_loaded_day(name, region.name)
        requested = window
        window = window.catch_up(last_loaded, connector.config.catch_up_days)
        if window != requested:
            log.warning("run %s: %s catching up missed days, window %s..%s", run_id, name, window.start, window.end)
        recovered_days = _recover(connector, region, window, last_loaded, run_id=run_id, warehouse=warehouse)

    summary = _load_window(connector, region, window, run_id, warehouse)
    summary.recovered_days = recovered_days
    log.info("run summary: %s", summary.as_dict())
    return summary


def _recover(  # noqa: PLR0913 - the context of the run, keyword-only after the window
    connector: BaseConnector,
    region: Region,
    window: TimeWindow,
    last_loaded: date | None,
    *,
    run_id: str,
    warehouse: Warehouse,
) -> int:
    """Load the gap older than ``window`` (since ``last_loaded``), oldest first, one run per chunk.

    Each chunk is a run of its own (``<run_id>_<first day>``, like a backfill), so a failure stops the recovery with
    the earlier chunks recorded and the next run resumes after them. Returns the number of days recovered.
    """
    config = connector.config
    chunks = recovery_windows(window, last_loaded, config.recover_days, config.catch_up_days)
    if last_loaded is not None and chunks and chunks[0].start > last_loaded + timedelta(days=1):
        log.warning("run %s: %s missed %s..%s, beyond recover_days (%d): load it with `make backfill`", run_id,
                    config.name, last_loaded + timedelta(days=1), chunks[0].start - timedelta(days=1),
                    config.recover_days)  # fmt: skip
    for chunk in chunks:
        log.warning("run %s: %s recovering %s..%s before the window", run_id, config.name, chunk.start, chunk.end)
        older = _load_window(connector, region, chunk, f"{run_id}_{chunk.start:%Y%m%d}", warehouse)
        log.info("run summary: %s", older.as_dict())
    return sum(chunk.n_days for chunk in chunks)


def _load_window(
    connector: BaseConnector, region: Region, window: TimeWindow, run_id: str, warehouse: Warehouse
) -> RunSummary:
    """Extract, normalise and load one window as one run recorded in ``ops.ingestion_runs``."""
    name = connector.config.name
    settings = warehouse.settings
    warehouse.start_run(run_id, name, region.name, window)
    log.info("run %s: %s %s..%s (%s)", run_id, name, window.start, window.end, region.name)

    try:
        store = BronzeStore(settings)
        store.ensure()
        keys, normalized = _load_observations(connector, window, region, store)
        observations = normalized.observations
        if normalized.entities:
            named = warehouse.merge_entities(normalized.entities, run_id)
            log.info("run %s: %d of %d %s names new or changed", run_id, named, len(normalized.entities), name)
        if normalized.routes:
            changed = warehouse.replace_routes(name, normalized.routes, run_id)
            log.info("run %s: %d of %d %s routes new, changed or gone", run_id, changed, len(normalized.routes), name)
        if observations:
            ensure_bucket(store.client, settings.silver_bucket)
            rows_silver, upserted, results = _load_silver(connector, observations, window, run_id, warehouse)
            warehouse.record_quality(run_id, name, window, results)
        else:  # event source with no events in the window: raw response kept in bronze, nothing to load
            log.info("run %s: no %s events in %s..%s", run_id, name, window.start, window.end)
            rows_silver, upserted, results = 0, 0, []
    except Exception as exc:
        # A source that is down is `unavailable`, our own failure `failed`; the exception type stays in the error.
        status = "unavailable" if is_outage(exc) else "failed"
        warehouse.finish_run(run_id, name, status, error=f"{type(exc).__name__}: {exc}"[:2000])
        raise
    stats = RunStats(payloads=len(keys), rows_silver=rows_silver, rows_upserted=upserted)
    warehouse.finish_run(run_id, name, "success", stats=stats)
    return RunSummary.of(
        run_id, name, region.name, window, stats=stats, checks_failed=sum(1 for r in results if not r.passed)
    )
