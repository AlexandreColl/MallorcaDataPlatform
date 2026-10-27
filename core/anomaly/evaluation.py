"""Benchmark the detectors against injected faults: precision, and recall per fault kind.

Each series is scored twice: clean, to know what the detector already flags (real events, which cannot be
judged right or wrong), and corrupted by the `FaultInjector`. Flags on injected values are true positives;
new flags on clean values are false alarms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from core.anomaly.faults import FaultInjector, FaultSpec
from core.anomaly.runner import SERIES_KEYS, AnomalyConfig
from core.config import Settings
from core.models import Quality, TimeWindow
from core.warehouse import Warehouse

if TYPE_CHECKING:
    from core.anomaly.base import Detector

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationConfig:
    """The ``evaluation`` block of ``config/anomaly.yaml``."""

    source: str
    days: int
    seed: int
    faults: dict[str, FaultSpec]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationConfig:
        """Build from the parsed YAML block."""
        return cls(
            source=data["source"],
            days=int(data["days"]),
            seed=int(data["seed"]),
            faults={kind: FaultSpec.from_dict(spec) for kind, spec in data["faults"].items()},
        )


@dataclass
class FaultRecall:
    """How much of one fault kind a detector caught: by value and by fault (any value of it flagged)."""

    events: int = 0
    events_detected: int = 0
    points: int = 0
    points_detected: int = 0

    @property
    def recall(self) -> float | None:
        """Share of the injected values that were flagged."""
        return self.points_detected / self.points if self.points else None

    @property
    def event_recall(self) -> float | None:
        """Share of the injected faults with at least one flagged value."""
        return self.events_detected / self.events if self.events else None


@dataclass
class Evaluation:
    """Result of one detector over every series of the benchmark."""

    detector: str
    series: int = 0
    values: int = 0
    true_positives: int = 0
    false_alarms: int = 0
    baseline_flags: int = 0
    by_fault: dict[str, FaultRecall] = field(default_factory=dict)

    @property
    def precision(self) -> float | None:
        """Share of the new flags that hit an injected value (real events flagged on clean data excluded)."""
        flags = self.true_positives + self.false_alarms
        return self.true_positives / flags if flags else None

    @property
    def total(self) -> FaultRecall:
        """Recall over every fault kind together."""
        return FaultRecall(
            events=sum(f.events for f in self.by_fault.values()),
            events_detected=sum(f.events_detected for f in self.by_fault.values()),
            points=sum(f.points for f in self.by_fault.values()),
            points_detected=sum(f.points_detected for f in self.by_fault.values()),
        )

    def add_series(self, flagged: np.ndarray, baseline: np.ndarray, corrupted: pd.DataFrame) -> None:
        """Accumulate the counts of one series."""
        injected = corrupted["fault"].notna().to_numpy()
        self.series += 1
        self.values += len(corrupted)
        self.true_positives += int((flagged & injected).sum())
        self.false_alarms += int((flagged & ~injected & ~baseline).sum())
        self.baseline_flags += int(baseline.sum())
        for kind, rows in corrupted[injected].groupby("fault"):
            hits = flagged[rows.index]
            recall = self.by_fault.setdefault(kind, FaultRecall())
            recall.points += len(rows)
            recall.points_detected += int(hits.sum())
            per_event = pd.Series(hits, index=rows["event"]).groupby(level=0).any()
            recall.events += len(per_event)
            recall.events_detected += int(per_event.sum())

    def rows(self) -> list[dict[str, Any]]:
        """One row per fault kind plus an ``all`` row with the totals and the precision."""
        out = []
        for fault, recall in [*sorted(self.by_fault.items()), ("all", self.total)]:
            is_total = fault == "all"
            out.append(
                {
                    "detector": self.detector,
                    "fault": fault,
                    "series": self.series,
                    "events": recall.events,
                    "events_detected": recall.events_detected,
                    "points": recall.points,
                    "points_detected": recall.points_detected,
                    "recall": recall.recall,
                    "event_recall": recall.event_recall,
                    "false_alarms": self.false_alarms if is_total else None,
                    "baseline_flags": self.baseline_flags if is_total else None,
                    "precision": self.precision if is_total else None,
                }
            )
        return out


def evaluate(detector: Detector, observations: pd.DataFrame, injector: FaultInjector, seed: int) -> Evaluation:
    """Inject faults into every series of ``observations`` and score them clean and corrupted.

    The random generator of each series derives from ``seed`` and its position, so a run is reproducible.
    """
    result = Evaluation(detector.name)
    for i, (_, group) in enumerate(observations.sort_values([*SERIES_KEYS, "ts"]).groupby(list(SERIES_KEYS))):
        clean = group[["ts", "value"]].reset_index(drop=True)
        corrupted = injector.inject(clean, np.random.default_rng([seed, i]))
        baseline = detector.score(clean)["is_anomaly"].to_numpy()
        flagged = detector.score(corrupted[["ts", "value"]])["is_anomaly"].to_numpy()
        result.add_series(flagged, baseline, corrupted)
    return result


def load_series(settings: Settings, source: str, window: TimeWindow, skip_metrics: frozenset[str]) -> pd.DataFrame:
    """Values labelled ``ok`` of one source in ``window``, as a pandas DataFrame."""
    with Warehouse(settings).connect() as conn:
        rows = conn.execute(
            """
            SELECT source, entity, metric, ts, value FROM silver.observations
             WHERE source = %s AND quality = %s AND value IS NOT NULL AND NOT (metric = ANY(%s))
               AND ts >= %s AND ts < %s
            """,
            (source, Quality.OK, sorted(skip_metrics), window.start_dt(), window.end_dt_exclusive()),
        ).fetchall()
    return pd.DataFrame(rows, columns=[*SERIES_KEYS, "ts", "value"])


def run_evaluation(
    *, run_id: str, days: int | None = None, seed: int | None = None, settings: Settings | None = None
) -> list[dict[str, Any]]:
    """Benchmark every configured detector and store the result in ``quality.anomaly_evaluations``."""
    settings = settings or Settings.from_env()
    config = AnomalyConfig.load(settings.anomaly_config)
    evaluation = EvaluationConfig.from_dict(config.evaluation)
    window = TimeWindow.last_days(days or evaluation.days)
    seed = evaluation.seed if seed is None else seed

    observations = load_series(settings, evaluation.source, window, config.skip_metrics)
    if observations.empty:
        msg = f"no '{evaluation.source}' values in {window.start}..{window.end} to inject faults into"
        raise ValueError(msg)
    injector = FaultInjector(evaluation.faults)
    rows = []
    for detector in config.build():
        result = evaluate(detector, observations, injector, seed)
        rows += [
            {**row, "source": evaluation.source, "window_start": window.start, "window_end": window.end}
            for row in result.rows()
        ]
        log.info("run %s: %s precision %s, recall %s", run_id, detector.name, result.precision, result.total.recall)

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    warehouse.record_evaluation(run_id, seed, rows)
    return rows
