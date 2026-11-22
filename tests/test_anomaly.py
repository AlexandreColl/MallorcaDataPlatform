from datetime import date
from functools import partial

import numpy as np
import pandas as pd
import pytest

from core.anomaly import SCORE_COLUMNS, IsolationForestDetector, RobustZScore, SeasonalResidual, Vote
from core.anomaly.base import ENTITY_SCORE_COLUMNS, Detector
from core.anomaly.runner import (
    ANOMALY_COLUMNS,
    ANOMALY_SCHEMA,
    ENTITY_KEYS,
    AnomalyConfig,
    score_entities,
    score_entity,
)
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


def test_daily_series_use_the_daily_window():
    detector = RobustZScore(window="7D", daily_window="31D")
    daily = pd.Series(pd.date_range("2026-09-01", periods=40, freq="D", tz="UTC"))
    assert detector.window_for(daily) == "31D"
    assert detector.window_for(hourly(temperature())["ts"]) == "7D"
    assert detector.context == pd.Timedelta(days=15, hours=12)


def test_a_month_of_daily_values_raises_fewer_false_alarms_than_a_week():
    """Pure noise has no anomalies: with 7 daily values the MAD swings and ordinary days get flagged."""
    ts = pd.date_range("2026-01-01", periods=365, freq="D", tz="UTC")
    series = pd.DataFrame({"ts": ts, "value": 24 + np.random.default_rng(3).normal(0, 1.5, ts.size)})
    week = RobustZScore(daily_window="7D").score(series)["is_anomaly"].sum()
    month = RobustZScore(daily_window="31D").score(series)["is_anomaly"].sum()
    assert month < week / 2


def test_threshold_controls_sensitivity():
    values = temperature()
    values[120] = 28.0  # unusual but not extreme
    loose = RobustZScore(threshold=10).score(hourly(values))
    strict = RobustZScore(threshold=2).score(hourly(values))
    assert not loose.loc[120, "is_anomaly"]
    assert strict.loc[120, "is_anomaly"]


def test_context_is_half_the_centred_window():
    assert RobustZScore(window="7D", daily_window="1D").context == pd.Timedelta(days=3, hours=12)


def test_score_entity_keeps_only_anomalies_inside_the_window():
    values = temperature(days=10)
    values[30] = 45.0  # 2026-10-02: context, before the window
    values[150] = 45.0  # 2026-10-07: inside
    series = hourly(values).assign(source="socib", entity="palma", metric="temperature_2m")
    window = TimeWindow(date(2026, 10, 5), date(2026, 10, 10))
    flagged = score_entity(series.sample(frac=1, random_state=1), RobustZScore(), window)  # unsorted input
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


def test_score_entity_accepts_naive_utc_timestamps():
    """applyInPandas hands timestamps over without a time zone."""
    values = temperature()
    values[150] = 45.0
    series = hourly(values).assign(source="s", entity="e", metric="m")
    series["ts"] = series["ts"].dt.tz_localize(None)
    flagged = score_entity(series, RobustZScore(), TimeWindow(date(2026, 10, 5), date(2026, 10, 10)))
    assert len(flagged) == 1


def test_project_config_loads():
    config = AnomalyConfig.load(PROJECT_ROOT / "config" / "anomaly.yaml")
    assert config.rescore_days >= 1
    assert "ign" in config.skip_sources
    assert "precipitation" in config.skip_metrics
    zscore, seasonal, forest, vote = config.build()
    assert isinstance(zscore, RobustZScore)
    assert zscore.threshold == 3.5
    assert isinstance(seasonal, SeasonalResidual)
    assert isinstance(forest, IsolationForestDetector)
    assert isinstance(vote, Vote)
    members = {type(m): m for m in vote.members}
    assert set(members) == {SeasonalResidual, IsolationForestDetector}
    assert members[SeasonalResidual] is seasonal  # the same instance as the detector run alone: scored once
    assert members[IsolationForestDetector] is forest
    assert vote.min_votes == 1


def test_unknown_detector_is_rejected(tmp_path):
    path = tmp_path / "anomaly.yaml"
    path.write_text("rescore_days: 7\ndetectors:\n  magic: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown detectors"):
        AnomalyConfig.load(path)


