"""Connection pool to the warehouse. The rest of the API only sees the ``Database`` protocol, so tests fake it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from api.settings import Settings

type Row = dict[str, Any]
STREAM_BATCH = 10_000  # rows per round trip of an export


class Database(Protocol):
    """Anything that runs a parametrised query and returns its rows as dicts."""

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[Row]:
        """Run ``sql`` with named ``%(param)s`` placeholders and return every row."""
        ...

    def stream(self, sql: str, params: Mapping[str, Any] | None = None) -> Iterator[Row]:
        """Run ``sql`` and yield its rows one at a time, without holding them all in memory."""
        ...

    def ping(self) -> bool:
        """True when the warehouse answers."""
        ...


class PooledDatabase:
    """psycopg 3 connection pool. Every connection is read-only and has a statement timeout (see Settings)."""

    def __init__(self, settings: Settings) -> None:
        from psycopg_pool import ConnectionPool  # noqa: PLC0415 - tests with a fake database never need psycopg

        self.pool = ConnectionPool(
            settings.conninfo,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            open=False,
        )

    def open(self) -> None:
        """Open the pool without waiting for the warehouse: /health reports it while it is down."""
        self.pool.open(wait=False)

    def close(self) -> None:
        """Close every connection."""
        self.pool.close()

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[Row]:
        """Run ``sql`` on a pooled connection and return every row as a dict."""
        from psycopg.rows import dict_row  # noqa: PLC0415

        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params or {}).fetchall()

    def stream(self, sql: str, params: Mapping[str, Any] | None = None) -> Iterator[Row]:
        """Rows from a server-side cursor, fetched ``STREAM_BATCH`` at a time, on a connection held while they flow."""
        from psycopg.rows import dict_row  # noqa: PLC0415

        with self.pool.connection() as conn, conn.cursor(name="export", row_factory=dict_row) as cur:
            cur.itersize = STREAM_BATCH
            cur.execute(sql, params or {})
            yield from cur

    def ping(self) -> bool:
        """True when a connection answers ``SELECT 1`` within a few seconds."""
        try:
            with self.pool.connection(timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 - any failure means "not available" for the health check
            return False
        return True
