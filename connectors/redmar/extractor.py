"""REDMAR connector: the tide gauges of Puertos del Estado, read through OPeNDAP (no API key) as hourly sea level.

Each station has one NetCDF file per day on the THREDDS server of Puertos del Estado, with the sea level every half
second (2 Hz) and its quality flag. A request asks OPeNDAP for one sample in ``stride`` (one a minute by default) in
its ASCII form, so a day is about 60 KB instead of the 5 MB file. ``normalize`` averages the samples the source
marks as good into hourly values and labels an hour ``suspect`` when too few of them are good.

The sea level is the height above the harbour's own datum (``sea_level_datum`` of the file), not above the mean sea
level: it compares hours of one station, not two stations or a model.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Any

import requests

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_EPOCH = datetime(1950, 1, 1, tzinfo=UTC)  # TIME is in "days since 1950-01-01T00:00:00Z"
_DAY = timedelta(days=1)
_SAMPLES_PER_DAY = 172_800  # 2 Hz: every daily file has this many samples, with fill values where there is none
_ARRAY = re.compile(r"^(\w+)\[\d+\]")  # the header of an array in the ASCII answer, e.g. "SLEV[1440][1]"
_SIZE = re.compile(r"TIME\[TIME = (\d+)\]")  # the length of a file, in its DDS


def parse_ascii(text: str) -> dict[str, list[float]]:
    """The arrays of an OPeNDAP ASCII answer, by name.

    One-dimensional arrays come as one line of comma separated values, two-dimensional ones as one ``[i], value``
    line per row (here the single depth of a tide gauge).
    """
    arrays: dict[str, list[float]] = {}
    current: list[float] | None = None
    _, _, data = text.partition("-" * 45)  # the DDS of the answer, then a line of dashes, then the values
    for raw_line in data.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = _ARRAY.match(line)
        if header:
            current = arrays.setdefault(header.group(1), [])
        elif current is not None:
            values = line.split(", ")[1:] if line.startswith("[") else line.split(", ")
            current.extend(float(v) for v in values)
    return arrays


def _server_error(error: requests.RequestException) -> bool:
    """Whether the server failed to answer (5xx, or still 5xx after the retries), not the request itself."""
    if isinstance(error, requests.exceptions.RetryError):
        return True
    response = error.response
    return response is not None and response.status_code >= requests.codes.internal_server_error


class RedmarConnector(BaseConnector):
    """Hourly sea level at the tide gauges of Puertos del Estado inside the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One payload per station with the sampled sea level of every day of the window that has a file.

        A day the server cannot read (a 5xx, as for the broken file of Palma on 2012-06-01) is skipped, unless more
        than ``max_unreadable_days`` follow one another: that is the server down, not a file.

        Raises:
            ConnectorError: if no station lies in the region.
            requests.HTTPError: on a client error, or on server errors for too many days in a row.
            requests.exceptions.RetryError: likewise, when the retries of the HTTP client ran out.
        """
        payloads = []
        stride = int(self.config.options["stride"])
        max_unreadable = int(self.config.options["max_unreadable_days"])
        for station in self._stations(region):
            days: dict[str, str] = {}
            urls: dict[str, str] = {}
            unreadable = 0  # consecutive days the server failed to read: one is a broken file, many an outage
            day = window.start
            while day <= window.end:
                url = self._file_url(station, day)
                try:
                    body = self._sampled_day(url, stride)
                except (requests.HTTPError, requests.exceptions.RetryError) as error:
                    if not _server_error(error) or unreadable >= max_unreadable:
                        raise
                    unreadable += 1
                    log.warning("%s: the server cannot read %s, day skipped: %s", self.name, url, error)
                    body = None
                else:
                    unreadable = 0
                if body is not None:
                    days[day.isoformat()], urls[day.isoformat()] = body, url
                day += _DAY
            if not days:
                log.warning("%s: no file of %s from %s to %s", self.name, station["entity"], window.start, window.end)
                continue
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="sea_level",
                    window=window,
                    request={"station": station["entity"], "stride": stride, "urls": urls},
                    body=days,
                    partition=str(station["entity"]),
                )
            )
        return payloads

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:  # noqa: ARG002 - names from config
        """The name of the payload's tide gauge, from ``connector.yaml``."""
        station = self._station(payload.request["station"])
        yield Entity(source=self.name, entity=station["entity"], name=str(station["name"]))

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - coords from config
        """One observation per station and hour: the mean of the samples the source marks as good.

        Raises:
            ConnectorError: if a day's arrays do not have the same length.
        """
        station = self._station(payload.request["station"])
        good_flags = {int(flag) for flag in self.config.options["good_qc_flags"]}
        min_good_share = float(self.config.options["min_good_share"])
        metric = self.config.metrics["sea_level"]
        samples: dict[datetime, int] = defaultdict(int)
        good: dict[datetime, list[float]] = defaultdict(list)
        for day, text in sorted(payload.body.items()):
            arrays = parse_ascii(text)
            times, levels, flags = arrays.get("TIME", []), arrays.get("SLEV", []), arrays.get("SLEV_QC", [])
            if not len(times) == len(levels) == len(flags):
                msg = f"{station['entity']} {day}: {len(times)} times, {len(levels)} levels and {len(flags)} flags"
                raise ConnectorError(msg)
            for t, level, flag in zip(times, levels, flags, strict=True):
                ts = _EPOCH + timedelta(seconds=round(t * 86_400))
                hour = ts.replace(minute=0, second=0, microsecond=0)
                samples[hour] += 1
                if int(flag) in good_flags and metric.min <= level <= metric.max:
                    good[hour].append(level)
        for hour in sorted(samples):
            values = good.get(hour, [])
            if not values:
                value, quality = None, Quality.MISSING
            else:
                value = round(fmean(values), 3)
                quality = Quality.OK if len(values) / samples[hour] >= min_good_share else Quality.SUSPECT
            yield Observation(
                source=self.name,
                entity=station["entity"],
                metric=metric.name,
                ts=hour,
                value=value,
                unit=metric.unit,
                quality=quality,
                lat=float(station["lat"]),
                lon=float(station["lon"]),
            )

    def _file_url(self, station: Mapping[str, Any], day: date) -> str:
        """The OPeNDAP address of one day of a station."""
        path = f"{station['folder']}/{day:%Y}/{day:%m}/MIR2Z_{station['code']}_{day:%Y%m%d}.nc4"
        return f"{self.config.options['thredds_url']}/dodsC/{path}"

    def _sampled_day(self, url: str, stride: int) -> str | None:
        """One sample in ``stride`` of a day file as OPeNDAP ASCII, or None when the station has no file that day."""
        try:
            return self.http.get_text(f"{url}.ascii?{self._constraint(stride, _SAMPLES_PER_DAY)}")
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status == requests.codes.not_found:
                log.info("no file %s", url)
                return None
            if status != requests.codes.bad_request:
                raise
        # A file of another length (the constraint went past its end): read its size and ask again.
        size = _SIZE.search(self.http.get_text(f"{url}.dds"))
        if size is None:
            msg = f"cannot read the size of {url}"
            raise ConnectorError(msg)
        return self.http.get_text(f"{url}.ascii?{self._constraint(stride, int(size.group(1)))}")

    @staticmethod
    def _constraint(stride: int, size: int) -> str:
        """The time, the sea level and its flag, one sample in ``stride`` (brackets escaped for the URL)."""
        hyperslab = f"%5B0:{stride}:{size - 1}%5D"
        depth = "%5B0:0%5D"
        return f"TIME{hyperslab},SLEV{hyperslab}{depth},SLEV_QC{hyperslab}{depth}"

    def _stations(self, region: Region) -> list[Mapping[str, Any]]:
        stations = [s for s in self.config.options["stations"] if region.contains(float(s["lat"]), float(s["lon"]))]
        if not stations:
            msg = f"no REDMAR tide gauge configured inside region '{region.name}'"
            raise ConnectorError(msg)
        return stations

    def _station(self, entity: str) -> Mapping[str, Any]:
        return next(s for s in self.config.options["stations"] if s["entity"] == entity)
