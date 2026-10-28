import json
from datetime import date

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
        calls.append((name, days, kwargs["catch_up"], kwargs["window"]))
        return _Summary(kwargs["window"])

    monkeypatch.setattr(core.pipeline, "run_connector", fake_run)

    code = cli.main(["backfill", "--connectors", "aemet", "--start", "2024-01-01", "--end", "2025-12-31"])

    assert code == 0
    assert [c[3] for c in calls] == [
        TimeWindow(date(2024, 1, 1), date(2024, 12, 30)),  # 365 days per run
        TimeWindow(date(2024, 12, 31), date(2025, 12, 30)),
        TimeWindow(date(2025, 12, 31), date(2025, 12, 31)),
    ]
    assert {(c[0], c[2]) for c in calls} == {("aemet", False)}
    assert [c[1] for c in calls] == [365, 365, 1]
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert printed[0] == {"start": "2024-01-01", "end": "2024-12-30"}


def test_backfill_chunks_never_exceed_the_connector_max_days(monkeypatch):
    windows = []
    monkeypatch.setattr(
        core.pipeline, "run_connector", lambda name, days, **kw: windows.append(kw["window"]) or _Summary(kw["window"])
    )

    cli.main(
        ["backfill", "--connectors", "socib", "--start", "2026-01-01", "--end", "2026-03-31", "--chunk-days", "400"]
    )

    assert max(w.n_days for w in windows) == 61  # SOCIB allows 61 days per run
