"""### Mallorca Data Platform.

Extracts open data for a region, lands it raw in **bronze** (MinIO), cleans it into the
common **silver** schema with quality checks (PySpark), upserts it into PostgreSQL and
builds the **gold** models with dbt.

Trigger with a config such as:

```json
{"connectors": ["open_meteo"], "days": 30, "region": "mallorca"}
```

* One mapped task per connector; a failing source does not stop the others, and dbt still
  builds gold with whatever loaded. Runs are visible in `ops.ingestion_runs` and Grafana: `failed` is our side,
  `unavailable` a source that was down (its task is skipped after the retries, and the run stays green).
* It runs every day by itself (`MDP_SCHEDULE`, default `@daily`, without catch-up): after the computer was off, the
  scheduler starts the pending run as soon as Airflow is back, once.
* With `only_missing` (default) a connector does not download again the days a successful run already loaded: it
  starts at its first missing day, or is skipped without calling its source. Sources that re-read on purpose to pick
  up revisions keep their window, once a day.
* With `catch_up` (default) each connector extends its window back to the day after its last
  successful run, so the days lost while a source was down are recovered by the next run.
* Re-running the same window is idempotent (no duplicated rows).
* After ingestion the anomaly detectors score the recent values and flag outliers in
  `silver.anomalies` (they never change the data), also when some sources failed.
* Then the station series get corrections for their gaps and suspect values in `silver.corrections`
  (interpolation, or a nearby support source with a calibrated bias); gold shows both values.
* Every task declares the datasets it reads and writes (Airflow assets). With `OPENLINEAGE_URL` set, the
  OpenLineage provider sends them with each run, and dbt runs as `dbt-ol`, which adds one job per model with its
  inputs and columns, under this task.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

import pendulum
from airflow.sdk import Asset, Param, TriggerRule, dag, get_current_context, task

from core.config import Settings, available_regions
from core.connectors import registry

DBT = "/opt/dbt-venv/bin/dbt"
# dbt with OpenLineage events, used when they have somewhere to go.
DBT_OL = "/opt/dbt-venv/bin/dbt-ol"
DBT_ARGS = "--profiles-dir . --target-path /tmp/dbt/target --log-path /tmp/dbt/logs"
# Freshness only warns (a late source is visible in the logs and in gold.source_health) and never blocks the build.
DBT_COMMAND = (
    f"cd /opt/project/dbt && ({DBT} source freshness {DBT_ARGS} || true)"
    # dbt-ol runs the `dbt` on the PATH: the venv's.
    f' && PATH=/opt/dbt-venv/bin:$PATH $( [ -n "$OPENLINEAGE_URL" ] && echo {DBT_OL} || echo {DBT} ) build {DBT_ARGS}'
)
# dbt-ol attaches its model jobs to the Airflow task run that started it. Without OPENLINEAGE_URL the provider turns
# its plugin off, and with it the macro: then there is no parent (and dbt-ol is not used).
DBT_LINEAGE_PARENT = (
    "{{ macros.OpenLineageProviderPlugin.lineage_parent_id(task_instance)"
    " if macros.OpenLineageProviderPlugin is defined else '' }}"
)


def _assets(settings: Settings) -> dict[str, Asset]:
    """The datasets the tasks read and write, named like their OpenLineage datasets (and dbt-ol's sources)."""
    warehouse = f"postgres://{settings.warehouse_host}:{settings.warehouse_port}/{settings.warehouse_db}"
    return {
        "bronze": Asset(f"s3://{settings.bronze_bucket}/"),  # every raw response, keyed by connector
        "silver_lake": Asset(f"s3://{settings.silver_bucket}/observations"),
        **{table: Asset(f"{warehouse}/silver/{table}") for table in ("observations", "anomalies", "corrections")},
    }


ASSETS = _assets(Settings.from_env())
# Daily by default, so the data is kept up to date and a restart picks up where it left off. Empty or `none`: only
# manual runs (the E2E test, which triggers its own runs).
SCHEDULE = os.environ.get("MDP_SCHEDULE", "@daily").strip() or None
if SCHEDULE and SCHEDULE.lower() == "none":
    SCHEDULE = None


@dag(
    dag_id="mallorca_pipeline",
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    # Only the latest missed interval runs after a restart: each connector recovers its own missed days.
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
        "only_missing": Param(
            True, type="boolean", description="Skip the days already loaded (false: download the whole window again)"
        ),
    },
)
def mallorca_pipeline() -> None:
    """Resolve connectors -> one mapped ingest task per connector -> anomaly detection -> corrections -> dbt build."""

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

    @task(
        map_index_template="{{ connector_name }}",
        max_active_tis_per_dagrun=2,
        outlets=[ASSETS["bronze"], ASSETS["silver_lake"], ASSETS["observations"]],
    )
    def ingest(connector: str, params: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        """Run one connector end to end (bronze -> silver -> warehouse).

        A source that is down keeps its retries, and if it is still down after them (or has not published the
        window yet) the task is skipped, not failed: the run stays green and `ops.ingestion_runs` says
        `unavailable`. A failure on our side that waiting will not fix (an HTTP 4xx such as a moved URL) fails
        without retries. Either way the next run recovers the days (catch-up).
        """
        from airflow.sdk.exceptions import AirflowFailException, AirflowSkipException

        from core.connectors import failure_action
        from core.pipeline import run_connector

        params = params or {}
        context = get_current_context()
        context["connector_name"] = connector
        ti = context["ti"]
        try:
            summary = run_connector(
                connector,
                days=int(params["days"]),
                region_name=params["region"],
                run_id=run_id,
                catch_up=bool(params.get("catch_up", True)),
                only_missing=bool(params.get("only_missing", True)),
            )
        except Exception as exc:
            action = failure_action(exc, retries_left=ti.try_number <= ti.max_tries)
            msg = f"{type(exc).__name__}: {exc}"
            if action == "skip":
                raise AirflowSkipException(f"{connector} unavailable: {msg}") from exc
            if action == "fail":
                raise AirflowFailException(msg) from exc
            raise
        return summary.as_dict()

    @task(trigger_rule=TriggerRule.ALL_DONE, retries=0, inlets=[ASSETS["observations"]], outlets=[ASSETS["anomalies"]])
    def detect_anomalies(
        connectors: list[str], params: dict[str, Any] | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        """Score the recent silver values of these sources and replace what the detectors flagged."""
        from core.anomaly.runner import detect_anomalies as run_detection

        params = params or {}
        return run_detection(int(params["days"]), sources=connectors, run_id=run_id or "manual").as_dict()

    @task(
        trigger_rule=TriggerRule.ALL_DONE,
        retries=0,
        inlets=[ASSETS["observations"], ASSETS["anomalies"]],
        outlets=[ASSETS["corrections"]],
    )
    def correct_values(
        connectors: list[str], params: dict[str, Any] | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        """Recompute the corrections of the recent station values of these sources (silver.corrections)."""
        from core.corrections.runner import correct_values as run_corrections

        params = params or {}
        return run_corrections(int(params["days"]), sources=connectors, run_id=run_id or "manual").as_dict()

    @task.bash(
        trigger_rule=TriggerRule.ALL_DONE,
        retries=0,
        env={"OPENLINEAGE_PARENT_ID": DBT_LINEAGE_PARENT},
        append_env=True,
    )
    def dbt_build() -> str:
        """Build and test the gold models, also when some sources failed (gold keeps their previous data)."""
        return DBT_COMMAND

    connectors = resolve_connectors()
    ingest.expand(connector=connectors) >> detect_anomalies(connectors) >> correct_values(connectors) >> dbt_build()


mallorca_pipeline()
