"""The statuses of a connector run are written in several places: they all list the same ones as core.warehouse.

Adding one (as `unavailable` was, ADR 0022) means changing the CHECK of the table, the dbt test, the API model, the
health mart, the Grafana colours and the SLA alert. A place left behind fails here instead of in production.
"""

import json
import re
from pathlib import Path
from typing import get_args

import yaml

from api.schemas import RunStatus as ApiRunStatus
from core.warehouse import RUN_STATUSES

ROOT = Path(__file__).parent.parent
# The statuses of a finished run, and those of a run that did not load.
FINISHED = set(RUN_STATUSES) - {"running"}
NOT_LOADED = FINISHED - {"success"}


def test_the_table_accepts_exactly_these_statuses():
    ddl = (ROOT / "core" / "sql" / "warehouse.sql").read_text(encoding="utf-8")
    checks = re.findall(r"CHECK \(status IN \(([^)]*)\)\)", ddl)
    assert len(checks) == 2  # the CREATE TABLE and the migration of existing warehouses
    for check in checks:
        assert re.findall(r"'(\w+)'", check) == list(RUN_STATUSES)


def test_dbt_accepts_exactly_these_statuses():
    staging = yaml.safe_load((ROOT / "dbt" / "models" / "staging" / "_staging.yml").read_text(encoding="utf-8"))
    model = next(m for m in staging["models"] if m["name"] == "stg_ops__ingestion_runs")
    column = next(c for c in model["columns"] if c["name"] == "status")
    (values,) = [t["accepted_values"]["arguments"]["values"] for t in column["data_tests"] if "accepted_values" in t]
    assert values == list(RUN_STATUSES)


def test_the_api_serves_exactly_these_statuses():
    assert get_args(ApiRunStatus) == RUN_STATUSES


def test_source_health_counts_each_way_a_run_did_not_load():
    mart = (ROOT / "dbt" / "models" / "marts" / "quality" / "source_health.sql").read_text(encoding="utf-8")
    for status in NOT_LOADED:
        assert f"status = '{status}'" in mart
        assert f"{status}_7d" in mart


def test_the_sla_alert_counts_every_run_that_did_not_load():
    alerting = (ROOT / "dashboards" / "provisioning" / "alerting" / "alerting.yml").read_text(encoding="utf-8")
    (listed,) = re.findall(r"status IN \(([^)]*)\)", alerting)
    assert set(re.findall(r"'(\w+)'", listed)) == NOT_LOADED


def _status_mappings(node):
    """Every Grafana value mapping that colours run statuses (the ones with a `failed` entry)."""
    if isinstance(node, dict):
        if node.get("type") == "value" and "failed" in node.get("options", {}):
            yield node["options"]
        for value in node.values():
            yield from _status_mappings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _status_mappings(value)


def test_grafana_colours_every_finished_status():
    dashboards = sorted((ROOT / "dashboards" / "json").glob("*.json"))
    mappings = [m for d in dashboards for m in _status_mappings(json.loads(d.read_text(encoding="utf-8")))]
    assert mappings  # the Operación dashboard colours the last status and the run history
    for options in mappings:
        assert FINISHED <= set(options) <= set(RUN_STATUSES)  # the history also colours the runs still going


def test_the_web_knows_every_status_that_did_not_load():
    sources = (ROOT / "web" / "src" / "lib" / "sources.ts").read_text(encoding="utf-8")
    for status in NOT_LOADED:
        assert f'"{status}"' in sources
