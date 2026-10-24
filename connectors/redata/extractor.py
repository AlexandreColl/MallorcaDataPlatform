"""REData connector: one request per dataset and chunk; series mapped to metrics in ``connector.yaml``."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)


class REDataConnector(BaseConnector):
    """Electricity data of the Balearic electric system from Red Eléctrica's public API."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset and per chunk of at most ``max_days_per_request`` days.

        Dates are sent as local (Europe/Madrid) days, which is how REData aggregates them.

        Raises:
            ConnectorError: if the region is not covered by the Balearic electric system.
        """
        options = self.config.options
        if region.name not in options["covers_regions"]:
            msg = f"REData Balearic system does not cover region '{region.name}'"
            raise ConnectorError(msg)
        payloads = []
        for dataset, spec in self.config.datasets.items():
            url = f"{options['base_url']}/{spec['path']}"
            for chunk in window.split(int(spec.get("max_days_per_request", window.n_days))):
                params = {
                    "start_date": f"{chunk.start.isoformat()}T00:00",
                    "end_date": f"{chunk.end.isoformat()}T23:59",
                    "time_trunc": spec["time_trunc"],
                    "geo_trunc": options["geo_trunc"],
                    "geo_limit": options["geo_limit"],
                    "geo_ids": str(options["geo_id"]),
                }
                body = self.http.get_json(url, params=params)
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset=dataset,
                        window=chunk,
                        request={"url": url, "params": params},
                        body=body,
                    )
                )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - system-wide source
        """Yield one observation per mapped series and timestamp (converted to UTC).

        Raises:
            ConnectorError: if the payload is an API error instead of data.
        """
        body: Mapping[str, Any] = payload.body or {}
        if "errors" in body:
            msg = f"REData error for {payload.dataset}: {body['errors']}"
            raise ConnectorError(msg)
        spec = self.config.datasets[payload.dataset]
        series: Mapping[str, str] = spec.get("series") or {}
        ignored = set(spec.get("ignore") or ())
        entity = self.config.options["entity"]

        for item in body.get("included") or []:
            attributes = item.get("attributes") or {}
            title = attributes.get("title", "")
            metric_name = series.get(title)
            if metric_name is None:
                if title not in ignored:
                    log.warning("%s/%s: unmapped series '%s' skipped", self.name, payload.dataset, title)
                continue
            unit = self.config.metrics[metric_name].unit
            for point in attributes.get("values") or []:
                value = point.get("value")
                yield Observation(
                    source=self.name,
                    entity=entity,
                    metric=metric_name,
                    ts=datetime.fromisoformat(point["datetime"]).astimezone(UTC),
                    value=None if value is None else float(value),
                    unit=unit,
                    quality=Quality.MISSING if value is None else Quality.OK,
                )
