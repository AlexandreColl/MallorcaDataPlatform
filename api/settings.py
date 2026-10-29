"""API settings, read from the environment (the same variables as the rest of the platform)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class Settings:
    """Connection to the warehouse as the read-only API role, plus paging and CORS limits."""

    host: str = "localhost"
    port: int = 5432
    database: str = "warehouse"
    user: str = "api_reader"
    password: str = "api_reader"  # noqa: S105 - local default, overridden by API_DB_PASSWORD
    pool_min_size: int = 1
    pool_max_size: int = 5
    max_page_size: int = 1000
    cors_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Settings from ``WAREHOUSE_HOST``/``PORT``/``DB`` and the ``API_*`` variables."""
        env = os.environ if env is None else env
        return cls(
            host=env.get("WAREHOUSE_HOST", cls.host),
            port=int(env.get("WAREHOUSE_PORT", cls.port)),
            database=env.get("WAREHOUSE_DB", cls.database),
            user=env.get("API_DB_USER", cls.user),
            password=env.get("API_DB_PASSWORD", cls.password),
            pool_min_size=int(env.get("API_POOL_MIN_SIZE", cls.pool_min_size)),
            pool_max_size=int(env.get("API_POOL_MAX_SIZE", cls.pool_max_size)),
            max_page_size=int(env.get("API_MAX_PAGE_SIZE", cls.max_page_size)),
            cors_origins=tuple(o.strip() for o in env.get("API_CORS_ORIGINS", "*").split(",") if o.strip()),
        )

    @property
    def conninfo(self) -> str:
        """libpq connection string (read-only transactions, short statement timeout)."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password} "
            "application_name=mallorca-api options='-c default_transaction_read_only=on -c statement_timeout=15000'"
        )
