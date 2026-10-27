"""Detector interface: score the series of one location and flag the values that do not fit."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd

# Columns returned by `UnivariateDetector.score`, one row per input value.
SCORE_COLUMNS = ("ts", "value", "expected", "score", "threshold", "is_anomaly")
# Columns returned by `Detector.score_entity`: the same, per metric.
ENTITY_SCORE_COLUMNS = ("metric", *SCORE_COLUMNS)


class Detector(ABC):
    """Scores every series of one entity (a location, station or point) at once.

    Univariate detectors look at one metric at a time; multivariate ones also see how the metrics of a
    location move together. Detectors are plain pandas so they can be tested without Spark; the runner
    distributes them over the entities with ``applyInPandas``. They mark values and never correct them.
    """

    name: ClassVar[str]

    @property
    @abstractmethod
    def context(self) -> pd.Timedelta:
        """History needed before the first scored value (read in addition to the scored window)."""

    @abstractmethod
    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        """Score every value of one entity.

        Args:
            observations: columns ``metric``, ``ts`` (UTC) and ``value``; one row per metric and time.

        Returns:
            ``ENTITY_SCORE_COLUMNS``, one row per input row. ``expected`` is what the detector considers normal
            (NaN when it has no such notion) and ``score`` is NaN when the value cannot be judged.
        """


class UnivariateDetector(Detector):
    """A detector that judges each metric on its own history."""

    @abstractmethod
    def score(self, series: pd.DataFrame) -> pd.DataFrame:
        """Score every value of one series.

        Args:
            series: columns ``ts`` (UTC, sorted, unique) and ``value``.

        Returns:
            One row per input row with ``SCORE_COLUMNS``.
        """

    def score_entity(self, observations: pd.DataFrame) -> pd.DataFrame:
        """Score each metric separately."""
        parts = [
            self.score(series.sort_values("ts")[["ts", "value"]].reset_index(drop=True)).assign(metric=metric)
            for metric, series in observations.groupby("metric", sort=True)
        ]
        if not parts:
            return pd.DataFrame(columns=list(ENTITY_SCORE_COLUMNS))
        return pd.concat(parts, ignore_index=True)[list(ENTITY_SCORE_COLUMNS)]
