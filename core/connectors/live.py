"""Live sources: the ones that only publish their current state, with no history to ask for (ADR 0026).

A live connector has two halves that never meet the source at the same time:

* ``poll`` asks the source for the current state of one dataset. The live poller (``core/live.py``, run every few
  minutes by ``dags/live_poll.py`` without Spark) keeps each answer untouched in bronze, under a key named after the
  instant the source stamped on it (``snapshot_key``). Polling a feed that has not changed writes the same key again.
* ``extract`` never calls the source. It lists the snapshots of the window's days in bronze and returns their keys in
  one payload, the manifest. ``normalize`` reads those snapshots back and ``aggregate`` turns them into the regular
  series of the YAML (hourly means, minimums, maximums...).

The daily run therefore works like any other connector: windows, catch-up, only the missing days. Rebuilding silver
from bronze reads the same manifest and the same snapshots, which are never rewritten with other content. Two hooks
tell the core what a live source cannot have: no day before its first snapshot (``first_day``), and no gap before it
or after the window was read (``observed_span``).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from core.connectors.base import BaseConnector
from core.models import RawPayload

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    from core.connectors.base import ConnectorConfig
    from core.connectors.http import JsonGetter
    from core.models import Entity, Observation, Region, TimeWindow

# Bronze folder of the snapshots, <source>/snapshots/<dataset>/day=<day>/, and dataset of the manifest payload.
SNAPSHOTS = "snapshots"
MANIFEST = "manifest"
# File name of a snapshot: the instant the source stamped on it, in UTC.
_INSTANT = "%Y%m%dT%H%M%SZ"


class SnapshotStore(Protocol):
    """Where the snapshots live: bronze (``core.storage.BronzeStore``), or a fake in the tests."""

    def put(self, payload: RawPayload, key: str | None = None) -> str:
        """Store a payload under ``key`` and return it."""
        ...

    def get(self, key: str) -> RawPayload:
        """Read one payload back."""
        ...

    def keys(self, prefix: str) -> list[str]:
        """Every key under ``prefix``, in order."""
        ...

    def folders(self, prefix: str) -> list[str]:
        """The next level of ``prefix``, in order."""
        ...


def instant_of(key: str) -> datetime:
    """The instant in a snapshot key (``.../20261126T153721Z.json``)."""
    return datetime.strptime(key.rsplit("/", 1)[-1].removesuffix(".json"), _INSTANT).replace(tzinfo=UTC)


def floor_to(at: datetime, step: timedelta) -> datetime:
    """``at`` rounded down to a multiple of ``step`` since the epoch (15:37 to 15:00 for an hour)."""
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return epoch + step * math.floor((at - epoch) / step)


class LiveConnector(BaseConnector, ABC):
    """A source polled every few minutes whose series are built from the snapshots kept in bronze."""

    def __init__(
        self,
        config: ConnectorConfig,
        http: JsonGetter | None = None,
        secrets: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(config, http=http, secrets=secrets)
        self._store: SnapshotStore | None = None
        # The snapshots of the last manifest read: normalize and describe read the same payload one after the other.
        self._read: tuple[str, dict[str, list[RawPayload]]] | None = None

    @property
    def store(self) -> SnapshotStore:
        """Bronze, opened on first use (the tests set a fake instead)."""
        if self._store is None:
            from core.config import Settings  # noqa: PLC0415 - only when there is no store given: keeps tests offline
            from core.storage import BronzeStore  # noqa: PLC0415

            self._store = BronzeStore(Settings.from_env())
        return self._store

    @store.setter
    def store(self, store: SnapshotStore) -> None:
        self._store = store
        self._read = None

    # --- the poller's half --------------------------------------------------------------------------------------

    @abstractmethod
    def poll(self, dataset: str, region: Region) -> RawPayload:
        """The current state of one polled dataset, exactly as the source returns it."""

    @abstractmethod
    def instant(self, payload: RawPayload) -> datetime:
        """The instant a snapshot describes, as the source stamps it (not when it was fetched)."""

    def polled_datasets(self) -> list[str]:
        """The datasets with a ``poll_every``, in YAML order."""
        return [d for d in self.config.datasets if self.config.poll_every(d) is not None]

    def snapshot_prefix(self, dataset: str, day: date | None = None) -> str:
        """The bronze folder of a dataset's snapshots, or of one UTC day of them."""
        base = f"{self.name}/{SNAPSHOTS}/{dataset}/"
        return f"{base}day={day.isoformat()}/" if day else base

    def snapshot_key(self, payload: RawPayload) -> str:
        """Where a snapshot is kept: its dataset, its UTC day and its instant."""
        at = self.instant(payload).astimezone(UTC)
        return f"{self.snapshot_prefix(payload.dataset, at.date())}{at.strftime(_INSTANT)}.json"

    def is_due(self, dataset: str, now: datetime) -> bool:
        """True when no snapshot of ``dataset`` was kept since the start of its current ``poll_every`` period.

        A dataset that changes rarely (the list of stations) is polled once an hour while the status is every five
        minutes; a period that has a snapshot already is not asked for again.
        """
        every = self.config.poll_every(dataset)
        if every is None:
            return False
        start = floor_to(now, every)
        kept = self.store.keys(self.snapshot_prefix(dataset, start.date()))
        return not any(instant_of(k) >= start for k in kept)

    def first_snapshot(self) -> datetime | None:
        """The instant of the oldest snapshot kept of any polled dataset (None before the first poll)."""
        firsts = []
        for dataset in self.polled_datasets():
            days = self.store.folders(self.snapshot_prefix(dataset))
            keys = self.store.keys(days[0]) if days else []
            if keys:
                firsts.append(instant_of(keys[0]))
        return min(firsts, default=None)

    # --- the daily run's half -----------------------------------------------------------------------------------

    def first_day(self) -> date | None:
        """The UTC day of the first snapshot; ``date.max`` before the first poll, so every window is before it."""
        first = self.first_snapshot()
        return first.date() if first else date.max

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - see aggregate
        """The manifest of the window: the keys of its snapshots in bronze, without calling the source."""
        days = [window.start + timedelta(days=i) for i in range(window.n_days)]
        keys = {
            dataset: [key for day in days for key in self.store.keys(self.snapshot_prefix(dataset, day))]
            for dataset in self.polled_datasets()
        }
        first = self.first_snapshot()
        body = {"first_snapshot": first.isoformat() if first else None, SNAPSHOTS: keys}
        request = {"bronze_prefix": f"{self.name}/{SNAPSHOTS}/"}
        return [RawPayload(source=self.name, dataset=MANIFEST, window=window, request=request, body=body)]

    def observed_span(self, payload: RawPayload) -> tuple[datetime, datetime]:
        """From the first snapshot (or the window start) to when the manifest was read (or the window end).

        Both ends are rounded to the series' step: the hour the poller started in, or the one in progress when the
        window was read, counts as expected.
        """
        step = self.config.frequency_delta
        window = payload.window
        first = payload.body.get("first_snapshot")
        start = max(window.start_dt(), floor_to(datetime.fromisoformat(first), step)) if first else window.start_dt()
        read_at = payload.fetched_at.astimezone(UTC)
        end = min(window.end_dt_exclusive(), floor_to(read_at, step) + step)
        return start, max(start, end)

    def snapshots(self, payload: RawPayload) -> dict[str, list[RawPayload]]:
        """The snapshots a manifest lists, per dataset, oldest first (read once for normalize and describe)."""
        if self._read is None or self._read[0] != payload.key:
            listed: Mapping[str, list[str]] = payload.body[SNAPSHOTS]
            self._read = (payload.key, {d: [self.store.get(k) for k in keys] for d, keys in listed.items()})
        return self._read[1]

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """The regular series of the window, from its snapshots."""
        yield from self.aggregate(self.snapshots(payload), payload.window, region)

    def describe(self, payload: RawPayload, region: Region) -> Iterable[Entity]:
        """The names of the entities, from the snapshots of the window."""
        return self.names(self.snapshots(payload), region)

    @abstractmethod
    def aggregate(
        self, snapshots: Mapping[str, list[RawPayload]], window: TimeWindow, region: Region
    ) -> Iterable[Observation]:
        """Turn the snapshots of a window (per dataset, oldest first) into observations."""

    def names(self, snapshots: Mapping[str, list[RawPayload]], region: Region) -> Iterable[Entity]:  # noqa: ARG002
        """The entity names in the snapshots (optional, like ``describe``)."""
        return ()
