"""Unity Catalog layout: one catalog, a schema per layer, two volumes, the tables and the read grants on gold.

Every statement is idempotent (``IF NOT EXISTS``, ``GRANT``), so the setup task runs at the start of every job run.
Locally the same layers are a MinIO bucket (bronze), a Delta table in MinIO plus Postgres (silver) and Postgres
(gold); here they are all Unity Catalog objects with their permissions in SQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class Names:
    """Where each layer lives inside one catalog."""

    catalog: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.catalog):
            msg = f"catalog '{self.catalog}' must be a lowercase identifier ([a-z][a-z0-9_]*)"
            raise ValueError(msg)

    @property
    def raw_volume(self) -> str:
        """Volume path where the extract tasks land the raw payloads (the local bronze bucket)."""
        return f"/Volumes/{self.catalog}/bronze/raw"

    @property
    def checkpoint(self) -> str:
        """Auto Loader checkpoint: which files of the raw volume are already in the bronze table."""
        return f"/Volumes/{self.catalog}/bronze/checkpoints/payloads"

    @property
    def bronze(self) -> str:
        """Append-only table with one row per raw payload file Auto Loader picked up."""
        return f"{self.catalog}.bronze.payloads"

    @property
    def silver(self) -> str:
        """Observations in the common schema, one row per key (the local ``s3://silver/observations``)."""
        return f"{self.catalog}.silver.observations"

    @property
    def loaded(self) -> str:
        """The bronze payloads already normalised into silver, with their row count (like ``ops.ingestion_runs``)."""
        return f"{self.catalog}.silver.loaded_payloads"

    @property
    def checks(self) -> str:
        """The result of every quality rule on every load (like ``quality.check_results``)."""
        return f"{self.catalog}.silver.check_results"

    def gold(self, table: str) -> str:
        """A table of the gold schema."""
        return f"{self.catalog}.gold.{table}"


def setup_statements(names: Names, readers: str) -> list[str]:
    """The DDL and grants of the whole layout, in order. ``readers`` gets read access to gold only."""
    if "`" in readers or not readers.strip():
        msg = f"invalid principal for the read grants: {readers!r}"
        raise ValueError(msg)
    c = names.catalog
    return [
        f"CREATE CATALOG IF NOT EXISTS {c} COMMENT 'Mallorca Data Platform: open data of Mallorca, bronze to gold'",
        f"CREATE SCHEMA IF NOT EXISTS {c}.bronze COMMENT 'Raw API responses, untouched'",
        f"CREATE SCHEMA IF NOT EXISTS {c}.silver COMMENT 'Observations in the common schema, quality-labelled'",
        f"CREATE SCHEMA IF NOT EXISTS {c}.gold COMMENT 'Daily tables ready for analysis'",
        f"CREATE VOLUME IF NOT EXISTS {c}.bronze.raw COMMENT 'payload.json files under the same keys as in MinIO'",
        f"CREATE VOLUME IF NOT EXISTS {c}.bronze.checkpoints COMMENT 'Auto Loader checkpoints'",
        f"""CREATE TABLE IF NOT EXISTS {names.bronze} (
            source STRING NOT NULL,
            dataset STRING NOT NULL,
            window_start DATE NOT NULL,
            window_end DATE NOT NULL,
            payload_partition STRING,
            fetched_at TIMESTAMP NOT NULL,
            payload STRING NOT NULL COMMENT 'The whole payload.json: request metadata and the untouched body',
            file_path STRING NOT NULL,
            file_modified_at TIMESTAMP,
            ingested_at TIMESTAMP NOT NULL
        ) CLUSTER BY (source) COMMENT 'One row per raw payload file, append-only: re-fetched windows add a row'""",
        f"""CREATE TABLE IF NOT EXISTS {names.silver} (
            source STRING NOT NULL,
            entity STRING NOT NULL,
            metric STRING NOT NULL,
            ts TIMESTAMP NOT NULL,
            value DOUBLE,
            unit STRING NOT NULL,
            quality STRING NOT NULL,
            lat DOUBLE,
            lon DOUBLE,
            run_id STRING NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            quality_reasons STRING
        ) CLUSTER BY (source, ts)
        COMMENT 'One value per source, entity, metric and hour (UTC); quality flags never change the value'
        TBLPROPERTIES (delta.enableChangeDataFeed = true)""",
        f"""CREATE TABLE IF NOT EXISTS {names.loaded} (
            file_path STRING NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            source STRING NOT NULL,
            observations BIGINT NOT NULL,
            run_id STRING NOT NULL,
            loaded_at TIMESTAMP NOT NULL
        ) COMMENT 'Bronze payloads already in silver: the next silver task skips them'""",
        f"""CREATE TABLE IF NOT EXISTS {names.checks} (
            run_id STRING NOT NULL,
            source STRING NOT NULL,
            rule STRING NOT NULL,
            target STRING NOT NULL,
            checked BIGINT NOT NULL,
            failed BIGINT NOT NULL,
            details STRING,
            checked_at TIMESTAMP NOT NULL
        ) COMMENT 'Quality rule results of every silver load'""",
        f"GRANT USE CATALOG ON CATALOG {c} TO `{readers}`",
        f"GRANT USE SCHEMA, SELECT ON SCHEMA {c}.gold TO `{readers}`",
    ]


def setup(spark: SparkSession, names: Names, readers: str) -> None:
    """Create whatever is missing and (re)apply the grants."""
    for statement in setup_statements(names, readers):
        spark.sql(statement)
