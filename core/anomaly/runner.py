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
from core.anomaly.zscore import RobustZScore
from core.config import Settings
from core.connectors import registry
from core.models import Quality, TimeWindow
from core.spark import build_spark
from core.warehouse import Warehouse

if TYPE_CHECKING:
    from pathlib import Path

    from core.anomaly.base import Detector

log = logging.getLogger(__name__)

DETECTORS: dict[str, type[Detector]] = {d.name: d for d in (RobustZScore, IsolationForestDetector)}

ENTITY_KEYS = ("source", "entity")
SERIES_KEYS = (*ENTITY_KEYS, "metric")
ANOMALY_COLUMNS = (*SERIES_KEYS, "ts", "detector", "value", "expected", "score", "threshold")
ANOMALY_SCHEMA = (
    "source string, entity string, metric string, ts timestamp, detector string,"
    " value double, expected double, score double, threshold double"
)
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
        skip = data.get("skip") or {}
        return cls(
            rescore_days=int(data["rescore_days"]),
            detectors={name: params or {} for name, params in data["detectors"].items()},
            skip_sources=frozenset(skip.get("sources") or ()),
            skip_metrics=frozenset(skip.get("metrics") or ()),
            evaluation=data.get("evaluation") or {},
        )

    def build(self) -> list[Detector]:
        """One configured instance per detector."""
        return [DETECTORS[name](**params) for name, params in self.detectors.items()]


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


def score_entity(observations: pd.DataFrame, detector: Detector, window: TimeWindow) -> pd.DataFrame:
    """Score every series of one entity and keep the anomalies inside ``window`` (earlier values are only context)."""
    observations = observations.assign(ts=pd.to_datetime(observations["ts"], utc=True))
    scored = detector.score_entity(observations[["metric", "ts", "value"]])
    in_window = scored["ts"].ge(pd.Timestamp(window.start_dt())) & scored["ts"].lt(
        pd.Timestamp(window.end_dt_exclusive())
    )
    flagged = scored[scored["is_anomaly"] & in_window]
    first = observations.iloc[0]
    return flagged.assign(**{k: first[k] for k in ENTITY_KEYS}, detector=detector.name)[list(ANOMALY_COLUMNS)]


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
    grouped = observations.groupBy(*ENTITY_KEYS)  # multivariate detectors see every metric of a location
    for detector in detectors:
        flagged = grouped.applyInPandas(partial(score_entity, detector=detector, window=window), ANOMALY_SCHEMA)
        # Anomalies are rare (a handful per series), so collecting them is cheap. Spark returns naive local
        # datetimes: going through the epoch makes them explicit UTC whatever the container's time zone.
        rows = [(*r[:3], datetime.fromtimestamp(r.ts.timestamp(), UTC), *r[4:]) for r in flagged.collect()]
        summary.anomalies[detector.name] = warehouse.replace_anomalies(detector.name, names, window, rows, run_id)
        log.info("run %s: %s flagged %s values", run_id, detector.name, summary.anomalies[detector.name])
    observations.unpersist()
    log.info("detection summary: %s", summary.as_dict())
    return summary
