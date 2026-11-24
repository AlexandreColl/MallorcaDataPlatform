"""Correction methods for one hourly station series: plain pandas, testable without a warehouse.

A series is corrected on its hourly grid between its first and last valid value. Each hour without a valid value
(missing, suspect or absent) belongs to a gap, and the gap's length picks the method:

* up to ``max_gap_hours``: time interpolation between the station's own values around the gap;
* longer: the best correlated nearby series of the same metric (another station or a model point), shifted by its
  bias calibrated per hour of the day on the hours both series share. For the metrics with a backtest (PM and the
  CAMS model) it is the nearby series that best fills gaps cut from the station's history, if it beats a line;
* longer and without such a support: the station's own weekly profile (the median of each local hour on weekdays
  and on weekends), moved to the level of the values around the gap.

Hours with no possible correction (a long gap without a usable support or profile) stay uncorrected. Every
correction carries a confidence between 0 and 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from core.models import Quality

if TYPE_CHECKING:
    from collections.abc import Sequence

INTERPOLATION = "interpolation"
SUPPORT = "support"
PROFILE = "profile"
METHODS = (INTERPOLATION, SUPPORT, PROFILE)
ABSENT = "absent"  # original_quality of an hour without a row in silver.observations
LOCAL_TZ = "Europe/Madrid"  # traffic follows the clock of the island, summer time included

CORRECTION_COLUMNS = (
    "ts",
    "original_value",
    "original_quality",
    "corrected_value",
    "method",
    "support_source",
    "support_entity",
    "bias",
    "confidence",
)
_HOUR = pd.Timedelta(hours=1)
_SATURDAY = 5  # pandas numbers the days of the week from Monday = 0


@dataclass(frozen=True)
class InterpolationParams:
    """``interpolation`` block of ``config/corrections.yaml``."""

    max_gap_hours: int
    confidence_scale_hours: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterpolationParams:
        """Build from the parsed YAML block."""
        return cls(int(data["max_gap_hours"]), float(data["confidence_scale_hours"]))

    def confidence(self, gap_hours: pd.Series) -> pd.Series:
        """Shorter gaps, more confidence."""
        return np.exp(-gap_hours / self.confidence_scale_hours)


@dataclass(frozen=True)
class SupportParams:
    """``support`` block of ``config/corrections.yaml``."""

    max_distance_km: float
    min_correlation: float
    min_pairs: int
    min_hour_pairs: int
    distance_scale_km: float
    gap_scale_hours: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SupportParams:
        """Build from the parsed YAML block."""
        return cls(**{name: data[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class BacktestParams:
    """``support.backtest`` block of ``config/corrections.yaml``."""

    metrics: frozenset[str]  # where the support is chosen by its backtest instead of its correlation
    gap_hours: int
    min_gaps: int
    min_gap_hours: int  # shorter gaps are not filled by such a support: a straight line errs less there

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestParams:
        """Build from the parsed YAML block."""
        return cls(
            frozenset(data["metrics"]), int(data["gap_hours"]), int(data["min_gaps"]), int(data["min_gap_hours"])
        )


@dataclass(frozen=True)
class ProfileParams:
    """``profile`` block of ``config/corrections.yaml``."""

    metrics: frozenset[str]  # the profile beats a straight line only where the clock drives the series (traffic)
    min_days: int
    min_correlation: float
    gap_scale_hours: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileParams:
        """Build from the parsed YAML block."""
        return cls(
            frozenset(data["metrics"]),
            int(data["min_days"]),
            float(data["min_correlation"]),
            float(data["gap_scale_hours"]),
        )


def _slots(ts: pd.DatetimeIndex) -> pd.MultiIndex:
    """(weekend, local hour) of every timestamp."""
    local = ts.tz_convert(LOCAL_TZ)
    return pd.MultiIndex.from_arrays([local.dayofweek >= _SATURDAY, local.hour], names=["weekend", "hour"])


@dataclass(frozen=True)
class Profile:
    """The usual value of a station at each local hour of a weekday and of a weekend day."""

    by_slot: pd.Series  # median indexed by (weekend, hour)
    correlation: float  # Pearson r of the station's valid values and the profile at their hours

    def expected(self, ts: pd.DatetimeIndex) -> pd.Series:
        """The profile at ``ts`` (NaN at a slot without values)."""
        return pd.Series(self.by_slot.reindex(_slots(ts)).to_numpy(), index=ts)

    def confidence(self, gap_hours: pd.Series, params: ProfileParams) -> pd.Series:
        """How much of the series the profile explains (r squared), discounted by the length of the gap."""
        return self.correlation**2 * np.exp(-gap_hours / params.gap_scale_hours)


def weekly_profile(valid: pd.Series, params: ProfileParams) -> Profile | None:
    """The station's profile over its valid values, or None with fewer than ``min_days`` days of them."""
    if valid.empty or valid.index.tz_convert(LOCAL_TZ).normalize().nunique() < params.min_days:
        return None
    slots = _slots(pd.DatetimeIndex(valid.index))
    by_slot = valid.groupby(slots).median()
    expected = by_slot.reindex(slots).to_numpy()
    if valid.std() == 0 or np.std(expected) == 0:
        return None
    return Profile(by_slot, float(np.corrcoef(valid.to_numpy(), expected)[0, 1]))


