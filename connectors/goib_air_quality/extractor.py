"""GOIB air quality connector: the hourly history of the official stations of Mallorca (2002 to June 2021).

The Govern open data catalogue (CKAN) publishes one CSV per station with its measurements since 2002, up to
November 2019, plus one per station for 2020 and for the first half of 2021. Nothing newer is published there:
the live feed is ``eea_air_quality``, with the same entity names, so a station is one series across both.

``extract`` asks ``package_show`` for the CSV of every dataset whose years overlap the window and keeps, untouched,
the header and the lines of the window's days (one file holds up to 18 years, so a yearly backfill would otherwise
store it 18 times); the request records the SHA-256 of the whole file. ``normalize`` reads them:

* the files differ in the delimiter (``;`` or ``,``) and the date (``01/22/2016 12:00:00 AM`` or ``22/01/2016``);
* period 1-24 of each day is the hour starting at that time in fixed UTC+01, so period 1 is 00:00 UTC;
* only the ``V`` flag is valid: any other flag, or an empty value, is stored as ``missing``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

# A backfill loads the connector again for every chunk, and each history file spans up to 18 yearly chunks: the
# files are downloaded once per process.
_DOWNLOADS: dict[str, bytes] = {}


class GoibAirQualityConnector(BaseConnector):
    """Hourly NO2, O3, PM10, PM2.5, SO2 and CO of the official air quality stations in the region, 2002-2021."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Download the station files that overlap the window and keep the lines of its days.

        Raises:
            ConnectorError: if no configured station lies in the region or no file overlaps the window.
        """
        options = self.config.options
        stations = self._stations(region)
        if not stations:
            msg = f"no GOIB air quality station configured inside region '{region.name}'"
            raise ConnectorError(msg)
        payloads = []
        for entity, station in stations.items():
            for suffix in station.get("files", list(options["files"])):
                years = options["files"][suffix]
                if window.end.year < int(years["first_year"]) or window.start.year > int(years["last_year"]):
                    continue
                dataset_name = f"{options['dataset_prefix']}{station['slug']}{suffix}"
                url = self._csv_url(dataset_name)
                content = self._download(url)
                text = content.decode("utf-8-sig")
                lines = _lines_in_window(text, window)
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset="hourly",
                        window=window,
                        request={
                            "dataset": dataset_name,
                            "url": url,
                            "entity": entity,
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "bytes": len(content),
                            "lines": len(lines) - 1,
                        },
                        body="".join(lines),
                        partition=f"{entity}{suffix}",
                    )
                )
        if not payloads:
            msg = f"the GOIB history (2002 to June 2021) has no file for {window.start}..{window.end}"
            raise ConnectorError(msg)
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - coords from config
        """One observation per hour and pollutant of the window.

        Raises:
            ConnectorError: if the file has none of the configured pollutant columns (a changed layout).
        """
        options = self.config.options
        spec = self.config.datasets[payload.dataset]
        station = options["stations"][payload.request["entity"]]
        offset = timedelta(hours=int(options["utc_offset_hours"]))
        valid_flag = str(options["valid_flag"])
        window_start, window_end = payload.window.start_dt(), payload.window.end_dt_exclusive()

        reader = _reader(payload.body)
        header = next(reader, [])
        index = {name.strip(): i for i, name in enumerate(header)}
        columns = {
            column: (index[f"{column}_HI"], index[f"FL_{column}"], column_spec)
            for column, column_spec in spec["columns"].items()
            if f"{column}_HI" in index and f"FL_{column}" in index
        }
        if not columns:
            msg = f"GOIB {payload.partition}: none of the columns {sorted(spec['columns'])} in the header"
            raise ConnectorError(msg)
        for row in reader:
            if len(row) < len(header):
                continue
            ts = datetime.combine(_day(row[0]), datetime.min.time(), tzinfo=UTC) + timedelta(hours=int(row[1])) - offset
            if not window_start <= ts < window_end:
                continue
            for value_at, flag_at, column_spec in columns.values():
                metric = self.config.metrics[column_spec["metric"]]
                value = _number(row[value_at]) if row[flag_at].strip() == valid_flag else None
                if value is not None:
                    value = round(value * float(column_spec.get("scale", 1)), 3)
                yield Observation(
                    source=self.name,
                    entity=payload.request["entity"],
                    metric=metric.name,
                    ts=ts,
                    value=value,
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=float(station["lat"]),
                    lon=float(station["lon"]),
                )

    def _stations(self, region: Region) -> dict[str, Mapping[str, Any]]:
        """Configured stations (by entity) inside the region."""
        stations: Mapping[str, Mapping[str, Any]] = self.config.options["stations"]
        return {e: s for e, s in stations.items() if region.contains(float(s["lat"]), float(s["lon"]))}

    def _csv_url(self, dataset_name: str) -> str:
        """URL of the CSV resource of a catalogue dataset.

        Raises:
            ConnectorError: if the dataset has no CSV resource.
        """
        response = self.http.get_json(self.config.options["catalog_url"], params={"id": dataset_name})
        resources = response["result"]["resources"]  # type: ignore[index, call-overload]
        for resource in resources:
            if str(resource.get("format", "")).upper() == "CSV":
                return str(resource["url"])
        msg = f"GOIB dataset {dataset_name} has no CSV resource"
        raise ConnectorError(msg)

    def _download(self, url: str) -> bytes:
        if url not in _DOWNLOADS:
            _DOWNLOADS[url] = self.http.get_bytes(url)
            log.info("downloaded %s (%d bytes)", url, len(_DOWNLOADS[url]))
        return _DOWNLOADS[url]


def _reader(text: str) -> Iterator[list[str]]:
    """CSV rows with the file's own delimiter: ``;`` in some files, ``,`` (with a quoted "PM2,5") in others."""
    first_line = text.split("\n", 1)[0]
    return csv.reader(io.StringIO(text), delimiter=";" if ";" in first_line else ",")


def _lines_in_window(text: str, window: TimeWindow) -> list[str]:
    """The header and the raw lines whose day falls in the window (all their hours do, see ``utc_offset_hours``)."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    delimiter = ";" if ";" in lines[0] else ","
    kept = [lines[0]]
    for line in lines[1:]:
        try:
            day = _day(line.split(delimiter, 1)[0])
        except ValueError:
            continue
        if window.start <= day <= window.end:
            kept.append(line)
    return kept


def _day(raw: str) -> date:
    """``01/22/2016 12:00:00 AM`` (month first, the history files) or ``22/01/2016`` (day first, the others).

    Raises:
        ValueError: for any other format.
    """
    raw = raw.strip()
    if raw.endswith(("AM", "PM")):
        return datetime.strptime(raw.split(" ", 1)[0], "%m/%d/%Y").date()  # noqa: DTZ007 - a calendar day
    return datetime.strptime(raw, "%d/%m/%Y").date()  # noqa: DTZ007 - a calendar day


def _number(raw: str) -> float | None:
    """Decimal point values; a comma is a thousands separator (pressure ``1,010``). Empty means no value."""
    raw = raw.strip().replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
