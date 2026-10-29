"""Connection pool to the warehouse. The rest of the API only sees the ``Database`` protocol, so tests fake it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from api.settings import Settings

type Row = dict[str, Any]


class Database(Protocol):
    """Anything that runs a parametrised query and returns its rows as dicts."""

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> list[Row]:
        """Run ``sql`` with named ``%(param)s`` placeholders and return every row."""
        ...

    def ping(self) -> bool:
        """True when the warehouse answers."""
        ...


class PooledDatabase:
    """psycopg 3 connection pool. Every connection is read-only and has a statement timeout (see Settings)."""

    def __init__(self, settings: Settings) -> None:
        from psycopg.rows import dict_row  # noqa: PLC0415 - tests with a fake database never need psycopg
        from psycopg_pool import ConnectionPool  # noqa: PLC0415

        self.pool = ConnectionPool(
            settings.conninfo,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            kwargs={"row_factory": dict_row},
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
        with self.pool.connection() as conn:
            return conn.execute(sql, params or {}).fetchall()

    def ping(self) -> bool:
        """True when a connection answers ``SELECT 1`` within a few seconds."""
        try:
            with self.pool.connection(timeout=3) as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 - any failure means "not available" for the health check
            return False
        return True
