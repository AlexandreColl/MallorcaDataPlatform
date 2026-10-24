"""EMT Palma connector: static GTFS turned into a daily series per stop.

``extract`` downloads the GTFS zip once per window and stores it untouched in bronze (base64, with its
SHA-256). ``normalize`` resolves which services run on each local day (``calendar.txt`` weekdays and date
range, plus the ``calendar_dates.txt`` exceptions for holidays) and counts, per stop:

* ``scheduled_departures``: buses calling at the stop. EMT publishes headway-based trips
  (``frequencies.txt``): a trip running every 15 min from 07:00 to 08:00 is 4 departures.
* ``lines_served``: distinct lines calling at the stop.

Days outside the feed's validity produce no rows, so the gaps rule reports them instead of reading them as
"no buses".
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import math
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator

_ADDED, _REMOVED = "1", "2"  # calendar_dates.exception_type


def _seconds(hhmmss: str) -> int:
    """GTFS time (may exceed 24:00:00 for trips after midnight) in seconds."""
    hours, minutes, seconds = (int(part) for part in hhmmss.strip().split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _gtfs_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%Y%m%d").date()  # noqa: DTZ007 - a calendar date, not an instant


class Gtfs:
    """The parts of a GTFS feed needed to count scheduled service per stop and day."""

    def __init__(self, archive: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            self._files = {name: zf.read(name).decode("utf-8-sig") for name in zf.namelist()}
        self.stops = {s["stop_id"]: s for s in self._rows("stops.txt") if s.get("location_type", "0") in {"", "0"}}
        self.trips = {t["trip_id"]: t for t in self._rows("trips.txt")}
        self.stops_of_trip: dict[str, set[str]] = defaultdict(set)
        for row in self._rows("stop_times.txt"):
            self.stops_of_trip[row["trip_id"]].add(row["stop_id"])
        self.departures_of_trip = self._departures_per_trip()
        self.calendar = self._rows("calendar.txt")
        self.exceptions: dict[date, dict[str, str]] = defaultdict(dict)
        for row in self._rows("calendar_dates.txt"):
            self.exceptions[_gtfs_date(row["date"])][row["service_id"]] = row["exception_type"].strip()

    def _rows(self, name: str) -> list[dict[str, str]]:
        if name not in self._files:
            return []
        return list(csv.DictReader(io.StringIO(self._files[name])))

    def _departures_per_trip(self) -> dict[str, int]:
        """Departures per trip: one, or one per headway in each ``frequencies.txt`` interval."""
        departures: dict[str, int] = defaultdict(int)
        for row in self._rows("frequencies.txt"):
            span = _seconds(row["end_time"]) - _seconds(row["start_time"])
            departures[row["trip_id"]] += max(math.ceil(span / int(row["headway_secs"])), 0)
        return {trip_id: departures.get(trip_id, 1) for trip_id in self.trips}

    def validity(self) -> tuple[date, date]:
        """First and last day covered by the feed's calendars."""
        days = [_gtfs_date(r[k]) for r in self.calendar for k in ("start_date", "end_date")] + list(self.exceptions)
        if not days:
            msg = "GTFS feed has neither calendar.txt nor calendar_dates.txt"
            raise ConnectorError(msg)
        return min(days), max(days)

    def services_on(self, day: date) -> set[str]:
        """Service ids running on ``day``."""
        weekday = day.strftime("%A").lower()
        services = {
            r["service_id"]
            for r in self.calendar
            if r[weekday].strip() == "1" and _gtfs_date(r["start_date"]) <= day <= _gtfs_date(r["end_date"])
        }
        for service_id, exception in self.exceptions.get(day, {}).items():
            if exception == _ADDED:
                services.add(service_id)
            elif exception == _REMOVED:
                services.discard(service_id)
        return services


class EmtPalmaConnector(BaseConnector):
    """Scheduled bus service per stop and day from EMT Palma's static GTFS."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - the feed covers the whole network
        """Download the GTFS zip (one payload per window; a feed is a snapshot of the current schedule)."""
        url = str(self.config.options["gtfs_url"])
        archive = self.http.get_bytes(url)
        return [
            RawPayload(
                source=self.name,
                dataset="schedule",
                window=window,
                request={"url": url, "sha256": hashlib.sha256(archive).hexdigest(), "bytes": len(archive)},
                body=base64.b64encode(archive).decode("ascii"),
            )
        ]

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per stop inside the region, metric and day the feed is valid."""
        gtfs = Gtfs(base64.b64decode(payload.body))
        tz = ZoneInfo(str(self.config.options["timezone"]))
        first, last = gtfs.validity()
        stops = {
            stop_id: (float(s["stop_lat"]), float(s["stop_lon"]))
            for stop_id, s in gtfs.stops.items()
            if region.contains(float(s["stop_lat"]), float(s["stop_lon"]))
        }
        departures_metric = self.config.metrics["scheduled_departures"]
        lines_metric = self.config.metrics["lines_served"]

        day = max(payload.window.start, first)
        while day <= min(payload.window.end, last):
            departures: dict[str, int] = defaultdict(int)
            lines: dict[str, set[str]] = defaultdict(set)
            services = gtfs.services_on(day)
            for trip_id, trip in gtfs.trips.items():
                if trip["service_id"] not in services:
                    continue
                for stop_id in gtfs.stops_of_trip[trip_id]:
                    departures[stop_id] += gtfs.departures_of_trip[trip_id]
                    lines[stop_id].add(trip["route_id"])
            ts = datetime.combine(day, time(), tzinfo=tz)
            for stop_id, (lat, lon) in stops.items():
                for metric, value in (
                    (departures_metric, departures[stop_id]),
                    (lines_metric, len(lines[stop_id])),
                ):
                    yield Observation(
                        source=self.name,
                        entity=f"stop_{stop_id}",
                        metric=metric.name,
                        ts=ts,
                        value=float(value),
                        unit=metric.unit,
                        lat=lat,
                        lon=lon,
                    )
            day += timedelta(days=1)
