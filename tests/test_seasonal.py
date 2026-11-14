import numpy as np
import pandas as pd
import pytest

from core.anomaly import ENTITY_SCORE_COLUMNS, SCORE_COLUMNS, RobustZScore, SeasonalResidual, Vote
from core.anomaly.base import Detector


def hourly(values, start="2026-10-01"):
    ts = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "value": np.asarray(values, dtype=float)})


def temperature(days=14, seed=7):
    """Daily cycle of 8 °C around 18 °C, a slow change of weather and a little noise."""
    rng = np.random.default_rng(seed)
    hours = np.arange(days * 24)
    weather = 2 * np.sin(2 * np.pi * hours / (24 * 9))
    return 18 + weather + 4 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 0.3, hours.size)


def flagged(scored):
    return scored.index[scored["is_anomaly"]].tolist()


def test_clean_series_has_no_anomalies():
    scored = SeasonalResidual().score(hourly(temperature()))
    assert list(scored.columns) == list(SCORE_COLUMNS)
    assert len(scored) == 14 * 24
    assert flagged(scored) == []


def test_clock_error_is_flagged_where_the_z_score_is_blind():
    values = temperature()
    values[180:190] = values[168:178]  # ten hours with the values of twelve hours earlier: night in the day
    series = hourly(values)
    assert flagged(RobustZScore().score(series)) == []
    hits = flagged(SeasonalResidual().score(series))
    assert hits
    assert set(hits) <= set(range(180, 190))


def test_spike_is_flagged_and_not_the_good_value_after_it():
    values = temperature()
    values[200] += 6
    scored = SeasonalResidual().score(hourly(values))
    assert flagged(scored) == [200]
    assert scored.loc[200, "expected"] == pytest.approx(values[200] - 6, abs=1.5)


def test_level_only_misses_the_clock_error_that_changes_see():
    values = temperature()
    values[180:190] = values[168:178]
    hits = flagged(SeasonalResidual(changes=False, threshold=6).score(hourly(values)))
    assert len(hits) < len(flagged(SeasonalResidual(threshold=6).score(hourly(values))))


def test_values_without_enough_neighbours_are_not_scored():
    scored = SeasonalResidual(min_points=5).score(hourly(temperature(days=2)))
    assert scored["score"].isna().all()  # one day before or after each value, three needed
    assert flagged(scored) == []


def test_daily_series_follow_the_week():
    days = pd.date_range("2026-06-01", periods=12 * 7, freq="D", tz="UTC")
    rng = np.random.default_rng(3)
    demand = 600 - 120 * (days.dayofweek >= 5) + rng.normal(0, 8, days.size)  # weekends are quieter
    demand[45] = demand[45] - 120 if days[45].dayofweek < 5 else demand[45] + 120  # a weekday like a Sunday
    series = pd.DataFrame({"ts": days, "value": demand})
    assert SeasonalResidual.cycle(series["ts"]) == pd.Timedelta(weeks=1)
    assert 45 in flagged(SeasonalResidual().score(series))


def test_irregular_values_find_no_neighbours():
    series = hourly(temperature())
    series["ts"] += pd.to_timedelta(np.random.default_rng(1).integers(1, 59, len(series)), unit="min")
    assert SeasonalResidual().score(series)["score"].isna().all()


def test_context_covers_the_neighbours_of_daily_series():
    assert SeasonalResidual(periods=3, daily_window="28D").context == pd.Timedelta(weeks=3)
    assert SeasonalResidual(periods=1, daily_window="63D").context == pd.Timedelta(days=31.5)


class Fixed(Detector):
    """Flags fixed timestamps of every metric, with a fixed expected value."""

    def __init__(self, name, hours, expected=np.nan):
        self.name = name
        self.hours = set(hours)
        self.expected_value = expected

    @property
    def context(self):
        return pd.Timedelta(hours=len(self.hours))

    def score_entity(self, observations):
        hour = (observations["ts"] - observations["ts"].min()) // pd.Timedelta(hours=1)
        return observations.assign(
            expected=self.expected_value, score=0.0, threshold=0.0, is_anomaly=hour.isin(self.hours)
        )[list(ENTITY_SCORE_COLUMNS)]


def entity():
    return pd.concat([hourly(temperature(days=1)).assign(metric=m) for m in ("t", "rh")], ignore_index=True)


def test_vote_of_one_is_the_union_and_counts_the_votes():
    vote = Vote([Fixed("a", [1, 2]), Fixed("b", [2, 3], expected=18.0)], min_votes=1)
    scored = vote.score_entity(entity())
    assert list(scored.columns) == list(ENTITY_SCORE_COLUMNS)
    t = scored[scored["metric"] == "t"].reset_index(drop=True)
    assert flagged(t) == [1, 2, 3]
    assert t.loc[[1, 2, 3], "score"].tolist() == [1.0, 2.0, 1.0]
    assert (t["threshold"] == 1.0).all()
    assert (t["expected"] == 18.0).all()  # the first member without one takes the next member's


def test_vote_of_two_keeps_what_both_flag():
    vote = Vote([Fixed("a", [1, 2]), Fixed("b", [2, 3])], min_votes=2)
    scored = vote.score_entity(entity())
    assert flagged(scored[scored["metric"] == "rh"].reset_index(drop=True)) == [2]
    assert vote.context == pd.Timedelta(hours=2)


@pytest.mark.parametrize("min_votes", [0, 3])
def test_vote_needs_a_reachable_number_of_votes(min_votes):
    with pytest.raises(ValueError, match="min_votes"):
        Vote([Fixed("a", []), Fixed("b", [])], min_votes=min_votes)
