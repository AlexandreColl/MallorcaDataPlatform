"""### Mallorca Data Platform.

Extracts open data for a region, lands it raw in **bronze** (MinIO), cleans it into the
common **silver** schema with quality checks (PySpark), upserts it into PostgreSQL and
builds the **gold** models with dbt.

Trigger with a config such as:

```json
{"connectors": ["open_meteo"], "days": 30, "region": "mallorca"}
```

* One mapped task per connector; a failing source does not stop the others, and dbt still
  builds gold with whatever loaded. Failed runs are visible in `ops.ingestion_runs` and Grafana.
* With `catch_up` (default) each connector extends its window back to the day after its last
  successful run, so the days lost while a source was down are recovered by the next run.
* Re-running the same window is idempotent (no duplicated rows).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

import pendulum
from airflow.sdk import Param, TriggerRule, dag, get_current_context, task

from core.config import available_regions
from core.connectors import registry

DBT = "/opt/dbt-venv/bin/dbt"
DBT_ARGS = "--profiles-dir . --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"
# Freshness only warns (a late source is visible in the logs and in gold.source_health) and never blocks the build.
DBT_COMMAND = (
    f"cd /opt/project/dbt && ({DBT} source freshness {DBT_ARGS} || true) && {DBT} build {DBT_ARGS}"
)


@dag(
    dag_id="mallorca_pipeline",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    doc_md=__doc__,
    tags=["mallorca", "bronze", "silver", "gold"],
    # Upstream APIs have short outages: retry with growing waits (2, 4, 8 min) before giving up on a source.
    default_args={
        "retries": int(os.environ.get("MDP_TASK_RETRIES", "3")),
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=10),
    },
    params={
        "connectors": Param(
            registry.runnable_names(),
            type="array",
            items={"type": "string", "enum": sorted(registry.discover())},
            description="Connectors to run. Default: every enabled connector whose API key is set.",
        ),
        "days": Param(1, type="integer", minimum=1, maximum=92, description="Days back"),
        "region": Param("mallorca", type="string", enum=available_regions()),
        "catch_up": Param(True, type="boolean", description="Recover days missed by failed runs"),
    },
)
def mallorca_pipeline() -> None:
    """Resolve connectors -> one mapped ingest task per connector -> dbt build."""

    @task
    def resolve_connectors(params: dict[str, Any] | None = None) -> list[str]:
        """Validate the requested connectors and their secrets before extracting anything."""
        params = params or {}
        requested = list(params.get("connectors") or []) or registry.runnable_names()
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
        summary = run_connector(
            connector,
            days=int(params["days"]),
            region_name=params["region"],
            run_id=run_id,
            catch_up=bool(params.get("catch_up", True)),
        )
        return summary.as_dict()

    @task.bash(trigger_rule=TriggerRule.ALL_DONE, retries=0)
    def dbt_build() -> str:
        """Build and test the gold models, also when some sources failed (gold keeps their previous data)."""
        return DBT_COMMAND

    ingest.expand(connector=resolve_connectors()) >> dbt_build()


mallorca_pipeline()
