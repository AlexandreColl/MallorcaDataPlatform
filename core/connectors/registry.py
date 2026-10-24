"""Discovers connectors by scanning ``connectors/*/connector.yaml``."""

from __future__ import annotations

import importlib
from pathlib import Path

from core.config import PROJECT_ROOT
from core.connectors.base import BaseConnector, ConnectorConfig, ConnectorError
from core.connectors.http import JsonGetter


def discover(connectors_dir: Path | None = None) -> dict[str, ConnectorConfig]:
    connectors_dir = connectors_dir or PROJECT_ROOT / "connectors"
    configs: dict[str, ConnectorConfig] = {}
    for path in sorted(connectors_dir.glob("*/connector.yaml")):
        config = ConnectorConfig.from_yaml(path)
        configs[config.name] = config
    return configs


def enabled_names(connectors_dir: Path | None = None) -> list[str]:
    return [name for name, cfg in discover(connectors_dir).items() if cfg.enabled]


def load(
    name: str,
    http: JsonGetter | None = None,
    connectors_dir: Path | None = None,
    secrets: dict[str, str] | None = None,
) -> BaseConnector:
    configs = discover(connectors_dir)
    if name not in configs:
        raise ConnectorError(f"unknown connector '{name}'. Available: {sorted(configs)}")
    config = configs[name]
    module_name, _, class_name = config.entrypoint.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    if not issubclass(cls, BaseConnector):
        raise ConnectorError(f"{config.entrypoint} is not a BaseConnector subclass")
    return cls(config, http=http, secrets=secrets)
