"""IGN connector: earthquakes from the FDSN event web service (text format, no API key).

One request per window with the region's bounding box widened by ``margin_deg``. The service answers
``204 No Content`` when there are no events, which is the usual case for a quiet area and a short window:
the empty body is still stored in bronze and the run succeeds with no rows (``frequency: event``).

Each event becomes one observation per metric (magnitude, depth) with the event id as ``entity`` and the
epicentre as ``lat``/``lon``.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector
from core.models import Observation, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator


def _to_float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in {None, ""} else None
    except ValueError:
        return None


class IgnConnector(BaseConnector):
    """Earthquakes located by the IGN inside the region and its surrounding sea."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One FDSN text request for the whole window."""
        url = str(self.config.options["fdsn_url"])
        min_lat, min_lon, max_lat, max_lon = self.search_box(region)
        params: dict[str, Any] = {
            "starttime": f"{window.start.isoformat()}T00:00:00",
            "endtime": f"{window.end.isoformat()}T23:59:59",
            "minlat": f"{min_lat:.2f}",
            "maxlat": f"{max_lat:.2f}",
            "minlon": f"{min_lon:.2f}",
            "maxlon": f"{max_lon:.2f}",
            "format": "text",
            "orderby": "time-asc",
        }
        return [
            RawPayload(
                source=self.name,
                dataset="earthquakes",
                window=window,
                request={"url": url, "params": params},
                body=self.http.get_text(url, params=params),
            )
        ]

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - the bbox was applied by the request
        """One observation per event and metric, only for events located by the configured authors."""
        columns: dict[str, str] = self.config.datasets[payload.dataset]["columns"]
        authors = {str(a) for a in self.config.options["authors"]}
        for event in self._rows(payload.body):
            if event["Author"] not in authors:
                continue
            ts = datetime.fromisoformat(event["Time"])
            lat, lon = float(event["Latitude"]), float(event["Longitude"])
            for column, metric_name in columns.items():
                metric = self.config.metrics[metric_name]
                yield Observation(
                    source=self.name,
                    entity=event["EventID"],
                    metric=metric.name,
                    ts=ts,
                    value=_to_float(event.get(column)),
                    unit=metric.unit,
                    lat=lat,
                    lon=lon,
                )

    def search_box(self, region: Region) -> tuple[float, float, float, float]:
        """Region bbox widened by ``margin_deg``: (min_lat, min_lon, max_lat, max_lon)."""
        margin = float(self.config.options["margin_deg"])
        return (region.min_lat - margin, region.min_lon - margin, region.max_lat + margin, region.max_lon + margin)

    @staticmethod
    def _rows(text: str) -> Iterator[dict[str, str]]:
        """Parse the FDSN text format: ``|``-separated, header line starting with ``#``."""
        lines = [line for line in (text or "").splitlines() if line.strip()]
        if not lines:
            return
        lines[0] = lines[0].removeprefix("#")
        yield from csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
