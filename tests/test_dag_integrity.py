"""DAG import check. Runs inside the Airflow image (`make test`); skipped elsewhere."""

from pathlib import Path

import pytest

pytest.importorskip("airflow")

DAGS_DIR = Path(__file__).parent.parent / "dags"


def test_dags_import_without_errors():
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False)
    assert bag.import_errors == {}
    dag = bag.get_dag("mallorca_pipeline")
    assert dag is not None
    assert set(dag.params.keys()) == {"connectors", "days", "region"}
    assert {"resolve_connectors", "ingest", "dbt_build"} <= set(dag.task_ids)
