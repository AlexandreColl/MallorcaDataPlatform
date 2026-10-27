"""Anomaly detection over silver: reusable detectors and the runner that stores what they flag."""

from core.anomaly.base import SCORE_COLUMNS, Detector
from core.anomaly.zscore import RobustZScore

__all__ = ["SCORE_COLUMNS", "Detector", "RobustZScore"]
