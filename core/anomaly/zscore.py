"""Robust z-score: distance to the rolling median, measured in rolling MADs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.anomaly.base import SCORE_COLUMNS, Detector

# Scales the MAD to the standard deviation of normally distributed data, so thresholds read like z-scores.
_MAD_TO_SIGMA = 0.6745


def _mad(values: np.ndarray) -> float:
    """Median absolute deviation from the median."""
    return float(np.median(np.abs(values - np.median(values))))


class RobustZScore(Detector):
    """Modified z-score of Iglewicz and Hoaglin over a centred rolling window.

    Median and MAD barely move when the window contains the spike being looked for, unlike the mean and
    the standard deviation, which a single outlier inflates until it hides itself. A window where most
    values are identical (MAD = 0, e.g. a flat sea or a constant schedule) is not scored: any change in it
    would look infinitely anomalous.
    """

    name = "robust_zscore"

    def __init__(self, window: str = "7D", threshold: float = 3.5, min_points: int = 5) -> None:
        self.window = window
        self.threshold = float(threshold)
        self.min_points = int(min_points)

    @property
    def context(self) -> pd.Timedelta:
        """The window is centred: the first scored value needs half of it before."""
        return pd.Timedelta(self.window) / 2

    def score(self, series: pd.DataFrame) -> pd.DataFrame:
        """Modified z-score of every value against the values within ``window`` around it."""
        values = series.set_index("ts")["value"].astype(float)
        rolling = values.rolling(self.window, center=True, min_periods=self.min_points)
        median = rolling.median()
        mad = rolling.apply(_mad, raw=True)
        score = _MAD_TO_SIGMA * (values - median) / mad.where(mad > 0)
        out = pd.DataFrame(
            {
                "ts": values.index,
                "value": values.to_numpy(),
                "expected": median.to_numpy(),
                "score": score.to_numpy(),
                "threshold": self.threshold,
            }
        )
        out["is_anomaly"] = out["score"].abs().gt(self.threshold)  # NaN scores are never anomalies
        return out[list(SCORE_COLUMNS)]
