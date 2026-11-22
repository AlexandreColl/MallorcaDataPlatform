"""Run the detectors over silver.observations and store the flagged values in silver.anomalies."""

from __future__ import annotations

import logging
import os
import warnings
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any

import pandas as pd
import yaml

from core.anomaly.isolation_forest import IsolationForestDetector
from core.anomaly.seasonal import SeasonalResidual
from core.anomaly.vote import Vote
from core.anomaly.zscore import RobustZScore
from core.config import Settings
from core.connectors import registry
from core.models import Quality, TimeWindow
from core.spark import build_spark
from core.warehouse import Warehouse

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from core.anomaly.base import Detector

log = logging.getLogger(__name__)

DETECTORS: dict[str, type[Detector]] = {
    d.name: d for d in (RobustZScore, SeasonalResidual, IsolationForestDetector, Vote)
}
# Their names, in this order, are written in the API, Grafana and the web too: tests/test_names.py keeps them in step.
DETECTOR_NAMES = tuple(DETECTORS)

ENTITY_KEYS = ("source", "entity")
SERIES_KEYS = (*ENTITY_KEYS, "metric")
ANOMALY_COLUMNS = (*SERIES_KEYS, "ts", "detector", "value", "expected", "score", "threshold")
ANOMALY_SCHEMA = (
    "source string, entity string, metric string, ts timestamp, detector string,"
    " value double, expected double, score double, threshold double"
)
# Text as plain Python strings: pandas 3 backs its string columns with Arrow, and concatenating them leaves chunked
# arrays that PySpark cannot turn back into a record batch.
_ANOMALY_TYPES = {
    **dict.fromkeys(("source", "entity", "metric", "detector"), object),
    **dict.fromkeys(("value", "expected", "score", "threshold"), "float64"),
}
_PANDAS3_WARNING = "PySpark does not yet fully support pandas"


@dataclass(frozen=True)
class AnomalyConfig:
    """``config/anomaly.yaml``: detectors with their parameters and the series they skip."""

    rescore_days: int
    detectors: dict[str, dict[str, Any]]
    skip_sources: frozenset[str] = frozenset()
    skip_metrics: frozenset[str] = frozenset()
    evaluation: dict[str, Any] = field(default_factory=dict)  # fault-injection benchmark (core.anomaly.evaluation)

    @classmethod
    def load(cls, path: Path) -> AnomalyConfig:
        """Read and validate the YAML file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        unknown = sorted(set(data["detectors"]) - set(DETECTORS))
        if unknown:
            msg = f"unknown detectors {unknown} in {path}; available {sorted(DETECTORS)}"
            raise ValueError(msg)
        members = (data["detectors"].get(Vote.name) or {}).get("members") or []
        if Vote.name in members or set(members) - set(DETECTORS):
            msg = f"the members of {Vote.name} must be other detectors, not {members}"
            raise ValueError(msg)
        skip = data.get("skip") or {}
        return cls(
            rescore_days=int(data["rescore_days"]),
            detectors={name: params or {} for name, params in data["detectors"].items()},
            skip_sources=frozenset(skip.get("sources") or ()),
            skip_metrics=frozenset(skip.get("metrics") or ()),
            evaluation=data.get("evaluation") or {},
        )

    def build(self) -> list[Detector]:
        """One configured instance per detector, in the order of the file.

        A vote's members are the same instances as the detectors that also run on their own, so the runner scores
        each of them once (``score_entities``). A member with no entry of its own takes the defaults.
        """
        alone = {name: DETECTORS[name](**params) for name, params in self.detectors.items() if name != Vote.name}
        detectors: list[Detector] = []
        for name, params in self.detectors.items():
            if name == Vote.name:
                members = [alone.get(m) or DETECTORS[m]() for m in params["members"]]
                detectors.append(Vote(members, min_votes=int(params.get("min_votes", 1))))
            else:
                detectors.append(alone[name])
        return detectors


@dataclass
class DetectionSummary:
    """Outcome of one detection run, returned to Airflow as XCom."""

    run_id: str
    window_start: str
    window_end: str
    sources: list[str]
    values_scored: int
    anomalies: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Plain dict (JSON-serialisable)."""
        return asdict(self)


