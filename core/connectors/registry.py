"""Discovers connectors by scanning ``connectors/*/connector.yaml``."""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

from core.config import PROJECT_ROOT
from core.connectors.base import BaseConnector, ConnectorConfig, ConnectorError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from core.connectors.http import JsonGetter


def discover(connectors_dir: Path | None = None) -> dict[str, ConnectorConfig]:
    """Load the config of every connector folder, keyed by name."""
    connectors_dir = connectors_dir or PROJECT_ROOT / "connectors"
    configs: dict[str, ConnectorConfig] = {}
    for path in sorted(connectors_dir.glob("*/connector.yaml")):
        config = ConnectorConfig.from_yaml(path)
        configs[config.name] = config
    return configs


def enabled_names(connectors_dir: Path | None = None) -> list[str]:
    """Names of the connectors with ``enabled: true``."""
    return [name for name, cfg in discover(connectors_dir).items() if cfg.enabled]


def runnable_names(connectors_dir: Path | None = None, env: Mapping[str, str] | None = None) -> list[str]:
    """Enabled connectors whose secrets are set: the default selection.

    A connector without its API key is left out of a default run instead of failing it; asking for it
    explicitly still fails fast with the missing variable.
    """
    env = os.environ if env is None else env
    return [n for n, cfg in discover(connectors_dir).items() if cfg.enabled and all(env.get(s) for s in cfg.secrets)]


def load(
    name: str,
    *,
    http: JsonGetter | None = None,
    connectors_dir: Path | None = None,
    secrets: dict[str, str] | None = None,
) -> BaseConnector:
    """Instantiate a connector from its ``entrypoint``.

    Raises:
        ConnectorError: if the connector is unknown or its class does not extend BaseConnector.
    """
    configs = discover(connectors_dir)
    if name not in configs:
        msg = f"unknown connector '{name}'. Available: {sorted(configs)}"
        raise ConnectorError(msg)
    config = configs[name]
    module_name, _, class_name = config.entrypoint.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    if not issubclass(cls, BaseConnector):
        msg = f"{config.entrypoint} is not a BaseConnector subclass"
        raise ConnectorError(msg)
    return cls(config, http=http, secrets=secrets)
