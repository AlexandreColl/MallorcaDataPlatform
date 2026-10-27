import itertools

import numpy as np
import pandas as pd
import pytest

from core.anomaly import RobustZScore
from core.anomaly.base import SCORE_COLUMNS, Detector
from core.anomaly.evaluation import Evaluation, EvaluationConfig, evaluate
from core.anomaly.faults import FaultInjector, FaultSpec, robust_sigma
from core.anomaly.runner import AnomalyConfig
from core.config import PROJECT_ROOT

SPECS = {
    "spike": FaultSpec(count=3, size=(6, 8)),
    "frozen": FaultSpec(count=1, length=(12, 12)),
    "drift": FaultSpec(count=1, length=(72, 72), size=(3, 3)),
}


def hourly(values):
    ts = pd.date_range("2026-10-01", periods=len(values), freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "value": np.asarray(values, dtype=float)})


def temperature(days=30, seed=7):
    hours = np.arange(days * 24)
    return 18 + 4 * np.sin(2 * np.pi * hours / 24) + np.random.default_rng(seed).normal(0, 0.4, hours.size)


def observations(n_series=4):
    frames = [
        hourly(temperature(seed=s)).assign(source="open_meteo", entity=f"e{s}", metric="t") for s in range(n_series)
    ]
    return pd.concat(frames, ignore_index=True)


class FlagIndexes(Detector):
    """Flags fixed positions, to check the arithmetic of the evaluation."""

    name = "fixed"

    def __init__(self, indexes):
        self.indexes = set(indexes)

    @property
    def context(self):
        return pd.Timedelta(0)

    def score(self, series):
        flagged = [i in self.indexes for i in range(len(series))]
        return series.assign(expected=np.nan, score=0.0, threshold=0.0, is_anomaly=flagged)[list(SCORE_COLUMNS)]


def test_injection_is_reproducible_and_leaves_the_input_untouched():
    clean = hourly(temperature())
    before = clean.copy()
    a = FaultInjector(SPECS).inject(clean, np.random.default_rng(1))
    b = FaultInjector(SPECS).inject(clean, np.random.default_rng(1))
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(clean, before)


def test_each_fault_has_its_length_and_they_do_not_touch():
    out = FaultInjector(SPECS, margin=6).inject(hourly(temperature()), np.random.default_rng(3))
    assert out["fault"].value_counts().to_dict() == {"drift": 72, "frozen": 12, "spike": 3}
    assert out.loc[out["event"] >= 0, "event"].nunique() == 5
    spans = sorted(out[out["event"] >= 0].groupby("event").apply(lambda g: (g.index.min(), g.index.max())).tolist())
    gaps = [b[0] - a[1] for a, b in itertools.pairwise(spans)]
    assert min(gaps) > 6


def test_fault_shapes():
    clean = hourly(temperature())
    sigma = robust_sigma(clean["value"].to_numpy())
    out = FaultInjector(SPECS).inject(clean, np.random.default_rng(5))
    delta = out["value"] - clean["value"]

    spikes = delta[out["fault"] == "spike"].abs()
    assert ((spikes >= 6 * sigma - 1e-9) & (spikes <= 8 * sigma + 1e-9)).all()

    frozen = out[out["fault"] == "frozen"]
    assert (frozen["value"] == frozen["value"].iloc[0]).all()
    assert frozen["value"].iloc[0] == clean.loc[frozen.index[0] - 1, "value"]  # stuck at the last good value

    ramp = delta[out["fault"] == "drift"].abs().to_numpy()
    assert np.all(np.diff(ramp) > 0)
    assert ramp[-1] == pytest.approx(3 * sigma)

    assert (delta[out["fault"].isna()] == 0).all()


def test_constant_series_is_left_clean():
    out = FaultInjector(SPECS).inject(hourly(np.full(200, 5.0)), np.random.default_rng(0))
    assert out["fault"].isna().all()


def test_short_series_gets_the_faults_that_fit():
    out = FaultInjector(SPECS).inject(hourly(temperature(days=2)), np.random.default_rng(0))
    assert "drift" not in set(out["fault"].dropna())  # 72 values do not fit in 48
    assert (out["fault"] == "spike").sum() == 3


def test_unknown_fault_kind_is_rejected():
    with pytest.raises(ValueError, match="unknown fault kinds"):
        FaultInjector({"teleport": FaultSpec(count=1)})


def test_evaluation_counts_true_positives_false_alarms_and_baseline():
    corrupted = hourly(np.arange(10.0)).assign(fault=None, event=-1)
    corrupted.loc[[2, 3], ["fault", "event"]] = ["frozen", 0]
    corrupted.loc[7, ["fault", "event"]] = ["spike", 1]
    flagged = np.zeros(10, dtype=bool)
    flagged[[3, 5, 9]] = True  # one frozen value, a false alarm, a real event
    baseline = np.zeros(10, dtype=bool)
    baseline[9] = True

    result = Evaluation("fixed")
    result.add_series(flagged, baseline, corrupted)

    assert (result.true_positives, result.false_alarms, result.baseline_flags) == (1, 1, 1)
    assert result.precision == 0.5
    frozen, spike = result.by_fault["frozen"], result.by_fault["spike"]
    assert (frozen.recall, frozen.event_recall) == (0.5, 1.0)
    assert (spike.recall, spike.event_recall) == (0.0, 0.0)
    rows = {r["fault"]: r for r in result.rows()}
    assert rows["all"]["recall"] == pytest.approx(1 / 3)
    assert rows["all"]["precision"] == 0.5
    assert rows["spike"]["precision"] is None


def test_detector_that_flags_nothing_has_no_precision_and_zero_recall():
    result = evaluate(FlagIndexes([]), observations(2), FaultInjector(SPECS), seed=1)
    assert result.series == 2
    assert result.precision is None
    assert result.total.recall == 0.0


def test_robust_zscore_catches_spikes_but_not_frozen_values():
    """What the benchmark shows: the z-score sees values far from their neighbours, not values stuck at normal."""
    result = evaluate(RobustZScore(), observations(), FaultInjector(SPECS), seed=42)
    assert result.by_fault["spike"].recall >= 0.9
    assert result.by_fault["frozen"].recall == 0.0
    assert result.precision >= 0.9


def test_project_config_has_a_valid_evaluation_block():
    config = AnomalyConfig.load(PROJECT_ROOT / "config" / "anomaly.yaml")
    evaluation = EvaluationConfig.from_dict(config.evaluation)
    assert evaluation.source == "open_meteo"
    assert set(evaluation.faults) == set(FaultInjector.KINDS)
    assert evaluation.faults["frozen"].length[0] >= 2
    FaultInjector(evaluation.faults)
