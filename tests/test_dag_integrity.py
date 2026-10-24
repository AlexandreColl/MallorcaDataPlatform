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
    assert set(dag.params.keys()) == {"connectors", "days", "region"}
    assert {"resolve_connectors", "ingest", "dbt_build"} <= set(dag.task_ids)
