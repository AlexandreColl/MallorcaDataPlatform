"""The live poller: keeps the current state of the live sources in bronze, every few minutes (ADR 0026).

It is the only part of the platform that calls a live source, and it stays light on purpose: plain HTTP and S3 calls,
no Spark and no warehouse, so running it every five minutes costs a few seconds and some tens of megabytes. Each
answer is stored untouched as a snapshot under a key named after the source's own timestamp; the daily run of the
connector reads them back (``core.connectors.live``). Polls are not recorded in ``ops.ingestion_runs``: 288 rows a day
would bury the daily runs, and a missed poll shows up where it matters, as a gap in the hourly series.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.config import Settings, load_region
from core.connectors import ConnectorError, registry
from core.connectors.live import LiveConnector

if TYPE_CHECKING:
    from pathlib import Path

    from core.connectors.http import JsonGetter
    from core.connectors.live import SnapshotStore

log = logging.getLogger(__name__)


@dataclass
class PollSummary:
    """What one poll kept: the bronze key of each dataset that was due, and the ones that were not."""

    source: str
    kept: dict[str, str] = field(default_factory=dict)
    not_due: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Plain dict (JSON-serialisable), the task's XCom."""
        return asdict(self)


def live_names(connectors_dir: Path | None = None) -> list[str]:
    """Enabled connectors with a polled dataset, the ones the live poller runs."""
    return [n for n, cfg in registry.discover(connectors_dir).items() if cfg.enabled and cfg.is_live]


def poll_period(connectors_dir: Path | None = None) -> timedelta | None:
    """The shortest ``poll_every`` of the live connectors: how often the poller has to run (None without any)."""
    configs = registry.discover(connectors_dir)
    periods = [
        every
        for name in live_names(connectors_dir)
        for dataset in configs[name].datasets
        if (every := configs[name].poll_every(dataset)) is not None
    ]
    return min(periods, default=None)


def poll_connector(  # noqa: PLR0913 - keyword-only: where to poll, and the fakes of the tests
    name: str,
    *,
    region_name: str = "mallorca",
    settings: Settings | None = None,
    store: SnapshotStore | None = None,
    http: JsonGetter | None = None,
    now: datetime | None = None,
) -> PollSummary:
    """Ask a live source for the datasets that are due and keep each answer in bronze (or ``store``).

    Raises:
        ConnectorError: if the connector is not a live one.
    """
    settings = settings or Settings.from_env()
    connector = registry.load(name, http=http, connectors_dir=settings.connectors_dir)
    if not isinstance(connector, LiveConnector):
        msg = f"connector '{name}' has no polled dataset (poll_every)"
        raise ConnectorError(msg)
    if store is None:
        from core.storage import BronzeStore  # noqa: PLC0415 - boto3 only when polling for real

        bronze = BronzeStore(settings)
        bronze.ensure()
        store = bronze
    connector.store = store
    region = load_region(region_name, settings.regions_dir)
    now = now or datetime.now(UTC)
    summary = PollSummary(source=name)
    for dataset in connector.polled_datasets():
        if not connector.is_due(dataset, now):
            summary.not_due.append(dataset)
            continue
        payload = connector.poll(dataset, region)
        summary.kept[dataset] = store.put(payload, key=connector.snapshot_key(payload))
    log.info("poll %s: kept %s, not due %s", name, sorted(summary.kept), summary.not_due)
    return summary
