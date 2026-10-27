"""Detector interface: score one time series and flag the values that do not fit it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import pandas as pd

# Columns returned by `Detector.score`, one row per input value.
SCORE_COLUMNS = ("ts", "value", "expected", "score", "threshold", "is_anomaly")


class Detector(ABC):
    """Scores one series (a single source, entity and metric).

    Detectors are plain pandas so they can be tested without Spark; the runner distributes them over every
    series with ``applyInPandas``. They mark values and never correct them: corrections are a later phase.
    """

    name: ClassVar[str]

    @property
    @abstractmethod
    def context(self) -> pd.Timedelta:
        """History needed before the first scored value (read in addition to the scored window)."""

    @abstractmethod
    def score(self, series: pd.DataFrame) -> pd.DataFrame:
        """Score every value of a series.

        Args:
            series: columns ``ts`` (UTC, sorted, unique) and ``value``.

        Returns:
            One row per input row with ``SCORE_COLUMNS``. ``expected`` is what the detector considers normal
            at that time and ``score`` is NaN when the value cannot be judged (too little history, flat window).
        """
