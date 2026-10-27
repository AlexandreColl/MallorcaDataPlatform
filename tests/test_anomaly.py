from datetime import date
from functools import partial

import numpy as np
import pandas as pd
import pytest

from core.anomaly import SCORE_COLUMNS, RobustZScore
from core.anomaly.runner import ANOMALY_COLUMNS, ANOMALY_SCHEMA, SERIES_KEYS, AnomalyConfig, score_series
from core.config import PROJECT_ROOT
from core.models import TimeWindow


def hourly(values, start="2026-10-01"):
    ts = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "value": values})


def temperature(days=10, seed=7):
    """Daily cycle of 8 °C around 18 °C plus a little noise."""
    hours = np.arange(days * 24)
    noise = np.random.default_rng(seed).normal(0, 0.4, hours.size)
    return 18 + 4 * np.sin(2 * np.pi * hours / 24) + noise


def test_clean_series_has_no_anomalies():
    scored = RobustZScore().score(hourly(temperature()))
    assert list(scored.columns) == list(SCORE_COLUMNS)
    assert len(scored) == 240
    assert not scored["is_anomaly"].any()


def test_spike_is_flagged_and_expected_stays_normal():
    values = temperature()
    values[120] = 45.0
    scored = RobustZScore().score(hourly(values))
    flagged = scored[scored["is_anomaly"]]
    assert flagged.index.tolist() == [120]
    spike = flagged.iloc[0]
    assert spike["score"] > 3.5
    assert 14 < spike["expected"] < 22  # the median ignores the spike it is judging


def test_drop_gives_negative_score():
    values = temperature()
    values[60] = -5.0
    scored = RobustZScore().score(hourly(values))
    assert scored.loc[60, "is_anomaly"]
    assert scored.loc[60, "score"] < -3.5


def test_flat_window_is_not_scored():
    values = np.zeros(240)
    values[100] = 12.0  # one rainy hour in a dry week
    scored = RobustZScore().score(hourly(values))
    assert scored["score"].isna().all()
    assert not scored["is_anomaly"].any()


def test_too_few_points_are_not_scored():
    scored = RobustZScore(min_points=5).score(hourly([10.0, 11.0, 50.0]))
    assert scored["score"].isna().all()


def test_threshold_controls_sensitivity():
    values = temperature()
    values[120] = 28.0  # unusual but not extreme
    loose = RobustZScore(threshold=10).score(hourly(values))
    strict = RobustZScore(threshold=2).score(hourly(values))
    assert not loose.loc[120, "is_anomaly"]
    assert strict.loc[120, "is_anomaly"]


def test_context_is_half_the_centred_window():
    assert RobustZScore(window="7D").context == pd.Timedelta(days=3, hours=12)


def test_score_series_keeps_only_anomalies_inside_the_window():
    values = temperature(days=10)
    values[30] = 45.0  # 2026-10-02: context, before the window
    values[150] = 45.0  # 2026-10-07: inside
    series = hourly(values).assign(source="socib", entity="palma", metric="temperature_2m")
    window = TimeWindow(date(2026, 10, 5), date(2026, 10, 10))
    flagged = score_series(series.sample(frac=1, random_state=1), RobustZScore(), window)  # unsorted input
    assert list(flagged.columns) == list(ANOMALY_COLUMNS)
    assert flagged["ts"].tolist() == [pd.Timestamp("2026-10-07 06:00", tz="UTC")]
    row = flagged.iloc[0]
    assert (row["source"], row["entity"], row["metric"], row["detector"]) == (
        "socib",
        "palma",
        "temperature_2m",
        "robust_zscore",
    )
    assert row["value"] == 45.0


def test_score_series_accepts_naive_utc_timestamps():
    """applyInPandas hands timestamps over without a time zone."""
    values = temperature()
    values[150] = 45.0
    series = hourly(values).assign(source="s", entity="e", metric="m")
    series["ts"] = series["ts"].dt.tz_localize(None)
    flagged = score_series(series, RobustZScore(), TimeWindow(date(2026, 10, 5), date(2026, 10, 10)))
    assert len(flagged) == 1


def test_project_config_loads():
    config = AnomalyConfig.load(PROJECT_ROOT / "config" / "anomaly.yaml")
    assert config.rescore_days >= 1
    assert "ign" in config.skip_sources
    assert "precipitation" in config.skip_metrics
    (detector,) = config.build()
    assert isinstance(detector, RobustZScore)
    assert detector.threshold == 3.5


def test_unknown_detector_is_rejected(tmp_path):
    path = tmp_path / "anomaly.yaml"
    path.write_text("rescore_days: 7\ndetectors:\n  magic: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown detectors"):
        AnomalyConfig.load(path)


@pytest.mark.spark
def test_apply_in_pandas_scores_each_series_separately(spark):
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 10))
    calm = hourly(temperature(seed=1)).assign(source="socib", entity="palma", metric="temperature_2m")
    spiky_values = temperature(seed=2)
    spiky_values[100] = 45.0
    spiky = hourly(spiky_values).assign(source="socib", entity="soller", metric="temperature_2m")
    df = spark.createDataFrame(pd.concat([calm, spiky])[["source", "entity", "metric", "ts", "value"]])

    flagged = (
        df.groupBy(*SERIES_KEYS)
        .applyInPandas(partial(score_series, detector=RobustZScore(), window=window), ANOMALY_SCHEMA)
        .collect()
    )
    assert [(r.entity, r.value) for r in flagged] == [("soller", 45.0)]
