import numpy as np
import pandas as pd

from core.anomaly import ENTITY_SCORE_COLUMNS, IsolationForestDetector


def location(days=20, seed=0):
    """Temperature, humidity and wind of one place: daily cycles, humidity moving against temperature."""
    rng = np.random.default_rng(seed)
    hours = np.arange(days * 24)
    cycle = np.sin(2 * np.pi * hours / 24)
    ts = pd.date_range("2026-10-01", periods=hours.size, freq="h", tz="UTC")
    metrics = {
        "temperature_2m": 18 + 4 * cycle + rng.normal(0, 0.4, hours.size),
        "relative_humidity_2m": 70 - 12 * cycle + rng.normal(0, 2, hours.size),
        "wind_speed_10m": 12 + 3 * rng.standard_normal(hours.size).cumsum() / np.sqrt(hours.size),
    }
    return pd.concat([pd.DataFrame({"metric": m, "ts": ts, "value": v}) for m, v in metrics.items()], ignore_index=True)


def flagged(scored, metric=None):
    rows = scored[scored["is_anomaly"]]
    return rows if metric is None else rows[rows["metric"] == metric]


def test_one_row_per_input_value():
    data = location()
    scored = IsolationForestDetector().score_entity(data)
    assert list(scored.columns) == list(ENTITY_SCORE_COLUMNS)
    assert len(scored) == len(data)
    assert scored["score"].notna().mean() > 0.95  # only the first values lack change and spread


def test_one_metric_is_blamed_per_flagged_timestamp():
    scored = IsolationForestDetector(contamination=0.01).score_entity(location())
    per_ts = scored[scored["is_anomaly"]].groupby("ts").size()
    assert (per_ts == 1).all()
    assert scored["is_anomaly"].mean() < 0.01


def test_spike_is_flagged_and_blamed_on_its_metric():
    data = location()
    temperature = data.index[data["metric"] == "temperature_2m"]
    data.loc[temperature[200], "value"] = 40.0
    scored = IsolationForestDetector().score_entity(data)
    assert data.loc[temperature[200], "ts"] in set(flagged(scored, "temperature_2m")["ts"])


def test_frozen_sensor_is_flagged_where_the_z_score_is_blind():
    data = location()
    humidity = data.index[data["metric"] == "relative_humidity_2m"]
    frozen = humidity[240:264]
    data.loc[frozen, "value"] = data.loc[humidity[239], "value"]  # stuck for a day at a normal level
    scored = IsolationForestDetector().score_entity(data)
    hits = set(flagged(scored, "relative_humidity_2m")["ts"]) & set(data.loc[frozen, "ts"])
    assert hits


def test_same_random_state_same_result():
    data = location()
    a = IsolationForestDetector(random_state=1).score_entity(data)
    b = IsolationForestDetector(random_state=1).score_entity(data)
    pd.testing.assert_frame_equal(a, b)


def test_contamination_sets_the_share_of_flagged_timestamps():
    scored = IsolationForestDetector(contamination=0.05).score_entity(location())
    share = scored.groupby("ts")["is_anomaly"].any().mean()
    assert 0.04 < share < 0.06


def test_too_few_timestamps_are_not_scored():
    scored = IsolationForestDetector(min_points=48).score_entity(location(days=1))
    assert scored["score"].isna().all()
    assert not scored["is_anomaly"].any()


def test_metric_of_another_frequency_does_not_empty_the_forest():
    data = location()
    daily_ts = pd.date_range("2026-10-01", periods=20, freq="D", tz="UTC")
    daily = pd.DataFrame({"metric": "co2_intensity", "ts": daily_ts, "value": np.linspace(0.5, 0.6, 20)})
    scored = IsolationForestDetector().score_entity(pd.concat([data, daily], ignore_index=True))
    assert scored.loc[scored["metric"] == "temperature_2m", "score"].notna().mean() > 0.95
    assert not flagged(scored, "co2_intensity").shape[0]
