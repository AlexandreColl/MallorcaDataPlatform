"""PostgreSQL warehouse access: DDL, idempotent upserts and audit tables."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql

from core.config import Settings
from core.models import TimeWindow
from core.quality.rules import RuleResult

DDL_PATH = Path(__file__).parent / "sql" / "warehouse.sql"

SILVER_COLUMNS = (
    "source",
    "entity",
    "metric",
    "ts",
    "value",
    "unit",
    "quality",
    "quality_reasons",
    "lat",
    "lon",
    "run_id",
    "ingested_at",
)
# Columns whose change counts as a real update (run_id / ingested_at always differ).
_COMPARED = ("value", "unit", "quality", "quality_reasons", "lat", "lon")


class Warehouse:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        s = self.settings
        with psycopg.connect(
            host=s.warehouse_host,
            port=s.warehouse_port,
            dbname=s.warehouse_db,
            user=s.warehouse_user,
            password=s.warehouse_password,
        ) as conn:
            yield conn

    def ensure_schema(self) -> None:
        # Advisory lock: several connector tasks may start at the same time.
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7302)")
            conn.execute(DDL_PATH.read_text(encoding="utf-8"))

    def merge_observations(self, landing_table: str) -> int:
        """Upsert a Spark-written landing table into silver.observations.

        Relaunching a window never duplicates rows (primary key) and rows whose
        content did not change are left untouched (IS DISTINCT FROM guard).
        Returns the number of inserted or changed rows.
        """
        cols = sql.SQL(", ").join(map(sql.Identifier, SILVER_COLUMNS))
        select_cols = sql.SQL(", ").join(
            sql.SQL("{c} AT TIME ZONE 'UTC'").format(c=sql.Identifier(c))
            if c in ("ts", "ingested_at")
            else sql.Identifier(c)
            for c in SILVER_COLUMNS
        )
        updates = sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c))
            for c in SILVER_COLUMNS
            if c not in ("source", "entity", "metric", "ts")
        )
        old = sql.SQL(", ").join(sql.SQL("t.{c}").format(c=sql.Identifier(c)) for c in _COMPARED)
        new = sql.SQL(", ").join(
            sql.SQL("EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in _COMPARED
        )
        query = sql.SQL(
            """
            INSERT INTO silver.observations AS t ({cols})
            SELECT {select_cols} FROM landing.{table}
            ON CONFLICT (source, entity, metric, ts) DO UPDATE
               SET {updates}, updated_at = now()
             WHERE ({old}) IS DISTINCT FROM ({new})
            """
        ).format(
            cols=cols,
            select_cols=select_cols,
            table=sql.Identifier(landing_table),
            updates=updates,
            old=old,
            new=new,
        )
        with self.connect() as conn:
            cur = conn.execute(query)
            return cur.rowcount

    def record_quality(
        self, run_id: str, source: str, window: TimeWindow, results: list[RuleResult]
    ) -> None:
        with self.connect() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO quality.check_results
                    (run_id, source, rule, target, checked, failed, passed, details,
                     window_start, window_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, source, rule, target) DO UPDATE
                   SET checked = EXCLUDED.checked, failed = EXCLUDED.failed,
                       passed = EXCLUDED.passed, details = EXCLUDED.details
                """,
                [
                    (
                        run_id,
                        source,
                        r.rule,
                        r.target,
                        r.checked,
                        r.failed,
                        r.passed,
                        r.details,
                        window.start,
                        window.end,
                    )
                    for r in results
                ],
            )

    def start_run(self, run_id: str, source: str, region: str, window: TimeWindow) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ops.ingestion_runs
                    (run_id, source, region, window_start, window_end, status)
                VALUES (%s, %s, %s, %s, %s, 'running')
                ON CONFLICT (run_id, source) DO UPDATE
                   SET status = 'running', started_at = now(), finished_at = NULL, error = NULL
                """,
                (run_id, source, region, window.start, window.end),
            )

    def finish_run(
        self,
        run_id: str,
        source: str,
        status: str,
        payloads: int | None = None,
        rows_silver: int | None = None,
        rows_upserted: int | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE ops.ingestion_runs
                   SET status = %s, payloads = %s, rows_silver = %s, rows_upserted = %s,
                       error = %s, finished_at = now()
                 WHERE run_id = %s AND source = %s
                """,
                (status, payloads, rows_silver, rows_upserted, error, run_id, source),
            )
