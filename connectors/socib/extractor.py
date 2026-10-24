"""SOCIB connector: THREDDS NetCDF Subset Service (CSV, no API key) aggregated to hourly values.

Per station: resolve the current deployment's ``*_latest.nc`` from the THREDDS catalog, check that it covers
the requested window, then download the raw 1-10 minute samples with their SOCIB QC flags. ``normalize``
averages the samples the source marks as good into hourly values and labels an hour ``suspect`` when too
few of its samples are good.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import fmean
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_LATEST_FILE = re.compile(r'urlPath="([^"]*?dep(\d+)_[^"]*_latest\.nc)"')
_COVERAGE_BEGIN = re.compile(r"<begin>([^<]+)</begin>")


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
    """Hourly weather observations from SOCIB stations and buoys inside the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One CSV request per station with every configured variable and its QC flag.

        Raises:
            ConnectorError: if no station lies in the region, a station has no current file, or the file
                does not cover the window.
        """
        options = self.config.options
        variables = list(self.config.datasets["weather"]["variables"])
        requested = [name for var in variables for name in (var, f"QC_{var}")]
        payloads = []
        for station in self._stations(region):
            path = self._latest_file(station["folder"])
            self._check_coverage(path, window)
            url = f"{options['thredds_url']}/ncss/{path}"
            params: dict[str, Any] = {
                "var": requested,
                "time_start": f"{window.start.isoformat()}T00:00:00Z",
                "time_end": f"{window.end.isoformat()}T23:59:59Z",
                "accept": "csv",
            }
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="weather",
                    window=window,
                    request={"url": url, "params": params, "station": station["entity"]},
                    body=self.http.get_text(url, params=params),
                    partition=station["entity"],
                )
            )
        return payloads

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
        return next(s for s in self.config.options["stations"] if s["entity"] == entity)

    def _latest_file(self, folder: str) -> str:
        """Path of the newest deployment's ``*_latest.nc`` (highest ``depNNNN``)."""
        catalog = self.http.get_text(f"{self.config.options['thredds_url']}/catalog/{folder}/L1/catalog.xml")
        files = _LATEST_FILE.findall(catalog)
        if not files:
            msg = f"no *_latest.nc in SOCIB catalog {folder}/L1"
            raise ConnectorError(msg)
        return max(files, key=lambda match: int(match[1]))[0]

    def _check_coverage(self, path: str, window: TimeWindow) -> None:
        metadata = self.http.get_text(f"{self.config.options['thredds_url']}/ncss/{path}/dataset.xml")
        match = _COVERAGE_BEGIN.search(metadata)
        if match is None:
            msg = f"cannot read the time coverage of {path}"
            raise ConnectorError(msg)
        first_day = datetime.fromisoformat(match.group(1)).date()
        if window.start < first_day:
            available = (window.end - first_day).days + 1
            msg = f"SOCIB {path} starts on {first_day}; request at most {available} days (got {window.n_days})"
            raise ConnectorError(msg)
