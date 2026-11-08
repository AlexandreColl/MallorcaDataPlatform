"""Static GTFS feeds turned into a daily series per stop (shared by the EMT Palma and CTM connectors).

``extract`` downloads the GTFS zip once per window and stores it untouched in bronze (base64, with its
SHA-256). ``normalize`` resolves which services run on each local day (``calendar.txt`` weekdays and date
range, plus the ``calendar_dates.txt`` exceptions for holidays) and counts, per stop:

* ``scheduled_departures``: vehicles calling at the stop. Headway-based trips (``frequencies.txt``) count once
  per headway: a trip running every 15 min from 07:00 to 08:00 is 4 departures; any other trip counts once.
* ``lines_served``: distinct lines (``route_id``) calling at the stop.

and, per line (entity ``route_<route_id>``), ``scheduled_trips``: its departures that day, counted the same way.

Days outside the feed's validity produce no rows, so the gaps rule reports them instead of reading them as
"no service". ``describe`` names every stop with its ``stop_name`` and every line with its short and long name, as
the feed publishes them. ``routes`` draws each line with ``shapes.txt``: the shape most of its trips follow in each
direction, simplified to about 10 m.
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

from core.connectors.base import BaseConnector, ConnectorError
from core.models import Entity, Observation, RawPayload, Region, Route, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator

_ADDED, _REMOVED = "1", "2"  # calendar_dates.exception_type
_KINDS = {"0": "tram", "1": "metro", "2": "train", "3": "bus"}  # routes.route_type
# Extended route types (Google Transit, used by CTM: 715 is an on-demand bus), by hundreds.
_EXTENDED_KINDS = {1: "train", 2: "bus", 4: "metro", 7: "bus", 8: "bus", 9: "tram"}
# Douglas-Peucker tolerance of the line paths, in degrees: about 9 m north-south and 7 m east-west at 39.5° N.
_TOLERANCE = 0.00008


def _simplify(points: list[tuple[float, float]], tolerance: float = _TOLERANCE) -> list[tuple[float, float]]:
    """Douglas-Peucker: drop the points closer than ``tolerance`` to the line between the ones kept."""
    if len(points) < 3:  # noqa: PLR2004 - a segment has nothing to drop
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        farthest, distance = first, 0.0
        for i in range(first + 1, last):
            x, y = points[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / length if length else math.hypot(x - x1, y - y1)
            if d > distance:
                farthest, distance = i, d
        if distance > tolerance:
            keep[farthest] = True
            stack += [(first, farthest), (farthest, last)]
    return [p for p, kept in zip(points, keep, strict=True) if kept]


def _read(payload: RawPayload, *names: str) -> dict[str, list[dict[str, str]]]:
    """The rows of some files of the payload's GTFS zip (a missing file has none)."""
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload.body))) as files:
        present = set(files.namelist())
        return {
            name: list(csv.DictReader(io.StringIO(files.read(name).decode("utf-8-sig")))) if name in present else []
            for name in names
        }


