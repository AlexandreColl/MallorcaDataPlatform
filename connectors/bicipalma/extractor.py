"""BiciPalma connector: Palma's public bikes per station and hour, from the operator's GBFS feed (Nextbike).

GBFS only publishes the current state, so this is a live connector (``core.connectors.live``, ADR 0026):

* ``poll`` fetches ``station_status.json`` every 5 minutes and ``station_information.json`` once an hour, and the
  live poller keeps each answer untouched in bronze under the feed's own ``last_updated``.
* A run reads the snapshots of its window from bronze and sums them up per station and UTC hour: the mean, minimum
  and maximum of the free bikes and of the free docks, the mean of the e-bikes and the mean occupancy
  (bikes over bikes plus docks, so a broken dock counts neither as free nor as full).

Names, positions and capacities come from ``station_information``: the newest snapshot of a station in the window.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import fmean
from typing import TYPE_CHECKING, Any

from core.connectors import ConnectorError
from core.connectors.live import LiveConnector, floor_to
from core.models import Entity, Observation, Quality, RawPayload, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from core.models import Region

STATUS = "station_status"
INFORMATION = "station_information"


@dataclass(frozen=True)
class Station:
    """What ``station_information`` says about one station.

    Its capacity is left out: bikes plus docks is what the station can take now, without its broken docks.
    """

    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Reading:
    """One station in one status snapshot."""

    bikes: int
    ebikes: int
    docks: int


def _stations(body: Any, feed: str) -> list[dict[str, Any]]:  # noqa: ANN401 - the decoded JSON of a feed
    """The ``data.stations`` list of a GBFS feed.

    Raises:
        ConnectorError: when the answer is not a GBFS feed with stations.
    """
    stations = body.get("data", {}).get("stations") if isinstance(body, dict) else None
    if not isinstance(stations, list) or "last_updated" not in body:
        msg = f"bicipalma {feed}: not a GBFS feed with stations: {str(body)[:200]}"
        raise ConnectorError(msg)
    return stations


def entity(station_id: str) -> str:
    """The entity of a station: its GBFS ``station_id`` (the Nextbike place uid), e.g. ``station_91733840``."""
    return f"station_{station_id}"


class BiciPalmaConnector(LiveConnector):
    """Free bikes, e-bikes and docks per BiciPalma station and hour, built from 5-minute snapshots of GBFS."""

    def poll(self, dataset: str, region: Region) -> RawPayload:  # noqa: ARG002 - the feed is the whole system
        """The current answer of one GBFS feed, untouched, dated on the day of its ``last_updated``."""
        url = f"{self.config.options['base_url']}/{self.config.datasets[dataset]['feed']}"
        body: Any = self.http.get_json(url)
        _stations(body, dataset)
        day = self._last_updated(body).date()
        return RawPayload(
            source=self.name, dataset=dataset, window=TimeWindow(day, day), request={"url": url}, body=body
        )

    def instant(self, payload: RawPayload) -> datetime:
        """The feed's ``last_updated``: when Nextbike built the answer, not when it was fetched."""
        return self._last_updated(payload.body)

    @staticmethod
    def _last_updated(body: Mapping[str, Any]) -> datetime:
        return datetime.fromtimestamp(int(body["last_updated"]), UTC)

    def _directory(self, snapshots: Mapping[str, list[RawPayload]]) -> dict[str, Station]:
        """Every station of the information snapshots; a later snapshot updates an earlier one."""
        directory: dict[str, Station] = {}
        for payload in snapshots.get(INFORMATION, []):
            for item in _stations(payload.body, INFORMATION):
                directory[str(item["station_id"])] = Station(
                    name=str(item["name"]),
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                )
        return directory

    def _readings(
        self, snapshots: Mapping[str, list[RawPayload]], window: TimeWindow
    ) -> dict[tuple[str, datetime], list[Reading]]:
        """The readings of each station, grouped by the UTC hour of their snapshot, inside the window only."""
        ebike_types = {str(t) for t in self.config.options.get("ebike_types", [])}
        step = self.config.frequency_delta
        start, end = window.start_dt(), window.end_dt_exclusive()
        readings: dict[tuple[str, datetime], list[Reading]] = defaultdict(list)
        seen: set[datetime] = set()
        for payload in snapshots.get(STATUS, []):
            at = self.instant(payload)
            if not start <= at < end or at in seen:  # the same answer polled twice counts once
                continue
            seen.add(at)
            hour = floor_to(at, step)
            for item in _stations(payload.body, STATUS):
                if item.get("is_installed") is False:  # not on the street: neither empty nor full
                    continue
                types = item.get("vehicle_types_available") or []
                readings[str(item["station_id"]), hour].append(
                    Reading(
                        bikes=int(item["num_bikes_available"]),
                        ebikes=sum(int(t["count"]) for t in types if str(t["vehicle_type_id"]) in ebike_types),
                        docks=int(item["num_docks_available"]),
                    )
                )
        return readings

    def aggregate(
        self, snapshots: Mapping[str, list[RawPayload]], window: TimeWindow, region: Region
    ) -> Iterator[Observation]:
        """One observation per station of the region, metric and UTC hour that has at least one snapshot."""
        directory = self._directory(snapshots)
        for (station_id, hour), readings in sorted(self._readings(snapshots, window).items()):
            station = directory.get(station_id)
            if station is not None and not region.contains(station.lat, station.lon):
                continue
            bikes = [r.bikes for r in readings]
            docks = [r.docks for r in readings]
            filled = [100 * r.bikes / (r.bikes + r.docks) for r in readings if r.bikes + r.docks > 0]
            values: dict[str, float | None] = {
                "bikes_available": fmean(bikes),
                "bikes_available_min": min(bikes),
                "bikes_available_max": max(bikes),
                "ebikes_available": fmean(r.ebikes for r in readings),
                "docks_available": fmean(docks),
                "docks_available_min": min(docks),
                "docks_available_max": max(docks),
                "occupancy": fmean(filled) if filled else None,
            }
            for name, value in values.items():
                metric = self.config.metrics[name]
                yield Observation(
                    source=self.name,
                    entity=entity(station_id),
                    metric=name,
                    ts=hour,
                    value=round(float(value), 2) if value is not None else None,  # Spark wants floats, not ints
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=station.lat if station else None,
                    lon=station.lon if station else None,
                )

    def names(self, snapshots: Mapping[str, list[RawPayload]], region: Region) -> Iterator[Entity]:
        """Each station as BiciPalma names it (``01 PARC DE SES VELES``: its public number and its place)."""
        for station_id, station in self._directory(snapshots).items():
            if region.contains(station.lat, station.lon):
                yield Entity(source=self.name, entity=entity(station_id), name=station.name)
