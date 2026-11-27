"""NOAA OISST connector: the satellite sea surface temperature of NOAA OISST v2.1 around Mallorca, read through ERDDAP.

The Daily Optimum Interpolation SST of NOAA NCEI blends satellite (AVHRR), ship and buoy temperatures into one
global grid of 0.25 degrees, one analysis per UTC day since September 1981. ERDDAP serves it as CSV for any
box of the grid, without a key, in two products:

* ``final``: the record, published about 16 days after the day it describes.
* ``preliminary``: the near-real-time analysis since May 2020, published the next day and replaced by the final
  one about two weeks later.

A run asks each product for its last published day (``time[last]``, a few bytes), then for one box of cells that
covers every configured point, for the days of the window it has: the final product up to its last day, the
preliminary one for the days after it. The days ERDDAP's final aggregation lacks (it has holes, NOAA's files do
not) come from the copy of NOAA PSL, over OPeNDAP. ``normalize`` keeps the configured cells and stamps each value
at 00:00 UTC of the day it describes (ERDDAP stamps it at 12:00 UTC, the middle of that day).
"""

from __future__ import annotations

import csv
import io
import logging
import math
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import requests

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_DAY = timedelta(days=1)
_HEADER_ROWS = 2  # ERDDAP's CSV has a row of names and a row of units before the values
_NOT_PUBLISHED = "greater than the axis maximum"  # the 404 of a day the server does not have yet
_PSL_EPOCH = date(1800, 1, 1)  # the time of PSL's files is in "days since 1800-01-01"
_PSL_FILL = 1e30  # PSL's missing value (land) is -9.96921e36
_GRID_STEP = 0.25
_GRID_FIRST = 0.125  # the first cell centre of the grid, in latitude from -90 and in longitude from 0
_ARRAY = re.compile(r"^sst\.(\w+)\[")  # an array header of PSL's OPeNDAP ASCII answer, e.g. "sst.time[4]"