def _kind(route_type: str) -> str:
    """``bus``, ``train``, ``metro`` or ``tram`` from a basic or extended route type; others keep their code."""
    code = route_type.strip()
    if code in _KINDS:
        return _KINDS[code]
    return _EXTENDED_KINDS.get(int(code) // 100, code) if code.isdigit() else code


def _route_name(route: dict[str, str]) -> str:
    """``101 · Port d'Andratx - Palma``, or whichever of the two names the feed fills."""
    parts = [(route.get(k) or "").strip() for k in ("route_short_name", "route_long_name")]
    return " · ".join(p for p in parts if p)


def _seconds(hhmmss: str) -> int:
    """GTFS time (may exceed 24:00:00 for trips after midnight) in seconds."""
    hours, minutes, seconds = (int(part) for part in hhmmss.strip().split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _gtfs_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%Y%m%d").date()  # noqa: DTZ007 - a calendar date, not an instant


def _is_stop(row: dict[str, str]) -> bool:
    """A boarding point (``location_type`` empty or 0), not a station, an entrance or a node."""
    return row.get("location_type", "0").strip() in {"", "0"}


class Gtfs:
    """The parts of a GTFS feed needed to count scheduled service per stop and day."""

    def __init__(self, archive: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            self._files = {name: zf.read(name).decode("utf-8-sig") for name in zf.namelist()}
        self.stops = {s["stop_id"]: s for s in self._rows("stops.txt") if _is_stop(s)}
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


class GtfsConnector(BaseConnector):
    """Scheduled service per stop and day from a static GTFS feed (``options.gtfs_url``, ``options.timezone``)."""

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
        trips_metric = self.config.metrics["scheduled_trips"]
        # The lines that call at a stop of the region, whether or not they run on a given day.
        routes = {t["route_id"] for trip_id, t in gtfs.trips.items() if gtfs.stops_of_trip[trip_id] & stops.keys()}

        day = max(payload.window.start, first)
        while day <= min(payload.window.end, last):
            departures: dict[str, int] = defaultdict(int)
            lines: dict[str, set[str]] = defaultdict(set)
            trips: dict[str, int] = defaultdict(int)
            services = gtfs.services_on(day)
            for trip_id, trip in gtfs.trips.items():
                if trip["service_id"] not in services:
                    continue
                trips[trip["route_id"]] += gtfs.departures_of_trip[trip_id]
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
            for route_id in sorted(routes):
                yield Observation(
                    source=self.name,
                    entity=f"route_{route_id}",
                    metric=trips_metric.name,
                    ts=ts,
                    value=float(trips[route_id]),
                    unit=trips_metric.unit,
                )
            day += timedelta(days=1)

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:
        """The ``stop_name`` of every stop inside the region and the name of every line (not the timetables)."""
        files = _read(payload, "stops.txt", "routes.txt")
        for stop in files["stops.txt"]:
            name = (stop.get("stop_name") or "").strip()
            if name and _is_stop(stop) and region.contains(float(stop["stop_lat"]), float(stop["stop_lon"])):
                yield Entity(source=self.name, entity=f"stop_{stop['stop_id']}", name=name)
        for route in files["routes.txt"]:
            if name := _route_name(route):
                yield Entity(source=self.name, entity=f"route_{route['route_id']}", name=name)

    def routes(self, payload: RawPayload, region: Region) -> Iterator[Route]:
        """Every line with a path that enters the region: the shape most of its trips follow in each direction."""
        files = _read(payload, "routes.txt", "trips.txt", "shapes.txt")
        points: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
        for row in files["shapes.txt"]:
            points[row["shape_id"]].append(
                (float(row["shape_pt_sequence"]), float(row["shape_pt_lon"]), float(row["shape_pt_lat"]))
            )
        # Trips per shape, by line and direction.
        usage: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for trip in files["trips.txt"]:
            shape = (trip.get("shape_id") or "").strip()
            if shape in points:
                usage[trip["route_id"]][(trip.get("direction_id") or "").strip()][shape] += 1
        for route in files["routes.txt"]:
            lines = []
            for shapes in usage.get(route["route_id"], {}).values():
                main = max(sorted(shapes), key=shapes.__getitem__)  # the most used; ties go to the first shape id
                path = [(round(lon, 5), round(lat, 5)) for _, lon, lat in sorted(points[main])]
                lines.append(tuple(_simplify(path)))
            if not any(region.contains(lat, lon) for line in lines for lon, lat in line):
                continue
            color = (route.get("route_color") or "").strip()
            yield Route(
                source=self.name,
                route=f"route_{route['route_id']}",
                short_name=(route.get("route_short_name") or "").strip() or route["route_id"],
                name=_route_name(route),
                kind=_kind(route.get("route_type") or ""),
                color=f"#{color.lower()}" if color else None,
                lines=tuple(lines),
            )
