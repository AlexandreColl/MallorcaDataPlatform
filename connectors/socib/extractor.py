"""SOCIB connector: THREDDS NetCDF Subset Service (CSV, no API key) aggregated to hourly values.

Per station, the days from the first of its current deployment's ``*_latest.nc`` on come from that file; earlier
days come from the monthly files of the archive (``L1/<year>/..._L1_<year>-<month>.nc``), one request per file.
Each request downloads the raw 1-30 minute samples with their SOCIB QC flags. ``normalize`` averages the samples
the source marks as good into hourly values and labels an hour ``suspect`` when too few of them are good.

A station is a weather station (dataset ``weather``) or a wave buoy (``waves``); the variables of each dataset are
in ``connector.yaml``.
"""

from __future__ import annotations

import calendar
import csv
import io
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import fmean
from typing import TYPE_CHECKING, Any

import requests

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_LATEST_FILE = re.compile(r'urlPath="([^"]*?dep(\d+)_[^"]*_latest\.nc)"')
# A month of the archive: every deployment that recorded in that month has a file of its own.
_MONTHLY_FILE = re.compile(r'urlPath="([^"]*?dep(\d+)_[^"]*_L1_(\d{4})-(\d{2})\.nc)"')
# The file's first time, a global attribute of its NcML. NCSS's dataset.xml also has it as <TimeSpan><begin>, but
# SOCIB's server leaves that block out at times (November 2026).
_COVERAGE_START = re.compile(r'<attribute name="time_coverage_start" value="([^"]+)"')
# NetCDF Subset Service for point data (station time series). SOCIB moved it from `/ncss/` to `/ncss/point/` in
# November 2026; the old path answers 404.
_NCSS = "ncss/point"
# NCSS answers 400 with this text when the asked days fall outside the file (a deployment that ended mid-month).
_NO_FEATURES = "No features"
_DAY = timedelta(days=1)


@dataclass(frozen=True)
class _Part:
    """One file to read and the days of the window it covers."""

    path: str
    first: date
    last: date
    label: str  # "latest", or the month and deployment of an archive file, e.g. "2026-08_dep0001"


@dataclass
class _HourBucket:
    samples: int = 0
    good: list[float] = field(default_factory=list)


