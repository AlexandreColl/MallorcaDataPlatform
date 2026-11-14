"""Seasonal residual: distance to the value the same series had at the same time on the days around it."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.anomaly.base import SCORE_COLUMNS, UnivariateDetector
from core.anomaly.zscore import _MAD_TO_SIGMA


def _nan_mad(values: np.ndarray) -> float:
    """Median absolute deviation from the median, ignoring the NaN residuals of values without neighbours."""
    return float(np.nanmedian(np.abs(values - np.nanmedian(values))))


class SeasonalResidual(UnivariateDetector):
    """Modified z-score of the residual left after removing the daily (or weekly) cycle.

    The expected value of each reading is the median of the readings at the same time of day on the ``periods``
    days before and after it (the same weekday, for daily series). The residual is then scored like
    `RobustZScore` scores values: in rolling MADs around its rolling median. Removing the cycle first is what lets
    it see a clock or time-zone error: values from 12 hours earlier are ordinary for the series, but not for that
    hour. It also sees a sensor frozen at a value normal for the day but not for the hour.

    A missing reading at one of those times only shortens the median; with fewer than ``min_periods`` of them the
    value is not scored. Readings that are not on a whole step of the cycle (an irregular source) find no
    neighbours and are not scored either.
    """

    name = "seasonal_residual"

    def __init__(  # noqa: PLR0913 - one parameter per key of its entry in config/anomaly.yaml
        self,
        *,
        periods: int = 3,
        min_periods: int = 3,
        window: str = "7D",
        daily_window: str = "63D",
        threshold: float = 4.5,
        min_points: int = 24,
        changes: bool = True,
    ) -> None:
        self.changes = bool(changes)
        self.periods = int(periods)
        self.min_periods = int(min_periods)
        self.window = window
        self.daily_window = daily_window  # daily series have one residual a day: they need a longer window
        self.threshold = float(threshold)
        self.min_points = int(min_points)

    @property
    def context(self) -> pd.Timedelta:
        """The neighbours of the first scored value of a daily series reach ``periods`` weeks back."""
        return max(self.periods * pd.Timedelta(weeks=1), pd.Timedelta(self.daily_window) / 2)

    @staticmethod
    def cycle(ts: pd.Series) -> pd.Timedelta:
        """A day for sub-daily series, a week for series a day or more apart (median spacing)."""
        is_daily = len(ts) > 1 and ts.diff().median() >= pd.Timedelta(days=1)
        return pd.Timedelta(weeks=1) if is_daily else pd.Timedelta(days=1)

    def expected(self, values: pd.Series, cycle: pd.Timedelta) -> pd.Series:
        """Median of the values ``1..periods`` cycles before and after each one (NaN with too few of them)."""
        index = pd.DatetimeIndex(values.index)
        lags = [k for k in range(-self.periods, self.periods + 1) if k != 0]
        neighbours = np.column_stack([values.reindex(index + k * cycle).to_numpy() for k in lags])
        enough = np.isfinite(neighbours).sum(axis=1) >= self.min_periods
        median = np.full(len(values), np.nan)
        if enough.any():
            median[enough] = np.nanmedian(neighbours[enough], axis=1)
        return pd.Series(median, index=values.index)

    def residual_score(self, values: pd.Series, cycle: pd.Timedelta, window: str) -> tuple[pd.Series, pd.Series]:
        """Expected value of every point and the modified z-score of its residual within ``window``."""
        expected = self.expected(values, cycle)
        residual = values - expected
        rolling = residual.rolling(window, center=True, min_periods=self.min_points)
        centre = rolling.median()
        mad = rolling.apply(_nan_mad, raw=True)
        return expected + centre, _MAD_TO_SIGMA * (residual - centre) / mad.where(mad > 0)

    def score(self, series: pd.DataFrame) -> pd.DataFrame:
        """The larger of the scores of the value and of its change, each against the same time on nearby days."""
        values = series.set_index("ts")["value"].astype(float)
        cycle = self.cycle(series["ts"])
        window = self.daily_window if cycle >= pd.Timedelta(weeks=1) else self.window
        expected, score = self.residual_score(values, cycle, window)
        if self.changes:
            # The change since the previous step, where the previous value is one step before. The weather of one
            # day shifts the level of every hour, but much less how much each hour warms or cools.
            index = pd.DatetimeIndex(values.index)
            step = pd.Series(index).diff().median()
            change = values - values.reindex(index - step).to_numpy()
            _, jump = self.residual_score(change, cycle, window)
            # An odd change involves two values: it is blamed on the one further from its usual level, so the jump
            # back to normal after a fault flags the fault's last value and not the first good one.
            level = score.abs().fillna(0)
            previous = pd.Series(level.reindex(index - step).to_numpy(), index=values.index).fillna(0)
            on_this = jump.where(level.ge(previous))
            on_previous = pd.Series(jump.where(level.lt(previous)).reindex(index + step).to_numpy(), index=values.index)
            change_score = on_this.where(on_this.abs().ge(on_previous.abs()) | on_previous.isna(), on_previous)
            score = score.where(score.abs().ge(change_score.abs()) | change_score.isna(), change_score)
        out = pd.DataFrame(
            {
                "ts": values.index,
                "value": values.to_numpy(),
                "expected": expected.to_numpy(),
                "score": score.to_numpy(),
                "threshold": self.threshold,
            }
        )
        out["is_anomaly"] = out["score"].abs().gt(self.threshold)
        return out[list(SCORE_COLUMNS)]
