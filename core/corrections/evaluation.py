"""Benchmark the corrections: hide clean station values in gaps of known length, correct them, compare.

Each target series gets ``gaps_per_series`` artificial gaps of every length in ``gap_hours``, placed at random on
clean hours of the window and surrounded by clean hours, so each is a gap of exactly that length. The hidden values
are the truth. Per source, metric and gap length the benchmark reports how many hidden hours were corrected, the
mean absolute error and, for the support method, the error the support would have without its calibrated bias.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from core.config import Settings
from core.corrections.methods import SUPPORT, correct_series
from core.corrections.runner import SERIES_KEYS, CorrectionConfig, Neighbours, load_observations, with_utc
from core.models import Quality, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger(__name__)

_HOUR = pd.Timedelta(hours=1)
_ATTEMPTS = 50  # random positions tried per gap before giving up (short or very gappy series)


def hide_gaps(
    series: pd.DataFrame,
    *,
    lengths: Sequence[int],
    per_length: int,
    window: tuple[pd.Timestamp, pd.Timestamp],
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mark random runs of clean hours of ``window`` (start, exclusive end) as missing.

    Returns:
        The series with the hidden values as ``missing`` and the hidden hours (``ts``, ``truth``, ``gap_hours``).
    """
    start, end = window
    clean = series.loc[series["quality"].eq(Quality.OK) & series["value"].notna()].set_index("ts")["value"]
    usable = clean.index[(clean.index >= start) & (clean.index < end)]
    hidden: dict[pd.Timestamp, int] = {}
    for length in lengths:
        for _ in range(per_length):
            for _ in range(_ATTEMPTS):
                first = usable[rng.integers(len(usable))] if len(usable) else None
                if first is None:
                    break
                hours = pd.date_range(
                    first - _HOUR, periods=length + 2, freq=_HOUR
                )  # the gap and a clean hour on each side
                if all(h in clean.index and h not in hidden for h in hours) and hours[-1] < end:
                    hidden.update(dict.fromkeys(hours[1:-1], length))
                    break
    truth = pd.DataFrame(
        {"ts": list(hidden), "truth": clean.reindex(list(hidden)).to_numpy(), "gap_hours": list(hidden.values())}
    )
    masked = series.assign(
        value=series["value"].mask(series["ts"].isin(hidden)),
        quality=series["quality"].mask(series["ts"].isin(hidden), Quality.MISSING),
    )
    return masked, truth


def evaluate(
    observations: pd.DataFrame, config: CorrectionConfig, start: pd.Timestamp, end: pd.Timestamp, seed: int
) -> pd.DataFrame:
    """One row per source, metric and gap length with the counts and errors described in the module docstring."""
    observations = with_utc(observations)
    neighbours = Neighbours(observations, config)
    lengths = [int(h) for h in config.evaluation["gap_hours"]]
    per_length = int(config.evaluation["gaps_per_series"])
    results = []
    for position, ((source, entity, metric), series) in enumerate(observations.groupby(list(SERIES_KEYS))):
        if source not in config.targets:
            continue
        rng = np.random.default_rng([seed, position])
        masked, truth = hide_gaps(
            series[["ts", "value", "quality"]], lengths=lengths, per_length=per_length, window=(start, end), rng=rng
        )
        if truth.empty:
            continue
        corrected, _ = correct_series(
            masked,
            neighbours.candidates(source, entity, metric),
            start=start,
            end=end,
            interpolation=config.interpolation,
            support=config.support,
        )
        compared = truth.merge(corrected[["ts", "corrected_value", "method", "bias"]], on="ts", how="left")
        results.append(compared.assign(source=source, metric=metric))
    if not results:
        return pd.DataFrame()
    compared = pd.concat(results, ignore_index=True)
    compared["error"] = (compared["corrected_value"] - compared["truth"]).abs()
    by_support = compared["method"].eq(SUPPORT)
    compared["error_without_bias"] = (
        (compared["corrected_value"] - compared["bias"] - compared["truth"]).abs().where(by_support)
    )
    return (
        compared.groupby(["source", "metric", "gap_hours"])
        .agg(
            hidden=("truth", "size"),
            corrected=("corrected_value", "count"),
            by_support=("method", lambda m: int(m.eq(SUPPORT).sum())),
            mae=("error", "mean"),
            mae_without_bias=("error_without_bias", "mean"),
        )
        .reset_index()
    )


def run_evaluation(
    *, days: int | None = None, seed: int | None = None, settings: Settings | None = None
) -> list[dict[str, Any]]:
    """Benchmark the corrections on the last ``days`` days of every target source."""
    settings = settings or Settings.from_env()
    config = CorrectionConfig.load(settings.corrections_config)
    window = TimeWindow.last_days(days or int(config.evaluation["days"]))
    start, end = pd.Timestamp(window.start_dt()), pd.Timestamp(window.end_dt_exclusive())
    read_from = start - pd.Timedelta(days=config.calibration_days)
    observations = load_observations(settings, config.read_sources(), read_from, end)
    if observations.empty:
        msg = f"no values of {sorted(config.targets)} in {window.start}..{window.end} to evaluate"
        raise ValueError(msg)
    result = evaluate(observations, config, start, end, int(config.evaluation["seed"] if seed is None else seed))
    log.info("evaluated %s hidden hours", int(result["hidden"].sum()) if not result.empty else 0)
    return result.round(3).to_dict("records")
