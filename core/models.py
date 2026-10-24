"""Domain objects shared by every connector and pipeline stage."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

# Common silver schema. Every connector must emit observations with these fields.
SILVER_COLUMNS: tuple[str, ...] = (
    "source",
    "entity",
    "metric",
    "ts",
    "value",
    "unit",
    "quality",
    "lat",
    "lon",
)


class Quality:
    """Row-level quality labels used in the silver layer."""

    OK = "ok"
    SUSPECT = "suspect"
    MISSING = "missing"

    ALL = (OK, SUSPECT, MISSING)


@dataclass(frozen=True)
class TimeWindow:
    """Closed interval of whole UTC days, e.g. 2026-10-01..2026-10-30."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"window end {self.end} is before start {self.start}")

    @classmethod
    def last_days(cls, days: int, today: date | None = None) -> TimeWindow:
        """Last `days` complete days, ending yesterday (UTC).

        Only complete days are requested so that re-running the same window
        always asks the APIs for exactly the same slice of data.
        """
        if days < 1:
            raise ValueError("days must be >= 1")
        today = today or datetime.now(UTC).date()
        end = today - timedelta(days=1)
        return cls(start=end - timedelta(days=days - 1), end=end)

    @property
    def n_days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def slug(self) -> str:
        return f"{self.start:%Y%m%d}_{self.end:%Y%m%d}"

    def start_dt(self) -> datetime:
        return datetime(self.start.year, self.start.month, self.start.day, tzinfo=UTC)

    def end_dt_exclusive(self) -> datetime:
        return self.start_dt() + timedelta(days=self.n_days)


@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Region:
    name: str
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    locations: tuple[Location, ...] = ()

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon

    def location(self, name: str) -> Location:
        for loc in self.locations:
            if loc.name == name:
                return loc
        raise KeyError(f"location '{name}' not defined in region '{self.name}'")


@dataclass(frozen=True)
class RawPayload:
    """One raw API response, stored untouched in the bronze layer."""

    source: str
    dataset: str
    window: TimeWindow
    request: dict[str, Any]
    body: Any
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def key(self) -> str:
        # Deterministic key: re-running a window overwrites the object, and bucket
        # versioning keeps the previous raw response instead of discarding it.
        return f"{self.source}/{self.dataset}/window={self.window.slug}/payload.json"

    def to_json(self) -> str:
        return json.dumps(
            {
                "source": self.source,
                "dataset": self.dataset,
                "window": {
                    "start": self.window.start.isoformat(),
                    "end": self.window.end.isoformat(),
                },
                "request": self.request,
                "fetched_at": self.fetched_at.isoformat(),
                "body": self.body,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> RawPayload:
        data = json.loads(raw)
        return cls(
            source=data["source"],
            dataset=data["dataset"],
            window=TimeWindow(
                start=date.fromisoformat(data["window"]["start"]),
                end=date.fromisoformat(data["window"]["end"]),
            ),
            request=data["request"],
            body=data["body"],
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
        )


@dataclass(frozen=True)
class Observation:
    """One value in the common silver schema."""

    source: str
    entity: str
    metric: str
    ts: datetime
    value: float | None
    unit: str
    quality: str = Quality.OK
    lat: float | None = None
    lon: float | None = None

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("Observation.ts must be timezone-aware (UTC)")
        if self.quality not in Quality.ALL:
            raise ValueError(f"unknown quality label '{self.quality}'")

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["ts"] = self.ts.astimezone(UTC)
        return row
