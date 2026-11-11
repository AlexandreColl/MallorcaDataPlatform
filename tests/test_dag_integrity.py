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
    assert set(dag.params.keys()) == {"connectors", "days", "region", "catch_up", "only_missing"}
    assert dag.params["only_missing"] is True  # a restart or a manual run only downloads what is missing
    assert dag.catchup is False  # after a restart only the latest interval runs; connectors recover their own days
    assert {"resolve_connectors", "ingest", "detect_anomalies", "correct_values", "dbt_build"} <= set(dag.task_ids)
    # anomalies are scored, values corrected and gold rebuilt even when a source failed
    for task_id in ("detect_anomalies", "correct_values", "dbt_build"):
        assert dag.get_task(task_id).trigger_rule == "all_done"
    assert dag.get_task("detect_anomalies").downstream_task_ids == {"correct_values"}
    assert dag.get_task("correct_values").downstream_task_ids == {"dbt_build"}


def _load_dag_module(monkeypatch, schedule):
    if schedule is None:
        monkeypatch.delenv("MDP_SCHEDULE", raising=False)
    else:
        monkeypatch.setenv("MDP_SCHEDULE", schedule)
    spec = importlib.util.spec_from_file_location("mallorca_pipeline_schedule", DAGS_DIR / "mallorca_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("schedule", "expected"), [(None, "@daily"), ("@hourly", "@hourly"), ("none", None), ("", None)]
)
def test_the_dag_runs_daily_unless_turned_off(monkeypatch, schedule, expected):
    module = _load_dag_module(monkeypatch, schedule)

    schedule = module.SCHEDULE
    assert schedule == expected


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


def test_a_source_that_is_down_is_skipped_and_our_failures_fail(monkeypatch):
    import requests  # noqa: PLC0415
    from airflow.sdk.exceptions import AirflowFailException, AirflowSkipException  # noqa: PLC0415

    import core.pipeline  # noqa: PLC0415
    from core.connectors import SourceNotUpdatedError  # noqa: PLC0415

    ingest = dagbag.DagBag(dag_folder=DAGS_DIR).dags["mallorca_pipeline"].get_task("ingest").python_callable
    attempt = {"try_number": 1, "max_tries": 3}  # the first of 1 + 3 retries
    monkeypatch.setitem(ingest.__globals__, "get_current_context", lambda: {"ti": SimpleNamespace(**attempt)})

    def run(error):
        def fail(*args, **kwargs):
            raise error

        monkeypatch.setattr(core.pipeline, "run_connector", fail)
        ingest("eea_air_quality", params={"days": 1, "region": "mallorca"}, run_id="r1")

    # Not published yet: skipped at once, since waiting minutes will not publish it.
    stale = SourceNotUpdatedError("EEA files end at 2026-10-30 11:00 UTC, before 2026-11-01: not updated yet")
    with pytest.raises(AirflowSkipException, match=r"eea_air_quality unavailable: SourceNotUpdatedError"):
        run(stale)

    # A moved URL is ours to fix, and retrying will not fix it: failed without retries.
    response = requests.Response()
    response.status_code = 404
    with pytest.raises(AirflowFailException, match=r"^HTTPError: 404"):
        run(requests.HTTPError("404 Client Error", response=response))

    # A source that is down keeps its retries...
    with pytest.raises(requests.ConnectionError):
        run(requests.ConnectionError("connection refused"))

    # ...and is skipped, not failed, when it is still down on the last one.
    attempt["try_number"] = 4
    with pytest.raises(AirflowSkipException, match=r"unavailable: ConnectionError"):
        run(requests.ConnectionError("connection refused"))