@dataclass(frozen=True)
class Candidate:
    """A series that may stand in for the station: same metric, another location."""

    source: str
    entity: str
    distance_km: float
    history: pd.Series  # valid values indexed by ts (UTC)


@dataclass(frozen=True)
class Backtest:
    """How a support would have filled gaps cut from the station's own history, and how a straight line would."""

    gaps: int
    mae: float
    line_mae: float


@dataclass(frozen=True)
class Calibration:
    """How a candidate relates to the station over the hours both have a valid value."""

    candidate: Candidate
    pairs: int
    correlation: float
    bias_by_hour: pd.Series  # station minus candidate, indexed by the UTC hour 0-23
    backtest: Backtest | None = None  # only for the metrics whose support is chosen by its backtest

    def corrected(self, ts: pd.DatetimeIndex) -> pd.Series:
        """The candidate's values at ``ts`` shifted by the bias of their hour (NaN where it has none)."""
        bias = self.bias_by_hour.reindex(ts.hour).to_numpy()
        return pd.Series(self.candidate.history.reindex(ts).to_numpy() + bias, index=ts)

    def confidence(self, gap_hours: pd.Series, params: SupportParams) -> pd.Series:
        """Correlation squared, discounted by distance and by the length of the gap."""
        distance = math.exp(-self.candidate.distance_km / params.distance_scale_km)
        return self.correlation**2 * distance * np.exp(-gap_hours / params.gap_scale_hours)


def _only_where(mask: np.ndarray, value: object) -> np.ndarray:
    """``value`` where ``mask`` holds and None elsewhere, in an object array (None, not NaN, is a NULL in Postgres)."""
    out = np.full(len(mask), None, dtype=object)
    out[mask] = value
    return out


def calibrate(station: pd.Series, candidate: Candidate, params: SupportParams) -> Calibration | None:
    """Correlation and bias per hour of the day over the shared hours, or None if there are too few of them."""
    pairs = pd.concat({"station": station, "support": candidate.history}, axis=1, sort=True).dropna()
    if len(pairs) < params.min_pairs or pairs["station"].std() == 0 or pairs["support"].std() == 0:
        return None
    diff = pairs["station"] - pairs["support"]
    by_hour = diff.groupby(pairs.index.hour).agg(["median", "size"])
    overall = float(diff.median())
    bias = by_hour["median"].where(by_hour["size"] >= params.min_hour_pairs).reindex(range(24)).fillna(overall)
    return Calibration(candidate, len(pairs), float(pairs["station"].corr(pairs["support"])), bias)


def backtest_support(station: pd.Series, calibration: Calibration, params: BacktestParams) -> Backtest | None:
    """Fill runs of ``gap_hours`` valid hours of the station with the support and with a straight line, and compare.

    The runs follow one another without overlapping, each between two valid hours, and the support fills them with
    its bias calibrated on the same history. None with fewer than ``min_gaps`` runs that both can fill.
    """
    grid = pd.date_range(station.index.min(), station.index.max(), freq=_HOUR)
    values = station.reindex(grid).to_numpy()
    support = calibration.corrected(grid).to_numpy()
    n = params.gap_hours
    steps = np.arange(1, n + 1) / (n + 1)
    support_errors, line_errors = [], []
    for first in range(1, len(grid) - n, n + 1):  # the hour after a run is the hour before the next one
        truth, filled = values[first : first + n], support[first : first + n]
        before, after = values[first - 1], values[first + n]
        if np.isnan(before) or np.isnan(after) or np.isnan(truth).any() or np.isnan(filled).any():
            continue
        support_errors.append(np.abs(filled - truth).mean())
        line_errors.append(np.abs(before + (after - before) * steps - truth).mean())
    if len(support_errors) < params.min_gaps:
        return None
    return Backtest(len(support_errors), float(np.mean(support_errors)), float(np.mean(line_errors)))


