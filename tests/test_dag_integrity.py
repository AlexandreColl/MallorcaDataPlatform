"""DAG import check. Runs inside the Airflow image (`make test`); skipped elsewhere."""

from pathlib import Path

import pytest

dagbag = pytest.importorskip("airflow.dag_processing.dagbag")

DAGS_DIR = Path(__file__).parent.parent / "dags"


def test_dags_import_without_errors():
    bag = dagbag.DagBag(dag_folder=DAGS_DIR)
    assert bag.import_errors == {}
    assert "mallorca_pipeline" in bag.dags  # get_dag() would query the metadata DB
    dag = bag.dags["mallorca_pipeline"]
    assert set(dag.params.keys()) == {"connectors", "days", "region", "catch_up"}
    assert {"resolve_connectors", "ingest", "detect_anomalies", "dbt_build"} <= set(dag.task_ids)
    # anomalies are scored and gold is rebuilt even when a source failed
    assert dag.get_task("detect_anomalies").trigger_rule == "all_done"
    assert dag.get_task("dbt_build").trigger_rule == "all_done"
    assert dag.get_task("detect_anomalies").downstream_task_ids == {"dbt_build"}
