import json
from datetime import date

import core.anomaly.evaluation
import core.anomaly.runner
import core.pipeline
from core import cli
from core.models import TimeWindow


class _Summary:
    def __init__(self, window: TimeWindow) -> None:
        self.window = window

    def as_dict(self) -> dict:
        return {"start": self.window.start.isoformat(), "end": self.window.end.isoformat()}


def test_backfill_runs_one_window_per_chunk_without_catch_up(monkeypatch, capsys):
    calls = []

    def fake_run(name, days, **kwargs):
        calls.append((name, days, kwargs["catch_up"], kwargs["window"], kwargs["run_id"]))
        return _Summary(kwargs["window"])

    monkeypatch.setattr(core.pipeline, "run_connector", fake_run)

    code = cli.main(
        ["backfill", "--connectors", "aemet", "--start", "2024-01-01", "--end", "2025-12-31", "--run-id", "hist"]
    )

    assert code == 0
    assert [c[3] for c in calls] == [
        TimeWindow(date(2024, 1, 1), date(2024, 12, 30)),  # 365 days per run
        TimeWindow(date(2024, 12, 31), date(2025, 12, 30)),
        TimeWindow(date(2025, 12, 31), date(2025, 12, 31)),
    ]
    assert {(c[0], c[2]) for c in calls} == {("aemet", False)}
    assert [c[1] for c in calls] == [365, 365, 1]
    # One run id per chunk: runs and quality results of a chunk do not overwrite the previous one.
    assert [c[4] for c in calls] == ["hist_20240101", "hist_20241231", "hist_20251231"]
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert printed[0] == {"start": "2024-01-01", "end": "2024-12-30"}


def test_list_shows_connectors_status_secrets_and_regions(capsys):
    assert cli.main(["list"]) == 0

    out = capsys.readouterr().out
    assert "goib_air_quality disabled" in out
    assert "secrets=['AEMET_API_KEY']" in out
    assert "regions: " in out
    assert "mallorca" in out


def test_run_reports_each_connector_and_fails_if_one_fails(monkeypatch, capsys):
    calls = []

    def fake_run(name, days, **kwargs):
        calls.append((name, days, kwargs["catch_up"], kwargs["run_id"]))
        if name == "ign":
            msg = "upstream down"
            raise RuntimeError(msg)
        return _Summary(TimeWindow(date(2026, 10, 1), date(2026, 10, 2)))

    monkeypatch.setattr(core.pipeline, "run_connector", fake_run)

    code = cli.main(["run", "--connectors", "open_meteo", "ign", "--days", "2", "--run-id", "r1", "--no-catch-up"])

    assert code == 1  # one connector failed, the other still ran
    assert calls == [("open_meteo", 2, False, "r1"), ("ign", 2, False, "r1")]
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_run_defaults_to_the_runnable_connectors(monkeypatch):
    names = []
    monkeypatch.setattr(cli.registry, "runnable_names", lambda: ["open_meteo", "redata"])
    monkeypatch.setattr(
        core.pipeline,
        "run_connector",
        lambda name, days, **kw: names.append(name) or _Summary(TimeWindow(date(2026, 10, 1), date(2026, 10, 1))),
    )

    assert cli.main(["run"]) == 0
    assert names == ["open_meteo", "redata"]


def test_backfill_counts_failed_chunks(monkeypatch):
    def fake_run(name, days, **kwargs):
        if kwargs["window"].start.year == 2025:
            msg = "chunk failed"
            raise RuntimeError(msg)
        return _Summary(kwargs["window"])

    monkeypatch.setattr(core.pipeline, "run_connector", fake_run)

    assert cli.main(["backfill", "--connectors", "aemet", "--start", "2024-06-01", "--end", "2025-06-30"]) == 1


def test_detect_and_evaluate_print_their_summaries(monkeypatch, capsys):
    seen = {}

    def fake_detect(days, sources, run_id):
        seen["detect"] = (days, sources, run_id)
        return _Summary(TimeWindow(date(2026, 10, 1), date(2026, 10, 30)))

    def fake_evaluate(run_id, days, seed):
        seen["evaluate"] = (run_id, days, seed)
        return [
            {
                "detector": "robust_zscore",
                "fault": "spike",
                "recall": 0.9,
                "events_detected": 9,
                "events": 10,
                "precision": 0.75,
                "false_alarms": 3,
            },
            {
                "detector": "robust_zscore",
                "fault": "drift",
                "recall": None,
                "events_detected": 0,
                "events": 0,
                "precision": None,
                "false_alarms": 0,
            },
        ]

    monkeypatch.setattr(core.anomaly.runner, "detect_anomalies", fake_detect)
    monkeypatch.setattr(core.anomaly.evaluation, "run_evaluation", fake_evaluate)

    assert cli.main(["detect", "--days", "30", "--sources", "aemet", "--run-id", "d1"]) == 0
    assert cli.main(["evaluate", "--days", "60", "--seed", "7", "--run-id", "e1"]) == 0

    assert seen == {"detect": (30, ["aemet"], "d1"), "evaluate": ("e1", 60, 7)}
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0]) == {"start": "2026-10-01", "end": "2026-10-30"}
    assert lines[1].split() == ["detector", "fault", "recall", "events", "precision", "false", "alarms"]
    assert lines[2].split() == ["robust_zscore", "spike", "90%", "9/10", "75%", "3"]
    assert lines[3].split() == ["robust_zscore", "drift", "0/0"]


def test_backfill_chunks_never_exceed_the_connector_max_days(monkeypatch):
    windows = []
    monkeypatch.setattr(
        core.pipeline, "run_connector", lambda name, days, **kw: windows.append(kw["window"]) or _Summary(kw["window"])
    )

    cli.main(
        ["backfill", "--connectors", "socib", "--start", "2026-01-01", "--end", "2026-03-31", "--chunk-days", "400"]
    )

    assert max(w.n_days for w in windows) == 61  # SOCIB allows 61 days per run
