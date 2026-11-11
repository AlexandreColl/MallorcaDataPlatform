"""Connector contract, registry and HTTP client shared by every data source."""

from core.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    ConnectorError,
    MetricSpec,
    SourceNotUpdatedError,
    failure_action,
    is_outage,
    is_permanent,
)

__all__ = [
    "BaseConnector",
    "ConnectorConfig",
    "ConnectorError",
    "MetricSpec",
    "SourceNotUpdatedError",
    "failure_action",
    "is_outage",
    "is_permanent",
]
