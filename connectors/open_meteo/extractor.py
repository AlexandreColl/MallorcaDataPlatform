"""Open-Meteo connector: one request per dataset with every region location at once."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.connectors import BaseConnector, ConnectorError
from core.models import Location, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator

log = logging.getLogger(__name__)


class OpenMeteoConnector(BaseConnector):
    """Hourly air quality and weather for every location of the region."""

    def locations(self, region: Region) -> tuple[Location, ...]:
        """Points to query: the region's locations (subclasses may use their own points).

        Raises:
            ConnectorError: if there are none.
        """
        if not region.locations:
            msg = f"region '{region.name}' has no locations for Open-Meteo"
            raise ConnectorError(msg)
        return region.locations

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset with all the points at once."""
        locations = self.locations(region)
        payloads = []
        for dataset, spec in self.config.datasets.items():
            metrics = [m.name for m in self.config.metrics_for(dataset)]
            params = {
                "latitude": ",".join(f"{loc.lat:.4f}" for loc in locations),
                "longitude": ",".join(f"{loc.lon:.4f}" for loc in locations),
                "hourly": ",".join(metrics),
                "start_date": window.start.isoformat(),
                "end_date": window.end.isoformat(),
                "timezone": "UTC",
            }
            body = self.http.get_json(spec["url"], params=params)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset=dataset,
                    window=window,
                    request={
                        "url": spec["url"],
                        "params": params,
                        "locations": [loc.name for loc in locations],
                    },
                    body=body,
                )
            )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """Yield one observation per location, metric and hour.

        A single location returns a JSON object and several locations return a list in
        request order; both shapes are accepted.

        Raises:
            ConnectorError: if the number of returned locations does not match the request.
        """
        bodies = payload.body if isinstance(payload.body, list) else [payload.body]
        names = payload.request["locations"]
        if len(bodies) != len(names):
            msg = f"expected {len(names)} locations, got {len(bodies)}"
            raise ConnectorError(msg)

        by_name = {loc.name: loc for loc in self.locations(region)}
        for loc_name, body in zip(names, bodies, strict=True):
            location = by_name[loc_name]
            hourly = body.get("hourly") or {}
            times = hourly.get("time") or []
            for metric in self.config.metrics_for(payload.dataset):
                values = hourly.get(metric.name)
                if values is None:
                    log.warning("%s: metric %s missing for %s", self.name, metric.name, loc_name)
                    continue
                for t, v in zip(times, values, strict=True):
                    yield Observation(
                        source=self.name,
                        entity=location.name,
                        metric=metric.name,
                        ts=datetime.fromisoformat(t).replace(tzinfo=UTC),
                        value=None if v is None else float(v),
                        unit=metric.unit,
                        quality=Quality.MISSING if v is None else Quality.OK,
                        lat=location.lat,
                        lon=location.lon,
                    )
