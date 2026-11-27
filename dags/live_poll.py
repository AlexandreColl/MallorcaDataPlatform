"""### Live poller.

Keeps the current state of the **live sources** (the ones without history, such as BiciPalma's GBFS feed) in
**bronze**, every few minutes. It is the only DAG that calls them: the daily `mallorca_pipeline` builds their hourly
series from these snapshots, never from the source (ADR 0026).

* Light on purpose: plain HTTP and S3 calls, no Spark and no warehouse. One task per live connector, without retries
  (the next poll is a few minutes away) and with a short timeout.
* Runs every `poll_every` of the fastest live dataset (5 minutes), or on the cron of `MDP_LIVE_SCHEDULE`; `none`
  turns it off (`make poll` still polls by hand).
* A source that is down skips its task: the missed snapshots show up as gaps in the hourly series.
* Each answer is stored untouched under the instant the source stamped on it, so polling an unchanged feed twice
  keeps one snapshot.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

import pendulum
from airflow.sdk import Asset, dag, task

from core.config import Settings
from core.live import live_names, poll_period

BRONZE = Asset(f"s3://{Settings.from_env().bronze_bucket}/")
LIVE = live_names()


def _schedule() -> str | None:
    """``MDP_LIVE_SCHEDULE`` (``none``: off), or by default a cron every ``poll_every`` of the fastest live dataset."""
    configured = os.environ.get("MDP_LIVE_SCHEDULE", "").strip()
    if configured:
        return None if configured.lower() == "none" else configured
    period = poll_period()
    if period is None:
        return None
    minutes = max(1, int(period.total_seconds() // 60))
    return f"*/{minutes} * * * *" if minutes < 60 else "@hourly"  # noqa: PLR2004 - a cron's minute field


@dag(
    dag_id="live_poll",
    schedule=_schedule(),
    start_date=pendulum.datetime(2026, 11, 26, tz="UTC"),
    catchup=False,  # a missed poll cannot be made up: the source only has its present
    max_active_runs=1,
    doc_md=__doc__,
    tags=["mallorca", "bronze", "live"],
    default_args={"retries": 0, "execution_timeout": timedelta(minutes=2)},
    dagrun_timeout=timedelta(minutes=4),
)
def live_poll() -> None:
    """One poll task per live connector."""

    @task(map_index_template="{{ connector_name }}", outlets=[BRONZE])
    def poll(connector: str) -> dict[str, Any]:
        """Keep the datasets of one live source that are due; skipped when the source is down."""
        from airflow.sdk import get_current_context
        from airflow.sdk.exceptions import AirflowSkipException

        from core.connectors import is_outage
        from core.live import poll_connector

        get_current_context()["connector_name"] = connector
        try:
            return poll_connector(connector).as_dict()
        except Exception as exc:
            if is_outage(exc):
                msg = f"{connector} unavailable: {type(exc).__name__}: {exc}"
                raise AirflowSkipException(msg) from exc
            raise

    poll.expand(connector=LIVE)


live_poll()