def _to_float(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw not in {None, ""} else None
    except ValueError:
        return None
    return None if value is None or math.isnan(value) else value


def _to_int(raw: str | None) -> int | None:
    value = _to_float(raw)
    return None if value is None else int(value)


class SocibConnector(BaseConnector):
    """Hourly observations from the SOCIB weather stations and wave buoys inside the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One CSV request per station and file with every variable of its dataset and their QC flags.

        Raises:
            ConnectorError: if no station lies in the region or a station has no current file.
        """
        payloads = []
        for station in self._stations(region):
            dataset = str(station.get("dataset", "weather"))
            variables = list(self.config.datasets[dataset]["variables"])
            requested = [name for var in variables for name in (var, f"QC_{var}")]
            for part in self._parts(str(station["folder"]), window):
                url = f"{self.config.options['thredds_url']}/{_NCSS}/{part.path}"
                params: dict[str, Any] = {
                    "var": requested,
                    "time_start": f"{part.first.isoformat()}T00:00:00Z",
                    "time_end": f"{part.last.isoformat()}T23:59:59Z",
                    "accept": "csv",
                }
                body = self._csv(url, params)
                if body is None:
                    continue
                entity = str(station["entity"])
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset=dataset,
                        window=window,
                        request={"url": url, "params": params, "station": entity, "file": part.label},
                        body=body,
                        # The latest file keeps the station's own partition, as before the archive was read.
                        partition=entity if part.label == "latest" else f"{entity}-{part.label}",
                    )
                )
        return payloads

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:  # noqa: ARG002 - names from config
        """The name of the payload's station, from ``connector.yaml``."""
        station = self._station(payload.request["station"])
        yield Entity(source=self.name, entity=station["entity"], name=str(station["name"]))

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - station coords come from config
        """Aggregate raw samples to one observation per station, variable and hour."""
        variables: Mapping[str, Mapping[str, Any]] = self.config.datasets[payload.dataset]["variables"]
        station = self._station(payload.request["station"])
        min_good_share = float(self.config.options["min_good_share"])

        for (var, hour), bucket in sorted(self._buckets(payload.body, variables).items()):
            spec = variables[var]
            metric = self.config.metrics[spec["metric"]]
            value = None
            if bucket.good:
                aggregate = max if spec.get("agg") == "max" else fmean
                value = round(aggregate(bucket.good) * float(spec.get("scale", 1)), 3)
            if value is None:
                quality = Quality.MISSING
            elif len(bucket.good) / bucket.samples < min_good_share:
                quality = Quality.SUSPECT
            else:
                quality = Quality.OK
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

    def _buckets(self, csv_text: str, variables: Mapping[str, Any]) -> dict[tuple[str, datetime], _HourBucket]:
        """Group samples by (variable, hour); keep only values the source QC marks as good."""
        good_flags = {int(flag) for flag in self.config.options["good_qc_flags"]}
        buckets: dict[tuple[str, datetime], _HourBucket] = defaultdict(_HourBucket)
        for raw_row in csv.DictReader(io.StringIO(csv_text)):
            row = {key.split("[", 1)[0]: value for key, value in raw_row.items()}  # 'AIR_TEM[unit="C"]' -> 'AIR_TEM'
            hour = datetime.fromisoformat(row["time"]).astimezone(UTC).replace(minute=0, second=0, microsecond=0)
            for var in variables:
                bucket = buckets[var, hour]
                bucket.samples += 1
                value, flag = _to_float(row.get(var)), _to_int(row.get(f"QC_{var}"))
                if value is not None and flag in good_flags:
                    bucket.good.append(value)
        return buckets

    def _stations(self, region: Region) -> list[Mapping[str, Any]]:
        stations = [s for s in self.config.options["stations"] if region.contains(float(s["lat"]), float(s["lon"]))]
        if not stations:
            msg = f"no SOCIB station configured inside region '{region.name}'"
            raise ConnectorError(msg)
        return stations

    def _station(self, entity: str) -> Mapping[str, Any]:
        """The station of ``entity``: a buoy with weather and waves has two entries, with the same name and place."""
        return next(s for s in self.config.options["stations"] if s["entity"] == entity)

    def _csv(self, url: str, params: dict[str, Any]) -> str | None:
        """The CSV of one file, or None when the file has no sample on those days."""
        try:
            return self.http.get_text(url, params=params)
        except requests.HTTPError as error:
            response = error.response
            if (
                response is not None
                and response.status_code == requests.codes.bad_request
                and _NO_FEATURES in (response.text or "")
            ):
                log.info("no samples in %s between %s and %s", url, params["time_start"], params["time_end"])
                return None
            raise

    def _parts(self, folder: str, window: TimeWindow) -> list[_Part]:
        """The latest file for the days it covers, and the archive's monthly files for the days before."""
        latest = self._latest_file(folder)
        latest_start = self._coverage_start(latest)
        parts = []
        if window.start < latest_start:
            parts += self._monthly_parts(folder, window.start, min(window.end, latest_start - _DAY))
        if window.end >= latest_start:
            parts.append(_Part(latest, max(window.start, latest_start), window.end, "latest"))
        return parts

    def _monthly_parts(self, folder: str, first: date, last: date) -> list[_Part]:
        """Every archive file of the months between ``first`` and ``last``, cut to those days."""
        parts = []
        for year in range(first.year, last.year + 1):
            catalog = self._year_catalog(folder, year)
            for path, deployment, file_year, month in sorted(set(_MONTHLY_FILE.findall(catalog))):
                month_first = date(int(file_year), int(month), 1)
                month_last = month_first.replace(day=calendar.monthrange(month_first.year, month_first.month)[1])
                if month_last < first or month_first > last:
                    continue
                label = f"{file_year}-{month}_dep{deployment}"
                parts.append(_Part(path, max(first, month_first), min(last, month_last), label))
        return sorted(parts, key=lambda p: (p.first, p.label))

    def _year_catalog(self, folder: str, year: int) -> str:
        """The archive catalog of one year, empty for a year the station did not exist (404)."""
        try:
            return self.http.get_text(f"{self.config.options['thredds_url']}/catalog/{folder}/L1/{year}/catalog.xml")
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == requests.codes.not_found:
                return ""
            raise

    def _latest_file(self, folder: str) -> str:
        """Path of the newest deployment's ``*_latest.nc`` (highest ``depNNNN``)."""
        catalog = self.http.get_text(f"{self.config.options['thredds_url']}/catalog/{folder}/L1/catalog.xml")
        files = _LATEST_FILE.findall(catalog)
        if not files:
            msg = f"no *_latest.nc in SOCIB catalog {folder}/L1"
            raise ConnectorError(msg)
        return max(files, key=lambda match: int(match[1]))[0]

    def _coverage_start(self, path: str) -> date:
        """First day of a file, from its NcML."""
        metadata = self.http.get_text(f"{self.config.options['thredds_url']}/ncml/{path}")
        match = _COVERAGE_START.search(metadata)
        if match is None:
            msg = f"cannot read the time coverage of {path}"
            raise ConnectorError(msg)
        return datetime.fromisoformat(match.group(1)).date()