def best_support(
    station: pd.Series,
    candidates: Sequence[Candidate],
    params: SupportParams,
    backtest: BacktestParams | None = None,
) -> Calibration | None:
    """The calibrated candidate with the highest correlation, if it reaches ``min_correlation``.

    Without such a candidate and with ``backtest``, the candidate whose backtest errs least, if it errs less than a
    straight line. That is a support that follows the days of the station but not its hourly noise, as the CAMS model
    follows the PM of a station.
    """
    calibrations = [c for c in (calibrate(station, candidate, params) for candidate in candidates) if c is not None]
    correlated = [c for c in calibrations if c.correlation >= params.min_correlation]
    if correlated or backtest is None:
        return max(correlated, key=lambda c: c.correlation, default=None)
    tested = [replace(c, backtest=backtest_support(station, c, backtest)) for c in calibrations]
    better = [c for c in tested if c.backtest is not None and c.backtest.mae < c.backtest.line_mae]
    return min(better, key=lambda c: c.backtest.mae if c.backtest else math.inf, default=None)


def correct_series(  # noqa: PLR0913 - keyword-only: the window and the parameters of each method
    observations: pd.DataFrame,
    candidates: Sequence[Candidate],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interpolation: InterpolationParams,
    support: SupportParams,
    profile: ProfileParams | None = None,
    backtest: BacktestParams | None = None,
) -> tuple[pd.DataFrame, Calibration | None]:
    """Correct the hours of one series in ``[start, end)``.

    Args:
        observations: every row of the series in the read range, columns ``ts`` (UTC), ``value``, ``quality``.
        candidates: series of the same metric within ``max_distance_km``, with their valid values.
        start: first hour to correct; earlier rows are calibration history.
        end: end of the window (exclusive).
        interpolation: parameters of method 1.
        support: parameters of method 2.
        profile: parameters of method 3 (None: long gaps without a support stay uncorrected).
        backtest: choose the support of method 2 by its backtest instead of its correlation (None: by correlation).

    Returns:
        ``CORRECTION_COLUMNS``, one row per corrected hour, and the support used (None when there was none).
    """
    rows = observations.set_index("ts").sort_index()
    valid = rows["value"].where(rows["quality"].eq(Quality.OK)).dropna()
    if len(valid) < 2:  # noqa: PLR2004 - a gap needs a valid value on each side
        return pd.DataFrame(columns=list(CORRECTION_COLUMNS)), None

    grid = pd.date_range(valid.index.min(), valid.index.max(), freq=_HOUR)
    values = valid.reindex(grid)
    gap = values.isna()
    run = gap.ne(gap.shift()).cumsum()
    gap_hours = run.map(run[gap].value_counts()).where(gap)

    calibration = best_support(valid, candidates, support, backtest)
    interpolated = values.interpolate(method="time", limit_area="inside")
    short = gap & gap_hours.le(interpolation.max_gap_hours)
    corrected = interpolated.where(short)
    method = pd.Series(_only_where(short.to_numpy(dtype=bool), INTERPOLATION), index=grid, dtype=object)
    confidence = interpolation.confidence(gap_hours).where(short)
    if calibration is not None:
        substituted = calibration.corrected(grid)
        long = gap & ~short & substituted.notna()
        if backtest is not None and calibration.backtest is not None:
            long &= gap_hours.ge(backtest.min_gap_hours)
        corrected = corrected.mask(long, substituted)
        method = method.mask(long, SUPPORT)
        confidence = confidence.mask(long, calibration.confidence(gap_hours, support))
    else:
        long = pd.Series(data=False, index=grid)
    usual = weekly_profile(valid, profile) if profile is not None else None
    if profile is not None and usual is not None and usual.correlation >= profile.min_correlation:
        expected = usual.expected(grid)
        # The profile moved to the level around the gap: the station's difference from it on each side, interpolated
        # across the gap, so a day with more traffic or a stagnant air mass keeps its level.
        level = (values - expected).interpolate(method="time", limit_area="inside")
        estimate = expected + level
        rest = gap & ~short & ~long & estimate.notna()
        corrected = corrected.mask(rest, estimate)
        method = method.mask(rest, PROFILE)
        confidence = confidence.mask(rest, usual.confidence(gap_hours, profile))

    keep = corrected.notna() & (grid >= start) & (grid < end)
    hours = grid[keep]
    by_support = long[keep].to_numpy(dtype=bool)
    source, entity = (calibration.candidate.source, calibration.candidate.entity) if calibration else (None, None)
    bias = calibration.bias_by_hour.reindex(hours.hour).to_numpy() if calibration else np.full(len(hours), np.nan)
    result = pd.DataFrame(
        {
            "ts": hours,
            "original_value": rows["value"].reindex(hours).to_numpy(),
            "original_quality": rows["quality"].reindex(hours).fillna(ABSENT).to_numpy(),
            "corrected_value": corrected[keep].round(3).to_numpy(),
            "method": method[keep].to_numpy(),
            "support_source": _only_where(by_support, source),
            "support_entity": _only_where(by_support, entity),
            "bias": np.where(by_support, np.round(bias, 3), np.nan),
            "confidence": confidence[keep].round(3).to_numpy(),
        }
    )
    return result[list(CORRECTION_COLUMNS)], calibration
