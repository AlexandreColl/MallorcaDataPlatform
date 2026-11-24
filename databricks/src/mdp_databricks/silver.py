"""Silver: the bronze payloads not loaded yet, normalised by their own connector, quality-labelled and merged.

The same steps as the local pipeline (``core/pipeline.py``): ``normalize()`` of the connector, ``to_dataframe`` and
``apply_quality`` from ``core/silver.py``, then a ``MERGE`` on the key that leaves unchanged rows alone. What differs
is where the state lives: Unity Catalog coordinates the commits of a managed table, so the Postgres lock of the local
Delta table is not needed, and ``loaded_payloads`` plays the part of ``ops.ingestion_runs``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyspark.sql import functions as F

from core.connectors import registry
from core.models import COMPARED, KEY, RawPayload, TimeWindow
from core.silver import apply_quality, to_dataframe

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, Row, SparkSession

    from core.models import Observation, Region
    from core.quality import RuleResult
    from mdp_databricks.catalog import Names

log = logging.getLogger(__name__)

_UPDATES_VIEW = "silver_updates"


@dataclass(frozen=True)
class SourceLoad:
    """What one source added to silver in a run."""

    source: str
    payloads: int
    observations: int
    inserted: int
    updated: int


def pending_payloads(spark: SparkSession, names: Names) -> list[Row]:
    """Bronze rows that no silver load has taken yet, oldest first."""
    return spark.sql(
        f"""
        SELECT b.source, b.file_path, b.fetched_at, b.payload
        FROM {names.bronze} AS b
        LEFT ANTI JOIN {names.loaded} AS l ON b.file_path = l.file_path AND b.fetched_at = l.fetched_at
        ORDER BY b.fetched_at
        """  # noqa: S608 - table names from Names, a checked identifier
    ).collect()


def merge_statement(table: str, view: str = _UPDATES_VIEW) -> str:
    """``MERGE`` of a view of silver rows on the key, skipping the rows already in the table with the same content.

    Delta rewrites every file holding a matched row, so a rerun of a window that changed nothing writes nothing.
    """
    on = " AND ".join(f"t.{c} = s.{c}" for c in KEY)
    same = " AND ".join([*(f"u.{c} = cur.{c}" for c in KEY), *(f"u.{c} <=> cur.{c}" for c in COMPARED)])
    return f"""
        MERGE INTO {table} AS t
        USING (SELECT u.* FROM {view} AS u LEFT ANTI JOIN {table} AS cur ON {same}) AS s
        ON {on}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """  # noqa: S608 - table and column names are constants or a checked identifier


def merge(spark: SparkSession, rows: DataFrame, names: Names) -> tuple[int, int]:
    """Upsert silver rows. Returns (inserted, updated)."""
    rows.createOrReplaceTempView(_UPDATES_VIEW)
    result = spark.sql(merge_statement(names.silver)).first()
    if result is None:
        return 0, 0
    return int(result["num_inserted_rows"]), int(result["num_updated_rows"])


def newest_per_key(per_payload: list[list[Observation]]) -> list[list[Observation]]:
    """Each payload's observations without the keys that a payload fetched later also gives.

    ``per_payload`` is in fetch order, oldest first. Payloads pile up in bronze when a run stops before silver, and
    the windows of consecutive days overlap: the latest fetch of a key wins, as the latest version of an object does
    in MinIO, and the duplicate rule still catches a key repeated inside one payload.
    """
    seen: set[tuple[object, ...]] = set()
    kept: list[list[Observation]] = []
    for batch in reversed(per_payload):
        keys = [tuple(getattr(o, c) for c in KEY) for o in batch]
        kept.append([o for o, k in zip(batch, keys, strict=True) if k not in seen])
        seen.update(keys)
    return kept[::-1]


def _window(payloads: list[RawPayload]) -> TimeWindow:
    """The days the payloads of one source cover, for the gaps rule."""
    return TimeWindow(min(p.window.start for p in payloads), max(p.window.end for p in payloads))


def _record(  # noqa: PLR0913 - the context of one source load, keyword-only
    spark: SparkSession,
    names: Names,
    *,
    source: str,
    rows: list[Row],
    counts: list[int],
    results: list[RuleResult],
    run_id: str,
) -> None:
    """Mark the payloads as loaded and keep the rule results."""
    loaded = spark.createDataFrame(
        [(r["file_path"], r["fetched_at"], source, n, run_id) for r, n in zip(rows, counts, strict=True)],
        "file_path STRING, fetched_at TIMESTAMP, source STRING, observations BIGINT, run_id STRING",
    ).withColumn("loaded_at", F.current_timestamp())
    loaded.write.mode("append").saveAsTable(names.loaded)
    if results:
        checks = spark.createDataFrame(
            [(run_id, source, r.rule, r.target, r.checked, r.failed, r.details) for r in results],
            "run_id STRING, source STRING, rule STRING, target STRING, checked BIGINT, failed BIGINT, details STRING",
        ).withColumn("checked_at", F.current_timestamp())
        checks.write.mode("append").saveAsTable(names.checks)


def load_source(  # noqa: PLR0913 - the context of one source load, keyword-only after the rows
    spark: SparkSession, names: Names, source: str, rows: list[Row], *, region: Region, run_id: str
) -> SourceLoad:
    """Normalise, label and merge the pending payloads of one source, then mark them as loaded."""
    connector = registry.load(source, secrets={})
    payloads = [RawPayload.from_json(r["payload"]) for r in rows]
    per_payload = newest_per_key([list(connector.normalize(p, region)) for p in payloads])
    observations = [o for batch in per_payload for o in batch]
    inserted = updated = 0
    results: list[RuleResult] = []
    if observations:
        silver, results = apply_quality(to_dataframe(spark, observations, run_id), connector, _window(payloads))
        inserted, updated = merge(spark, silver, names)
    _record(
        spark, names, source=source, rows=rows, counts=[len(b) for b in per_payload], results=results, run_id=run_id
    )
    load = SourceLoad(source, len(rows), len(observations), inserted, updated)
    log.info("silver: %s", load)
    return load


def load_silver(spark: SparkSession, names: Names, *, region: Region, run_id: str) -> list[SourceLoad]:
    """Load every pending payload, source by source. A failing source does not stop the others.

    Raises:
        RuntimeError: after the other sources are loaded, if any source failed.
    """
    by_source: dict[str, list[Row]] = defaultdict(list)
    for row in pending_payloads(spark, names):
        by_source[row["source"]].append(row)
    loads: list[SourceLoad] = []
    failed: list[str] = []
    for source, rows in sorted(by_source.items()):
        try:
            loads.append(load_source(spark, names, source, rows, region=region, run_id=run_id))
        except Exception:
            log.exception("silver: %s failed; its payloads stay pending for the next run", source)
            failed.append(source)
    if failed:
        msg = f"silver failed for {failed}"
        raise RuntimeError(msg)
    if not by_source:
        log.info("silver: no pending payloads in %s", names.bronze)
    return loads