@pytest.mark.parametrize("members", ["[magic]", "[vote, robust_zscore]"])
def test_a_vote_only_takes_other_known_detectors(tmp_path, members):
    path = tmp_path / "anomaly.yaml"
    path.write_text(f"rescore_days: 7\ndetectors:\n  vote: {{members: {members}}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="members of vote"):
        AnomalyConfig.load(path)


def test_a_vote_member_without_an_entry_takes_its_defaults(tmp_path):
    path = tmp_path / "anomaly.yaml"
    path.write_text("rescore_days: 7\ndetectors:\n  vote: {members: [robust_zscore], min_votes: 1}\n", encoding="utf-8")
    (vote,) = AnomalyConfig.load(path).build()
    assert vote.members[0].threshold == RobustZScore().threshold


@pytest.mark.spark
def test_apply_in_pandas_scores_each_entity_separately(spark):
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 10))
    calm = hourly(temperature(seed=1)).assign(source="socib", entity="palma", metric="temperature_2m")
    spiky_values = temperature(seed=2)
    spiky_values[100] = 45.0
    spiky = hourly(spiky_values).assign(source="socib", entity="soller", metric="temperature_2m")
    df = spark.createDataFrame(pd.concat([calm, spiky])[["source", "entity", "metric", "ts", "value"]])

    flagged = (
        df.groupBy(*ENTITY_KEYS)
        .applyInPandas(partial(score_entity, detector=RobustZScore(), window=window), ANOMALY_SCHEMA)
        .collect()
    )
    assert [(r.entity, r.value) for r in flagged] == [("soller", 45.0)]


class Counting(Detector):
    """A detector that flags values above 30 and counts how many times it scores an entity."""

    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def context(self) -> pd.Timedelta:
        return pd.Timedelta(0)

    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        self.calls += 1
        out = observations[["metric", "ts", "value"]].reset_index(drop=True)
        return out.assign(expected=np.nan, score=out["value"], threshold=30.0, is_anomaly=out["value"] > 30)


def test_a_vote_counts_what_its_members_already_scored():
    member = Counting()
    vote = Vote([member])
    values = temperature()
    values[150] = 45.0
    observations = hourly(values).assign(source="socib", entity="soller", metric="temperature_2m")
    window = TimeWindow(date(2026, 10, 1), date(2026, 10, 10))

    flagged = score_entities(observations, [member, vote], window)

    assert member.calls == 1  # not once more inside the vote
    assert flagged.groupby("detector")["value"].apply(list).to_dict() == {"counting": [45.0], "vote": [45.0]}


def test_scoring_every_detector_at_once_flags_what_scoring_each_alone_does():
    values = temperature()
    values[120] = 45.0
    values[180:186] += 6.0  # a shift the seasonal residual sees
    observations = hourly(values).assign(source="socib", entity="soller", metric="temperature_2m")
    window = TimeWindow(date(2026, 10, 3), date(2026, 10, 10))
    detectors = AnomalyConfig.load(PROJECT_ROOT / "config" / "anomaly.yaml").build()

    together = score_entities(observations, detectors, window)
    alone = pd.concat([score_entity(observations, d, window) for d in detectors], ignore_index=True)

    def by_key(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values(["detector", "ts"], ignore_index=True)

    pd.testing.assert_frame_equal(by_key(together), by_key(alone))
    assert set(together["detector"]) >= {"robust_zscore", "vote"}


def test_a_vote_needs_one_scored_frame_per_member():
    with pytest.raises(ValueError, match="2 members got 1"):
        Vote([Counting(), Counting()]).combine(hourly(temperature()).assign(metric="t"), [pd.DataFrame()])


class Silent(Counting):
    """Flags nothing, with the untyped empty frame a univariate detector returns for an entity without series."""

    name = "silent"

    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(columns=list(ENTITY_SCORE_COLUMNS))


def test_an_empty_untyped_result_does_not_turn_the_others_into_objects():
    values = temperature()
    values[150] = 45.0
    observations = hourly(values).assign(source="socib", entity="soller", metric="temperature_2m")

    flagged = score_entities(observations, [Silent(), Counting()], TimeWindow(date(2026, 10, 1), date(2026, 10, 10)))

    assert flagged["value"].tolist() == [45.0]
    assert str(flagged["ts"].dtype).startswith("datetime64")
    assert str(flagged["ts"].dt.tz) == "UTC"
    assert flagged["score"].dtype == "float64"


@pytest.mark.spark
def test_every_detector_of_the_project_scores_in_one_spark_pass(spark):
    window = TimeWindow(date(2026, 10, 3), date(2026, 10, 10))
    calm = hourly(temperature(seed=1)).assign(source="socib", entity="palma", metric="temperature_2m")
    spiky_values = temperature(seed=2)
    spiky_values[150] = 45.0
    spiky = hourly(spiky_values).assign(source="socib", entity="soller", metric="temperature_2m")
    df = spark.createDataFrame(pd.concat([calm, spiky])[["source", "entity", "metric", "ts", "value"]])
    detectors = AnomalyConfig.load(PROJECT_ROOT / "config" / "anomaly.yaml").build()

    flagged = (
        df.groupBy(*ENTITY_KEYS)
        .applyInPandas(partial(score_entities, detectors=detectors, window=window), ANOMALY_SCHEMA)
        .collect()
    )

    spike = {r.detector for r in flagged if r.entity == "soller" and r.value == 45.0}
    assert {"robust_zscore", "vote"} <= spike