def parse_csv(text: str) -> list[tuple[date, float, float, float | None]]:
    """The rows of an ERDDAP ``sst`` CSV as (day, latitude, longitude, value); a land or missing cell is None.

    Raises:
        ConnectorError: if the header is not that of the ``sst`` variable.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0] != ["time", "zlev", "latitude", "longitude", "sst"]:
        msg = f"unexpected ERDDAP header {rows[0] if rows else None}"
        raise ConnectorError(msg)
    parsed = []
    for row in rows[_HEADER_ROWS:]:
        if not row:
            continue
        stamp, _, lat, lon, sst = row
        value = float(sst)
        parsed.append((date.fromisoformat(stamp[:10]), float(lat), float(lon), None if math.isnan(value) else value))
    return parsed


def last_day(text: str) -> date:
    """The day of the last time step of a ``time[last]`` CSV answer.

    Raises:
        ConnectorError: if the answer has no time step.
    """
    rows = [row for row in csv.reader(io.StringIO(text)) if row]
    if len(rows) <= _HEADER_ROWS:
        msg = f"no time step in the ERDDAP answer {text[:200]!r}"
        raise ConnectorError(msg)
    return date.fromisoformat(rows[_HEADER_ROWS][0][:10])


def parse_opendap_grid(text: str) -> list[tuple[date, float, float, float | None]]:
    """The values of PSL's OPeNDAP ASCII answer for an ``sst[time][lat][lon]`` slab, in the shape of :func:`parse_csv`.

    The answer lists the slab as one ``[t][lat], v, v, ...`` line per time and latitude, then its time (days since
    1800-01-01), latitude and longitude axes. Land cells have the fill value and read as None.

    Raises:
        ConnectorError: if the slab and its axes do not match.
    """
    rows: list[list[float]] = []
    axes: dict[str, list[float]] = {}
    current: str | None = None
    _, _, data = text.partition("-" * 45)
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = _ARRAY.match(line)
        if header:
            current = header.group(1)
        elif current == "sst":
            rows.append([float(v) for v in line.split(", ")[1:]])
        elif current is not None:
            axes.setdefault(current, []).extend(float(v) for v in line.split(", "))
    times, lats, lons = axes.get("time", []), axes.get("lat", []), axes.get("lon", [])
    if len(rows) != len(times) * len(lats) or any(len(row) != len(lons) for row in rows):
        msg = f"PSL slab of {len(rows)} rows does not match {len(times)} times, {len(lats)} lats and {len(lons)} lons"
        raise ConnectorError(msg)
    parsed = []
    for i, row in enumerate(rows):
        day = _PSL_EPOCH + timedelta(days=round(times[i // len(lats)]))
        lat = lats[i % len(lats)]
        for lon, value in zip(lons, row, strict=True):
            lon_pm180 = lon - 360 if lon > 180 else lon  # noqa: PLR2004 - PSL's longitudes run 0-360
            parsed.append((day, lat, lon_pm180, None if abs(value) > _PSL_FILL else value))
    return parsed


def _spans(days: list[date], max_days: int) -> list[list[date]]:
    """Sorted ``days`` in groups of one year whose first and last day are less than ``max_days`` apart."""
    spans: list[list[date]] = []
    for day in days:
        if spans and day.year == spans[-1][0].year and (day - spans[-1][0]).days < max_days:
            spans[-1].append(day)
        else:
            spans.append([day])
    return spans


class NoaaOisstConnector(BaseConnector):
    """Daily satellite sea surface temperature at the OISST cells of the coastal points inside the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One box request per product for the days of the window it has published.

        A day neither product has published yet is left out (the next run asks for it again), and so are the days
        before the record starts.

        Raises:
            ConnectorError: if no point lies inside the region.
            requests.HTTPError: if ERDDAP rejects a request for another reason than a day it does not have yet.
        """
        points = self._points(region)
        start = max(window.start, date.fromisoformat(str(self.config.options["first_day"])))
        payloads = []
        for dataset in ("final", "preliminary"):
            if start > window.end:
                break
            published = min(window.end, self._last_day(dataset))
            if published >= start:
                payload = self._box(dataset, window, start, published, points)
                if payload is not None:
                    payloads.append(payload)
                    if dataset == "final":
                        payloads.extend(self._fill_gaps(window, start, published, payload, points))
            start = max(start, published + _DAY)
        if start <= window.end:
            log.info("%s: %s..%s not published yet", self.name, start, window.end)
        return payloads

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:  # noqa: ARG002 - names from config
        """The names of the payload's points, from ``connector.yaml``."""
        for point in self._configured(payload.request["points"]):
            yield Entity(source=self.name, entity=str(point["name"]), name=str(point["label"]))

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - points of extract
        """One observation per point and day: the value of its cell, missing when the analysis has none."""
        metric = next(iter(self.config.metrics_for(payload.dataset)))
        if payload.request.get("server") == "psl":
            days = set(payload.request["days"])
            rows = [row for row in parse_opendap_grid(payload.body) if row[0].isoformat() in days]
        else:
            rows = parse_csv(payload.body)
        points = self._configured(payload.request["points"])
        by_cell: dict[tuple[float, float], list[Mapping[str, Any]]] = {}
        for point in points:
            by_cell.setdefault((float(point["cell_lat"]), float(point["cell_lon"])), []).append(point)
        for day, lat, lon, value in rows:
            for point in by_cell.get((lat, lon), []):
                yield Observation(
                    source=self.name,
                    entity=str(point["name"]),
                    metric=metric.name,
                    ts=datetime.combine(day, time(), tzinfo=UTC),
                    value=value,
                    unit=metric.unit,
                    quality=Quality.MISSING if value is None else Quality.OK,
                    lat=lat,
                    lon=lon,
                )

    def _box(
        self, dataset: str, window: TimeWindow, start: date, end: date, points: list[Mapping[str, Any]]
    ) -> RawPayload | None:
        """The CSV of the smallest box that holds the cells of ``points`` from ``start`` to ``end``.

        None when ERDDAP answers that the days are past its last one (it was updated between the two requests).
        """
        lats = [float(p["cell_lat"]) for p in points]
        lons = [float(p["cell_lon"]) for p in points]
        url = (
            f"{self._dataset_url(dataset)}.csv?sst"
            f"%5B({start.isoformat()}T12:00:00Z):1:({end.isoformat()}T12:00:00Z)%5D%5B(0.0)%5D"
            f"%5B({min(lats)}):1:({max(lats)})%5D%5B({min(lons)}):1:({max(lons)})%5D"
        )
        try:
            body = self.http.get_text(url)
        except requests.HTTPError as error:
            text = error.response.text if error.response is not None else ""
            if error.response is None or error.response.status_code != requests.codes.not_found:
                raise
            if _NOT_PUBLISHED not in text:
                raise
            log.info("%s: %s has no day after %s yet: %s", self.name, dataset, start, text.strip()[-160:])
            return None
        return RawPayload(
            source=self.name,
            dataset=dataset,
            window=window,
            request={"url": url, "start": f"{start}", "end": f"{end}", "points": [p["name"] for p in points]},
            body=body,
        )

    def _fill_gaps(
        self, window: TimeWindow, start: date, end: date, erddap: RawPayload, points: list[Mapping[str, Any]]
    ) -> list[RawPayload]:
        """The days ERDDAP's aggregation of the final product lacks, from PSL's copy.

        ERDDAP's time axis has holes (about 1,200 days, most of them in 1992-1998) that NOAA's own files do not.
        PSL reads its yearly file at about 0.3 s a day and a whole year passes the read timeout, so the missing days
        are asked for in spans of at most ``psl_max_days`` inside one year. A request PSL fails is logged and left
        out: those days stay missing until the next run that reads them.
        """
        have = {day for day, *_ in parse_csv(erddap.body)}
        missing = [d for d in (start + timedelta(days=i) for i in range((end - start).days + 1)) if d not in have]
        if not missing:
            return []
        log.info("%s: %d days missing from ERDDAP, asked from PSL", self.name, len(missing))
        lat_index = sorted({round((float(p["cell_lat"]) + 90 - _GRID_FIRST) / _GRID_STEP) for p in points})
        lon_index = sorted({round((float(p["cell_lon"]) % 360 - _GRID_FIRST) / _GRID_STEP) for p in points})
        payloads = []
        for days in _spans(missing, int(self.config.options["psl_max_days"])):
            year = days[0].year
            first, last = ((d - date(year, 1, 1)).days for d in (days[0], days[-1]))
            url = (
                f"{self.config.options['psl_url']}/sst.day.mean.{year}.nc.ascii?sst%5B{first}:1:{last}%5D"
                f"%5B{lat_index[0]}:1:{lat_index[-1]}%5D%5B{lon_index[0]}:1:{lon_index[-1]}%5D"
            )
            try:
                body = self.http.get_text(url)
            except requests.RequestException as error:
                log.warning("%s: PSL could not fill %d days of %d: %s", self.name, len(days), year, error)
                continue
            request = {
                "server": "psl",
                "url": url,
                "days": [f"{d}" for d in days],
                "points": [p["name"] for p in points],
            }
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="final",
                    window=window,
                    request=request,
                    body=body,
                    partition=f"psl_{days[0]:%Y%m%d}",
                )
            )
        return payloads

    def _last_day(self, dataset: str) -> date:
        """The last day a product has published."""
        return last_day(self.http.get_text(f"{self._dataset_url(dataset)}.csv?time%5Blast%5D"))

    def _dataset_url(self, dataset: str) -> str:
        return f"{self.config.options['erddap_url']}/griddap/{self.config.datasets[dataset]['dataset_id']}"

    def _points(self, region: Region) -> list[Mapping[str, Any]]:
        points = [p for p in self.config.options["points"] if region.contains(float(p["lat"]), float(p["lon"]))]
        if not points:
            msg = f"no OISST point configured inside region '{region.name}'"
            raise ConnectorError(msg)
        return points

    def _configured(self, names: list[str]) -> list[Mapping[str, Any]]:
        return [p for p in self.config.options["points"] if p["name"] in names]
