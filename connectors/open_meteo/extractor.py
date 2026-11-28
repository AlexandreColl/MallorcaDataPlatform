"""Open-Meteo connector: one request per dataset with every region location at once.

A dataset may declare a ``history_url`` for the days its live API no longer serves (older than ``past_days``): the
weather forecast API keeps 92 days, and the archive of the same forecasts goes back decades.

Some metrics start later than their dataset (``available_since`` in the options: the air quality API has served dust
only since 2018 and pollen since 2020). A window that ends before that day does not ask for them, and the hours
before it, always null, are dropped rather than stored as missing values.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Location, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from core.connectors.base import MetricSpec

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

    def available_since(self) -> dict[str, date]:
        """First day of each metric that starts later than its dataset (``options.available_since``)."""
        since = self.config.options.get("available_since") or {}
        return {name: day if isinstance(day, date) else date.fromisoformat(str(day)) for name, day in since.items()}

    def metrics_in(self, dataset: str, window: TimeWindow) -> list[MetricSpec]:
        """The metrics of a dataset that exist on some day of the window."""
        since = self.available_since()
        return [m for m in self.config.metrics_for(dataset) if m.name not in since or since[m.name] <= window.end]

    @staticmethod
    def url_for(spec: Mapping[str, Any], window: TimeWindow, today: date | None = None) -> str:
        """The dataset's live URL, or its ``history_url`` when the window starts before the live API's ``past_days``."""
        history = spec.get("history_url")
        today = today or datetime.now(UTC).date()
        if history and window.start < today - timedelta(days=int(spec["past_days"])):
            return str(history)
        return str(spec["url"])

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset with all the points at once, to its live or its history URL."""
        locations = self.locations(region)
        payloads = []
        for dataset, spec in self.config.datasets.items():
            metrics = [m.name for m in self.metrics_in(dataset, window)]
            params = {
                "latitude": ",".join(f"{loc.lat:.4f}" for loc in locations),
                "longitude": ",".join(f"{loc.lon:.4f}" for loc in locations),
                "hourly": ",".join(metrics),
                "start_date": window.start.isoformat(),
                "end_date": window.end.isoformat(),
                "timezone": "UTC",
            }
            url = self.url_for(spec, window)
            body = self.http.get_json(url, params=params)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset=dataset,
                    window=window,
                    request={
                        "url": url,
                        "params": params,
                        "locations": [loc.name for loc in locations],
                    },
                    body=body,
                )
            )
        return payloads

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:
        """The display name (``label``) of every requested point that has one, with the height of its model cell.

        The height comes from the weather forecast (``elevation``, metres): the terrain the model sees at that point,
        which the station vs model comparison needs to correct for altitude. Other datasets name the points only.
        """
        by_name = {loc.name: loc for loc in self.locations(region)}
        names = payload.request["locations"]
        bodies = payload.body if isinstance(payload.body, list) else [payload.body]
        heights: list[float | None] = [None] * len(names)
        if payload.dataset == "weather" and len(bodies) == len(names):
            heights = [None if b.get("elevation") is None else float(b["elevation"]) for b in bodies]
        for name, height in zip(names, heights, strict=True):
            location = by_name.get(name)
            if location is not None and location.label:
                yield Entity(source=self.name, entity=location.name, name=location.label, elevation_m=height)

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
        since = self.available_since()
        requested = set(str(payload.request["params"]["hourly"]).split(","))
        metrics = [m for m in self.config.metrics_for(payload.dataset) if m.name in requested]
        for loc_name, body in zip(names, bodies, strict=True):
            location = by_name[loc_name]
            hourly = body.get("hourly") or {}
            times = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in hourly.get("time") or []]
            for metric in metrics:
                values = hourly.get(metric.name)
                if values is None:
                    log.warning("%s: metric %s missing for %s", self.name, metric.name, loc_name)
                    continue
                first = since.get(metric.name)
                for ts, v in zip(times, values, strict=True):
                    if first is not None and ts.date() < first:
                        continue  # the metric did not exist yet: no value, not a missing one
                    yield Observation(
                        source=self.name,
                        entity=location.name,
                        metric=metric.name,
                        ts=ts,
                        value=None if v is None else float(v),
                        unit=metric.unit,
                        quality=Quality.MISSING if v is None else Quality.OK,
                        lat=location.lat,
                        lon=location.lon,
                    )
