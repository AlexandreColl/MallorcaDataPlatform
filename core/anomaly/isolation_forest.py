"""Isolation Forest over every metric of a location: values that are odd together, or a sensor that stops moving."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from core.anomaly.base import ENTITY_SCORE_COLUMNS, Detector

_MAD_TO_SIGMA = 1.4826
_TIME = "_time"  # prefix of the hour-of-day features, which no metric is blamed for


def _robust_standardise(features: pd.DataFrame) -> pd.DataFrame:
    """Centre on the median and scale by the MAD (the standard deviation if the MAD is 0, 1 if that is too)."""
    median = features.median()
    scale = _MAD_TO_SIGMA * (features - median).abs().median()
    scale = scale.where(scale > 0, features.std()).replace(0, 1).fillna(1)
    return (features - median) / scale


class IsolationForestDetector(Detector):
    """Isolation Forest (Liu, Ting and Zhou) on the joint behaviour of the metrics of one entity.

    Each timestamp is a point described, for every metric, by its value, its change since the previous value
    and how many values in a row it has stayed the same, plus the hour of day for sub-daily series. The forest
    isolates points that few random splits are needed to separate: a temperature that does not match the
    humidity or the hour, a jump no other metric shows, or a series that always moves and has stopped (a frozen
    sensor). A rolling spread is not enough for that last case: near the top or bottom of a daily cycle the
    spread is almost zero anyway, while a run of identical values is rare.

    The forest flags a timestamp; the metric whose features stray furthest from their median at that time is
    the one flagged, so the result fits ``silver.anomalies`` like any univariate detector.
    """

    name = "isolation_forest"

    def __init__(  # noqa: PLR0913 - every argument is a documented setting of config/anomaly.yaml
        self,
        *,
        contamination: float | str = 0.01,
        n_estimators: int = 200,
        min_points: int = 48,
        min_coverage: float = 0.8,
        random_state: int = 42,
    ) -> None:
        self.contamination = contamination
        self.n_estimators = int(n_estimators)
        self.min_points = int(min_points)
        self.min_coverage = float(min_coverage)  # metrics present at fewer timestamps (another frequency) are left out
        self.random_state = int(random_state)

    @property
    def context(self) -> pd.Timedelta:
        """The change and stillness features look back a few values."""
        return pd.Timedelta(days=1)

    @staticmethod
    def features(wide: pd.DataFrame) -> pd.DataFrame:
        """Value, change and stillness of every metric (columns ``(metric, feature)``), plus the hour of day."""
        columns: dict[tuple[str, str], pd.Series] = {}
        for metric in wide.columns:
            values = wide[metric]
            change = values.diff()
            unchanged = change.eq(0)
            columns[metric, "value"] = values
            columns[metric, "change"] = change
            # Values in a row equal to the previous one: 0 while the series moves, it grows on a frozen sensor.
            columns[metric, "still"] = unchanged.groupby((~unchanged).cumsum()).cumsum().astype(float)
        index = pd.DatetimeIndex(wide.index)
        if len(index) > 1 and pd.Series(index).diff().median() < pd.Timedelta(days=1):
            angle = 2 * np.pi * index.hour.to_numpy() / 24
            columns[_TIME, "hour_sin"] = pd.Series(np.sin(angle), index=wide.index)
            columns[_TIME, "hour_cos"] = pd.Series(np.cos(angle), index=wide.index)
        return pd.DataFrame(columns, index=wide.index)

    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        """Fit a forest on the entity's timestamps and flag the metric to blame at each isolated one."""
        out = (
            observations[["metric", "ts", "value"]]
            .reset_index(drop=True)
            .assign(expected=np.nan, score=np.nan, threshold=0.0, is_anomaly=False)
        )
        wide = observations.pivot_table(index="ts", columns="metric", values="value", aggfunc="first").sort_index()
        wide = wide.loc[:, wide.notna().mean() >= self.min_coverage]
        features = self.features(wide).dropna() if not wide.empty else pd.DataFrame()
        if len(features) < self.min_points:
            return out[list(ENTITY_SCORE_COLUMNS)]

        standardised = _robust_standardise(features)
        forest = IsolationForest(
            n_estimators=self.n_estimators, contamination=self.contamination, random_state=self.random_state
        ).fit(standardised.to_numpy())
        # decision_function < 0 means isolated: flip it so that, like a z-score, bigger is more anomalous.
        score = pd.Series(-forest.decision_function(standardised.to_numpy()), index=features.index)
        blame = standardised.drop(columns=_TIME, level=0, errors="ignore").abs().T.groupby(level=0).max().T
        culprit = blame.idxmax(axis=1)

        keys = pd.MultiIndex.from_arrays([out["ts"], out["metric"]])
        out["score"] = score.reindex(out["ts"]).to_numpy()
        flagged = pd.MultiIndex.from_arrays([culprit.index[score > 0], culprit[score > 0].to_numpy()])
        out["is_anomaly"] = keys.isin(flagged)
        return out[list(ENTITY_SCORE_COLUMNS)]
