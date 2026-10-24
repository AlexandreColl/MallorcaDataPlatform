"""### Mallorca Data Platform.

Extracts open data for a region, lands it raw in **bronze** (MinIO), cleans it into the
common **silver** schema with quality checks (PySpark), upserts it into PostgreSQL and
builds the **gold** models with dbt.

Trigger with a config such as:

```json
{"connectors": ["open_meteo"], "days": 30, "region": "mallorca"}
```

* One mapped task per connector; a failing source does not stop the others.
* Re-running the same window is idempotent (no duplicated rows).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pendulum
from airflow.sdk import Param, dag, get_current_context, task

from core.config import available_regions
from core.connectors import registry

DBT_COMMAND = (
    "cd /opt/project/dbt && /opt/dbt-venv/bin/dbt build --profiles-dir . "
    "--target-path /tmp/dbt/target --log-path /tmp/dbt/logs"
)


@dag(
    dag_id="mallorca_pipeline",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    doc_md=__doc__,
    tags=["mallorca", "bronze", "silver", "gold"],
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    params={
        "connectors": Param(
            registry.enabled_names(),
            type="array",
            items={"type": "string", "enum": sorted(registry.discover())},
            description="Connectors to run. Default: every enabled connector.",
        ),
        "days": Param(1, type="integer", minimum=1, maximum=92, description="Days back"),
        "region": Param("mallorca", type="string", enum=available_regions()),
    },
)
def mallorca_pipeline() -> None:
    """Resolve connectors -> one mapped ingest task per connector -> dbt build."""

    @task
    def resolve_connectors(params: dict[str, Any] | None = None) -> list[str]:
        """Validate the requested connectors and their secrets before extracting anything."""
        params = params or {}
        requested = list(params.get("connectors") or []) or registry.enabled_names()
        known = registry.discover()
        unknown = sorted(set(requested) - set(known))
        if unknown:
            msg = f"unknown connectors {unknown}; available {sorted(known)}"
            raise ValueError(msg)
        # Fail fast on missing secrets before any extraction starts.
        for name in requested:
            registry.load(name)
        return requested

    @task(map_index_template="{{ connector_name }}", max_active_tis_per_dagrun=2)
    def ingest(connector: str, params: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        """Run one connector end to end (bronze -> silver -> warehouse)."""
        from core.pipeline import run_connector

        params = params or {}
        get_current_context()["connector_name"] = connector
        summary = run_connector(connector, days=int(params["days"]), region_name=params["region"], run_id=run_id)
        return summary.as_dict()

    @task.bash
    def dbt_build() -> str:
        """Build and test the gold models."""
        return DBT_COMMAND

    ingest.expand(connector=resolve_connectors()) >> dbt_build()


mallorca_pipeline()