def score_entities(observations: pd.DataFrame, detectors: Sequence[Detector], window: TimeWindow) -> pd.DataFrame:
    """Score every series of one entity with every detector and keep the anomalies inside ``window``.

    Earlier values are only context. Each detector scores once: a vote counts what its members already flagged
    (``Vote.combine``) instead of scoring them again, which used to double the cost of the seasonal residual and
    the forest.
    """
    observations = observations.assign(ts=pd.to_datetime(observations["ts"], utc=True))
    values = observations[["metric", "ts", "value"]]
    scores: dict[int, pd.DataFrame] = {}  # by instance: build() shares the members with the detectors run alone

    def scored(detector: Detector) -> pd.DataFrame:
        if id(detector) not in scores:
            if isinstance(detector, Vote):
                scores[id(detector)] = detector.combine(values, [scored(member) for member in detector.members])
            else:
                scores[id(detector)] = detector.score_entity(values)
        return scores[id(detector)]

    start, end = pd.Timestamp(window.start_dt()), pd.Timestamp(window.end_dt_exclusive())
    first = observations.iloc[0]
    flagged = []
    for detector in detectors:
        frame = scored(detector)
        keep = frame["is_anomaly"] & frame["ts"].ge(start) & frame["ts"].lt(end)
        flagged.append(frame[keep].assign(**{k: first[k] for k in ENTITY_KEYS}, detector=detector.name))
    # A detector with nothing to flag may return untyped columns, which would turn `ts` and the numbers into objects:
    # empty parts are left out. The result gets the types Spark expects (_ANOMALY_TYPES).
    parts = [part for part in flagged if len(part)] or flagged[:1]
    result = pd.concat(parts, ignore_index=True)[list(ANOMALY_COLUMNS)]
    return result.astype(_ANOMALY_TYPES).assign(ts=pd.to_datetime(result["ts"], utc=True))


def score_entity(observations: pd.DataFrame, detector: Detector, window: TimeWindow) -> pd.DataFrame:
    """``score_entities`` with one detector."""
    return score_entities(observations, [detector], window)


def _quoted(values: list[str]) -> str:
    """SQL list of names already validated against the connector registry."""
    return ", ".join(f"'{v}'" for v in values)


def detect_anomalies(
    days: int,
    *,
    sources: list[str] | None = None,
    run_id: str,
    settings: Settings | None = None,
) -> DetectionSummary:
    """Score the last ``max(days, rescore_days)`` days of every series and replace their anomalies.

    Only values labelled ``ok`` by the quality rules are scored: ``suspect`` ones already failed a hard rule.
    """
    settings = settings or Settings.from_env()
    config = AnomalyConfig.load(settings.anomaly_config)
    known = registry.discover(settings.connectors_dir)
    unknown = sorted(set(sources or ()) - set(known))
    if unknown:
        msg = f"unknown sources {unknown}"
        raise ValueError(msg)
    names = sorted(set(sources or known) - config.skip_sources)
    window = TimeWindow.last_days(max(days, config.rescore_days))
    summary = DetectionSummary(run_id, window.start.isoformat(), window.end.isoformat(), names, values_scored=0)
    if not names:
        return summary

    detectors = config.build()
    context = max(d.context for d in detectors)
    read_from = pd.Timestamp(window.start_dt()) - context
    metrics_filter = f"AND metric NOT IN ({_quoted(sorted(config.skip_metrics))})" if config.skip_metrics else ""
    query = f"""
        SELECT source, entity, metric, ts, value FROM silver.observations
         WHERE quality = '{Quality.OK}' AND value IS NOT NULL
           AND source IN ({_quoted(names)}) {metrics_filter}
           AND ts >= '{read_from.isoformat()}' AND ts < '{window.end_dt_exclusive().isoformat()}'
    """  # noqa: S608 - every interpolated value comes from the registry, the config or the clock

    # Airflow 3.3's constraints pin pandas 3, which PySpark 4.2 has not certified yet and warns about in every
    # Python worker. applyInPandas is covered by the tests, so the warning is silenced in the driver and, through
    # the environment the JVM passes on, in the workers.
    warnings.filterwarnings("ignore", _PANDAS3_WARNING, FutureWarning)
    os.environ.setdefault("PYTHONWARNINGS", f"ignore:{_PANDAS3_WARNING}:FutureWarning")
    spark = build_spark(settings, app_name="mdp-anomalies")
    observations = (
        spark.read.format("jdbc")
        .option("url", settings.jdbc_url)
        .option("query", query)
        .option("user", settings.warehouse_user)
        .option("password", settings.warehouse_password)
        .option("driver", "org.postgresql.Driver")
        .load()
        .cache()
    )
    summary.values_scored = observations.count()

    warehouse = Warehouse(settings)
    warehouse.ensure_schema()
    # One pass over the entities scores every detector (multivariate ones see every metric of a location).
    grouped = observations.groupBy(*ENTITY_KEYS)
    flagged = grouped.applyInPandas(partial(score_entities, detectors=detectors, window=window), ANOMALY_SCHEMA)
    # Anomalies are rare (a handful per series), so collecting them is cheap. Spark returns naive local datetimes:
    # going through the epoch makes them explicit UTC whatever the container's time zone.
    by_detector: dict[str, list[tuple]] = {d.name: [] for d in detectors}
    for r in flagged.collect():
        by_detector[r.detector].append((*r[:3], datetime.fromtimestamp(r.ts.timestamp(), UTC), *r[4:]))
    for name, rows in by_detector.items():  # every detector, so one with no flags left clears its old ones
        summary.anomalies[name] = warehouse.replace_anomalies(name, names, window, rows, run_id)
        log.info("run %s: %s flagged %s values", run_id, name, summary.anomalies[name])
    observations.unpersist()
    log.info("detection summary: %s", summary.as_dict())
    return summary
