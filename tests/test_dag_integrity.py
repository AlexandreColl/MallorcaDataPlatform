"""DAG import, structure and lineage checks. Runs inside the Airflow image (`make test`); skipped elsewhere."""

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config import Settings

dagbag = pytest.importorskip("airflow.dag_processing.dagbag")

DAGS_DIR = Path(__file__).parent.parent / "dags"


def test_dags_import_without_errors():
    bag = dagbag.DagBag(dag_folder=DAGS_DIR)
    assert bag.import_errors == {}
    assert "mallorca_pipeline" in bag.dags  # get_dag() would query the metadata DB
    dag = bag.dags["mallorca_pipeline"]
    assert set(dag.params.keys()) == {"connectors", "days", "region", "catch_up"}
    assert {"resolve_connectors", "ingest", "detect_anomalies", "correct_values", "dbt_build"} <= set(dag.task_ids)
    # anomalies are scored, values corrected and gold rebuilt even when a source failed
    for task_id in ("detect_anomalies", "correct_values", "dbt_build"):
        assert dag.get_task(task_id).trigger_rule == "all_done"
    assert dag.get_task("detect_anomalies").downstream_task_ids == {"correct_values"}
    assert dag.get_task("correct_values").downstream_task_ids == {"dbt_build"}


def _uris(assets):
    return {a.uri for a in assets}


def test_tasks_declare_the_datasets_they_read_and_write():
    dag = dagbag.DagBag(dag_folder=DAGS_DIR).dags["mallorca_pipeline"]
    s = Settings.from_env()
    warehouse = f"postgres://{s.warehouse_host}:{s.warehouse_port}/{s.warehouse_db}/silver"

    assert _uris(dag.get_task("ingest").outlets) == {
        f"s3://{s.bronze_bucket}/",
        f"s3://{s.silver_bucket}/observations",
        f"{warehouse}/observations",
    }
    assert _uris(dag.get_task("detect_anomalies").inlets) == {f"{warehouse}/observations"}
    assert _uris(dag.get_task("detect_anomalies").outlets) == {f"{warehouse}/anomalies"}
    assert _uris(dag.get_task("correct_values").inlets) == {f"{warehouse}/observations", f"{warehouse}/anomalies"}
    assert _uris(dag.get_task("correct_values").outlets) == {f"{warehouse}/corrections"}


def test_dbt_sends_lineage_only_with_somewhere_to_send_it():
    dag = dagbag.DagBag(dag_folder=DAGS_DIR).dags["mallorca_pipeline"]
    task = dag.get_task("dbt_build")
    assert task.append_env
    spec = importlib.util.spec_from_file_location("mallorca_pipeline", DAGS_DIR / "mallorca_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert task.env == {"OPENLINEAGE_PARENT_ID": module.DBT_LINEAGE_PARENT}

    import jinja2  # noqa: PLC0415 - an Airflow dependency: this module is skipped without Airflow

    # The parent run comes from the provider's macro, which only exists while the provider is on.
    template = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=True).from_string(
        module.DBT_LINEAGE_PARENT
    )
    plugin = SimpleNamespace(lineage_parent_id=lambda ti: f"mallorca-data-platform/mallorca_pipeline.dbt_build/{ti}")
    on = template.render(macros=SimpleNamespace(OpenLineageProviderPlugin=plugin), task_instance="run-1")
    assert on == "mallorca-data-platform/mallorca_pipeline.dbt_build/run-1"
    assert template.render(macros=SimpleNamespace(), task_instance="run-1") == ""

    # The part that picks the dbt executable, run with and without OPENLINEAGE_URL.
    pick = module.DBT_COMMAND.split("PATH=/opt/dbt-venv/bin:$PATH ", 1)[1].split(" build ", 1)[0]
    for url, expected in (("", "/opt/dbt-venv/bin/dbt"), ("http://marquez:5000", "/opt/dbt-venv/bin/dbt-ol")):
        out = subprocess.run(  # noqa: S603 - a fixed command
            ["/bin/bash", "-c", f"echo {pick}"],
            env={"OPENLINEAGE_URL": url},
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == expected
