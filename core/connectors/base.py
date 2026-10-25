"""The connector contract.

A connector lives in ``connectors/<name>/`` and consists of:

* ``connector.yaml``  - declarative config (datasets, metrics, units, valid ranges).
* ``extractor.py``    - a ``BaseConnector`` subclass implementing ``extract`` and ``normalize``.
* ``tests/``          - unit tests running against recorded API responses (``tests/fixtures``).

The core never knows anything source-specific: it only calls these two methods.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import yaml

from core.connectors.http import HttpClient, JsonGetter
from core.models import TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from core.models import Observation, RawPayload, Region


class ConnectorError(Exception):
    """Raised for invalid connector configuration or usage."""


@dataclass(frozen=True)
class MetricSpec:
    """A metric declared in ``connector.yaml``: dataset, canonical unit and valid range."""

    name: str
    dataset: str
    unit: str
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class ConnectorConfig:
    """Declarative part of a connector, loaded from ``connectors/<name>/connector.yaml``."""

    name: str
    description: str
    entrypoint: str
    enabled: bool = True
    frequency: str = "1h"
    max_days: int = 31
    # Longest window a run may grow to when it recovers days missed by failed runs (<= max_days).
    catch_up_days: int = 31
    # Days the source publishes late (AEMET daily values: ~3). Windows end that many days before yesterday.
    lag_days: int = 0
    secrets: tuple[str, ...] = ()
    datasets: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metrics: Mapping[str, MetricSpec] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> ConnectorConfig:
        """Parse and validate a ``connector.yaml``.

        Raises:
            ConnectorError: on missing keys, a name that does not match its folder, or
                metrics pointing to undeclared datasets.
        """
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            metrics = {
                name: MetricSpec(
                    name=name,
                    dataset=spec["dataset"],
                    unit=spec["unit"],
                    min=spec.get("min"),
                    max=spec.get("max"),
                )
                for name, spec in (data.get("metrics") or {}).items()
            }
            config = cls(
                name=data["name"],
                description=data.get("description", ""),
                entrypoint=data["entrypoint"],
                enabled=bool(data.get("enabled", True)),
                frequency=str(data.get("frequency", "1h")),
                max_days=int(data.get("max_days", 31)),
                catch_up_days=int(data.get("catch_up_days", data.get("max_days", 31))),
                lag_days=int(data.get("lag_days", 0)),
                secrets=tuple(data.get("secrets") or ()),
                datasets=data.get("datasets") or {},
                metrics=metrics,
                options=data.get("options") or {},
            )
        except KeyError as exc:
            msg = f"{path}: missing required key {exc}"
            raise ConnectorError(msg) from exc
        if config.name != path.parent.name:
            msg = f"{path}: name '{config.name}' must match folder '{path.parent.name}'"
            raise ConnectorError(msg)
        unknown = {m.dataset for m in metrics.values()} - set(config.datasets)
        if unknown:
            msg = f"{path}: metrics reference unknown datasets {sorted(unknown)}"
            raise ConnectorError(msg)
        if not 1 <= config.catch_up_days <= config.max_days:
            msg = f"{path}: catch_up_days must be between 1 and max_days ({config.max_days})"
            raise ConnectorError(msg)
        for dataset in config.datasets:
            config.frequency_for(dataset)  # fail fast on an invalid frequency
        return config

    def window(self, days: int, today: date | None = None) -> TimeWindow:
        """Last ``days`` complete days the source has already published (shifted back by ``lag_days``)."""
        today = today or datetime.now(UTC).date()
        return TimeWindow.last_days(days, today - timedelta(days=self.lag_days))

    @property
    def frequency_delta(self) -> timedelta:
        """Default spacing between samples (datasets may override it)."""
        return parse_frequency(self.frequency)

    def frequency_for(self, dataset: str) -> timedelta | None:
        """Spacing between samples of one dataset: its own ``frequency`` or the connector default.

        ``None`` for event datasets (``frequency: event``), which have no regular spacing.
        """
        spec = self.datasets.get(dataset) or {}
        freq = str(spec.get("frequency", self.frequency))
        return None if freq == EVENT_FREQUENCY else parse_frequency(freq)

    @property
    def is_event_source(self) -> bool:
        """True when every dataset holds irregular events: a window without events is a valid, empty result."""
        return bool(self.datasets) and all(self.frequency_for(d) is None for d in self.datasets)

    def metrics_for(self, dataset: str) -> list[MetricSpec]:
        """Metrics that belong to one dataset, in YAML order."""
        return [m for m in self.metrics.values() if m.dataset == dataset]


# Dataset frequency of irregular sources (earthquakes...): no gaps rule, empty windows are allowed.
EVENT_FREQUENCY = "event"


def parse_frequency(freq: str) -> timedelta:
    """Parse ``15m``, ``1h`` or ``1d`` into a timedelta.

    Raises:
        ConnectorError: for any other format.
    """
    units = {"m": "minutes", "h": "hours", "d": "days"}
    value, unit = freq[:-1], freq[-1]
    if unit not in units or not value.isdigit():
        msg = f"invalid frequency '{freq}', expected e.g. 15m, 1h, 1d"
        raise ConnectorError(msg)
    return timedelta(**{units[unit]: int(value)})


class BaseConnector(ABC):
    """Base class every connector extends."""

    def __init__(
        self,
        config: ConnectorConfig,
        http: JsonGetter | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.http = http or HttpClient()
        self.secrets = dict(secrets) if secrets is not None else self._secrets_from_env()

    @property
    def name(self) -> str:
        """Connector name (same as its folder)."""
        return self.config.name

    def _secrets_from_env(self) -> dict[str, str]:
        missing = [s for s in self.config.secrets if not os.environ.get(s)]
        if missing:
            msg = f"connector '{self.name}' needs secrets {missing}; add them to your .env file"
            raise ConnectorError(msg)
        return {s: os.environ[s] for s in self.config.secrets}

    def validate_window(self, window: TimeWindow) -> None:
        """Reject windows longer than the source allows.

        Raises:
            ConnectorError: if the window exceeds ``max_days``.
        """
        if window.n_days > self.config.max_days:
            msg = f"connector '{self.name}' supports at most {self.config.max_days} days, got {window.n_days}"
            raise ConnectorError(msg)

    @abstractmethod
    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Call the source API and return the raw responses, untouched."""

    @abstractmethod
    def normalize(self, payload: RawPayload, region: Region) -> Iterable[Observation]:
        """Turn one raw payload into observations in the common silver schema."""
