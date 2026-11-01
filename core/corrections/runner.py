"""Correct the recent station series of silver.observations and store the result in silver.corrections."""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any

import pandas as pd
import yaml

from core.config import Settings
from core.corrections.methods import (
    CORRECTION_COLUMNS,
    Candidate,
    InterpolationParams,
    SupportParams,
    correct_series,
)
from core.models import Quality, TimeWindow
from core.warehouse import Warehouse

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

SERIES_KEYS = ("source", "entity", "metric")
OBSERVATION_COLUMNS = (*SERIES_KEYS, "ts", "value", "unit", "quality", "lat", "lon")
STORED_COLUMNS = (*SERIES_KEYS, "unit", *CORRECTION_COLUMNS)
_EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class CorrectionConfig:
    """``config/corrections.yaml``."""

    window_days: int
    calibration_days: int
    targets: dict[str, tuple[str, ...]]  # corrected source -> sources that may support it
    interpolation: InterpolationParams
    support: SupportParams
    evaluation: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> CorrectionConfig:
        """Read the YAML file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            window_days=int(data["window_days"]),
            calibration_days=int(data["calibration_days"]),
            targets={source: tuple(spec["supports"]) for source, spec in data["targets"].items()},
            interpolation=InterpolationParams.from_dict(data["interpolation"]),
            support=SupportParams.from_dict(data["support"]),
            evaluation=data.get("evaluation") or {},
        )

    def only(self, sources: list[str]) -> CorrectionConfig:
        """The same configuration correcting only these targets (their supports are still read)."""
        return replace(self, targets={s: self.targets[s] for s in sources})

    def read_sources(self) -> list[str]:
        """The corrected sources and their supports."""
        return sorted(set(self.targets) | {s for supports in self.targets.values() for s in supports})


@dataclass
class CorrectionSummary:
    """Outcome of one correction run, returned to Airflow as XCom."""

    run_id: str
    window_start: str
    window_end: str
    sources: list[str]
    series: int = 0
    corrections: dict[str, int] = field(default_factory=dict)  # per method
    supports: dict[str, str] = field(default_factory=dict)  # "source/entity/metric" -> "source/entity r=0.93"

    def as_dict(self) -> dict[str, Any]:
        """Plain dict (JSON-serialisable)."""
        return asdict(self)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, the same formula as the dbt macro ``haversine_km``."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class Neighbours:
    """Locations and valid series of every source read, to find the candidates that may support a station."""

    def __init__(self, observations: pd.DataFrame, config: CorrectionConfig) -> None:
        self.config = config
        located = observations.dropna(subset=["lat", "lon"])
        self.locations = located.groupby(["source", "entity"])[["lat", "lon"]].last()
        valid = observations[observations["quality"].eq(Quality.OK) & observations["value"].notna()]
        self.series = {key: s.set_index("ts")["value"].sort_index() for key, s in valid.groupby(list(SERIES_KEYS))}

    def candidates(self, source: str, entity: str, metric: str) -> list[Candidate]:
        """Series of the same metric at another location of a support source, within ``max_distance_km``."""
        if (source, entity) not in self.locations.index:
            return []
        here = self.locations.loc[(source, entity)]
        candidates = []
        for (other_source, other_entity, other_metric), values in self.series.items():
            other = (other_source, other_entity)
            if other_metric != metric or other_source not in self.config.targets[source]:
                continue
            if other == (source, entity) or other not in self.locations.index:
                continue
            there = self.locations.loc[other]
            distance = haversine_km(here["lat"], here["lon"], there["lat"], there["lon"])
            if distance <= self.config.support.max_distance_km:
                candidates.append(Candidate(other_source, other_entity, round(distance, 1), values))
        return candidates


def with_utc(observations: pd.DataFrame) -> pd.DataFrame:
    """Timestamps as UTC pandas datetimes."""
    return observations.assign(ts=pd.to_datetime(observations["ts"], utc=True))


def correct_all(
    observations: pd.DataFrame, config: CorrectionConfig, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Correct every target series in ``[start, end)``.

    Args:
        observations: ``OBSERVATION_COLUMNS`` of the target and support sources, calibration history included.
        config: what to correct and how.
        start: first hour to correct.
        end: end of the window (exclusive).

    Returns:
        ``STORED_COLUMNS``, one row per corrected hour, and the support chosen for each series that has one.
    """
    observations = with_utc(observations)
    neighbours = Neighbours(observations, config)
    parts = []
    supports = {}
    for (source, entity, metric), series in observations.groupby(list(SERIES_KEYS)):
        if source not in config.targets:
            continue
        corrected, calibration = correct_series(
            series[["ts", "value", "quality"]],
            neighbours.candidates(source, entity, metric),
            start=start,
            end=end,
            interpolation=config.interpolation,
            support=config.support,
        )
        if calibration is not None:
            c = calibration.candidate
            supports[f"{source}/{entity}/{metric}"] = f"{c.source}/{c.entity} r={calibration.correlation:.2f}"
        if not corrected.empty:
            unit = series["unit"].iloc[-1]
            parts.append(corrected.assign(source=source, entity=entity, metric=metric, unit=unit))
    if not parts:
        return pd.DataFrame(columns=list(STORED_COLUMNS)), supports
    return pd.concat(parts, ignore_index=True)[list(STORED_COLUMNS)], supports


def load_observations(
    settings: Settings, sources: list[str], read_from: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Every row of these sources between ``read_from`` and ``end``, as a pandas DataFrame."""
    with Warehouse(settings).connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {", ".join(OBSERVATION_COLUMNS)} FROM silver.observations
             WHERE source = ANY(%s) AND ts >= %s AND ts < %s
            """,  # noqa: S608 - the column names are constants
            (sources, read_from.to_pydatetime(), end.to_pydatetime()),
        ).fetchall()
    return pd.DataFrame(rows, columns=list(OBSERVATION_COLUMNS))


def correct_values(
    days: int,
    *,
    sources: list[str] | None = None,
    run_id: str,
    settings: Settings | None = None,
) -> CorrectionSummary:
    """Recompute the corrections of the last ``max(days, window_days)`` days and replace the stored ones.

    Args:
        days: days of the run (at least ``window_days`` are corrected).
        sources: sources of this run; only the configured targets among them are corrected (default: all).
        run_id: stored with every correction.
        settings: warehouse and config location (default: from the environment).
    """
    settings = settings or Settings.from_env()
    config = CorrectionConfig.load(settings.corrections_config)
    targets = sorted(set(sources or config.targets) & set(config.targets))
    window = TimeWindow.last_days(max(days, config.window_days))
    summary = CorrectionSummary(run_id, window.start.isoformat(), window.end.isoformat(), targets)
    if not targets:
        return summary

    config = config.only(targets)
    start, end = pd.Timestamp(window.start_dt()), pd.Timestamp(window.end_dt_exclusive())
    read_from = start - pd.Timedelta(days=config.calibration_days)
    observations = load_observations(settings, config.read_sources(), read_from, end)
    corrections, summary.supports = correct_all(observations, config, start, end)
    summary.series = int(observations[observations["source"].isin(targets)].groupby(list(SERIES_KEYS)).ngroups)
    summary.corrections = dict(Counter(corrections["method"]))

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    # psycopg gets plain Python values: datetimes, not pandas Timestamps, and None for NaN.
    rows = [
        tuple(v.to_pydatetime() if isinstance(v, pd.Timestamp) else None if pd.isna(v) else v for v in row)
        for row in corrections.itertuples(index=False)
    ]
    warehouse.replace_corrections(targets, window, rows, run_id)
    log.info("correction summary: %s", summary.as_dict())
    return summary
