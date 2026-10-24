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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from core.connectors.http import HttpClient, JsonGetter
from core.models import Observation, RawPayload, Region, TimeWindow


class ConnectorError(Exception):
    """Raised for invalid connector configuration or usage."""


@dataclass(frozen=True)
class MetricSpec:
    name: str
    dataset: str
    unit: str
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class ConnectorConfig:
    name: str
    description: str
    entrypoint: str
    enabled: bool = True
    frequency: str = "1h"
    max_days: int = 31
    secrets: tuple[str, ...] = ()
    datasets: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    metrics: Mapping[str, MetricSpec] = field(default_factory=dict)
    options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> ConnectorConfig:
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
                secrets=tuple(data.get("secrets") or ()),
                datasets=data.get("datasets") or {},
                metrics=metrics,
                options=data.get("options") or {},
            )
        except KeyError as exc:
            raise ConnectorError(f"{path}: missing required key {exc}") from exc
        if config.name != path.parent.name:
            raise ConnectorError(
                f"{path}: name '{config.name}' must match folder '{path.parent.name}'"
            )
        unknown = {m.dataset for m in metrics.values()} - set(config.datasets)
        if unknown:
            raise ConnectorError(f"{path}: metrics reference unknown datasets {sorted(unknown)}")
        return config

    @property
    def frequency_delta(self) -> timedelta:
        return parse_frequency(self.frequency)

    def metrics_for(self, dataset: str) -> list[MetricSpec]:
        return [m for m in self.metrics.values() if m.dataset == dataset]


def parse_frequency(freq: str) -> timedelta:
    units = {"m": "minutes", "h": "hours", "d": "days"}
    value, unit = freq[:-1], freq[-1]
    if unit not in units or not value.isdigit():
        raise ConnectorError(f"invalid frequency '{freq}', expected e.g. 15m, 1h, 1d")
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
        return self.config.name

    def _secrets_from_env(self) -> dict[str, str]:
        missing = [s for s in self.config.secrets if not os.environ.get(s)]
        if missing:
            raise ConnectorError(
                f"connector '{self.name}' needs secrets {missing}; add them to your .env file"
            )
        return {s: os.environ[s] for s in self.config.secrets}

    def validate_window(self, window: TimeWindow) -> None:
        if window.n_days > self.config.max_days:
            raise ConnectorError(
                f"connector '{self.name}' supports at most {self.config.max_days} days, "
                f"got {window.n_days}"
            )

    @abstractmethod
    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Call the source API and return the raw responses, untouched."""

    @abstractmethod
    def normalize(self, payload: RawPayload, region: Region) -> Iterable[Observation]:
        """Turn one raw payload into observations in the common silver schema."""
