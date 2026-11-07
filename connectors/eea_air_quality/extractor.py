"""EEA air quality connector: hourly pollutants of the official stations of Mallorca.

The EEA Air Quality Download Service answers a JSON search (country, pollutants, dates) with the URLs of one
Parquet file per sampling point (a station and a pollutant). There are two datasets, and each year is in only one:

* up-to-date (E2a, dataset 1): the current year so far, unverified, about two hours behind real time;
* verified (E1a, dataset 2): every previous year the network has validated, 2013 onwards for Mallorca, in one file
  per sampling point. The EEA publishes a year in the autumn of the next one: until then it is in neither.

``extract`` searches the dataset of each year of the window and downloads the files of the stations listed in
``connector.yaml``. Bronze keeps each file's rows of the window, unchanged, as Parquet (base64), with the SHA-256 and
size of the whole file: a verified file holds thirteen years. ``normalize`` reads the Parquet with pyarrow and
converts it to the common schema:

* timestamps are fixed UTC+01 in the Spanish files (the EEA "Timezone"), so 10:00-11:00 is 09:00 UTC;
* values are stored in ug/m3 like Open-Meteo (CO comes in mg/m3);
* rows the source marks as not valid (validity -1, -99) carry a -999 sentinel: they are kept as ``missing``.

OpenAQ republishes the same stations but, for Mallorca, only about 30 % of the hours: this is the original feed.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError, SourceNotUpdatedError
from core.models import Entity, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_POLLUTANT_URI = "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/{code}"
_SAMPLING_POINT = re.compile(r"/SP_(?P<station>\d+)_(?P<rest>[^/]+)\.parquet$")
_UP_TO_DATE = 1
_VERIFIED = 2

# Verified files only change once a year: a backfill reads the same ones for every chunk, so they are downloaded
# once per process. Up-to-date files change every hour and are never cached.
_VERIFIED_FILES: dict[str, bytes] = {}


def _current_year() -> int:
    return datetime.now(UTC).year


class EeaAirQualityConnector(BaseConnector):
    """Hourly NO2, O3, PM10, PM2.5, SO2 and CO of the official air quality stations in the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Search the files of the window and download those of the configured stations inside the region.

        Raises:
            ConnectorError: if no configured station lies in the region or the search returns none of their files.
            SourceNotUpdatedError: if the window has no rows and every file ends before it (the EEA is late).
        """
        options = self.config.options
        stations = self._stations(region)
        if not stations:
            msg = f"no EEA air quality station configured inside region '{region.name}'"
            raise ConnectorError(msg)
        payloads = []
        unknown: set[str] = set()
        latest: list[datetime] = []  # last hour of each file, to tell a stale source from an empty window
        for dataset, part in _parts(window, _current_year()):
            search = {
                "countries": [options["country"]],
                "cities": [],
                "pollutants": [_POLLUTANT_URI.format(code=c) for c in self.config.datasets["hourly"]["pollutants"]],
                "dataset": dataset,
                "source": "API",
                "dateTimeStart": f"{part.start.isoformat()}T00:00:00Z",
                "dateTimeEnd": f"{part.end.isoformat()}T23:59:59Z",
                "aggregationType": "hour",
            }
            listing = self.http.post_text(f"{options['api_url']}/ParquetFile/urls", json=search)
            urls = [line.strip() for line in listing.splitlines() if line.strip().startswith("http")]
            for url in urls:
                match = _SAMPLING_POINT.search(url)
                if match is None:
                    continue
                code = match["station"]
                if code not in stations:
                    if code.startswith(str(options["province_code"])):
                        unknown.add(code)
                    continue
                archive = self._download(url, verified=dataset == _VERIFIED)
                rows, in_window, last = self._rows_of(archive, part)
                if last is not None:
                    latest.append(last)
                sampling_point = f"{code}_{match['rest']}"
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset="hourly",
                        window=window,
                        request={
                            "url": url,
                            "station": code,
                            "dataset": dataset,
                            "sha256": hashlib.sha256(archive).hexdigest(),
                            "bytes": len(archive),
                            "rows": in_window,
                        },
                        body=base64.b64encode(rows).decode("ascii"),
                        # A window across New Year has the same sampling point in both datasets.
                        partition=sampling_point if dataset == _UP_TO_DATE else f"{sampling_point}_verified",
                    )
                )
        if unknown:
            log.warning("EEA Balearic stations not in connector.yaml (ignored): %s", sorted(unknown))
        _check_found(payloads, latest, window)
        return payloads

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:  # noqa: ARG002 - names from config
        """The name of the payload's station, from ``connector.yaml``."""
        station = self.config.options["stations"][payload.request["station"]]
        yield Entity(source=self.name, entity=str(station["entity"]), name=str(station["name"]))

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - coords from config
        """One observation per hour of the window in the sampling point's file.

        Raises:
            ConnectorError: for a unit the connector does not know (it would silently mix scales).
        """
        import pyarrow.parquet as pq  # noqa: PLC0415 - only this connector reads Parquet

        spec = self.config.datasets[payload.dataset]
        options = self.config.options
        station = options["stations"][payload.request["station"]]
        offset = timedelta(hours=int(options["utc_offset_hours"]))
        min_validity = int(options["min_validity"])
        window_start, window_end = payload.window.start_dt(), payload.window.end_dt_exclusive()

        table = pq.read_table(io.BytesIO(base64.b64decode(payload.body)))
        columns = ["Pollutant", "Start", "Value", "Unit", "Validity"]
        rows = table.select(columns).to_pylist()
        for row in rows:
            pollutant = spec["pollutants"].get(str(row["Pollutant"]))
            if pollutant is None:
                continue
            ts = _utc(row["Start"]) - offset
            if not window_start <= ts < window_end:
                continue
            scale = spec["units"].get(row["Unit"])
            if scale is None:
                msg = f"EEA {payload.partition}: unknown unit '{row['Unit']}'"
                raise ConnectorError(msg)
            metric = self.config.metrics[pollutant["metric"]]
            valid = row["Validity"] is not None and int(row["Validity"]) >= min_validity
            value = _number(row["Value"]) if valid else None  # not valid: a -999 sentinel, never a measurement
            quality = Quality.OK if value is not None else Quality.MISSING
            yield Observation(
                source=self.name,
                entity=str(station["entity"]),
                metric=metric.name,
                ts=ts,
                value=round(value * float(scale), 3) if value is not None else None,
                unit=metric.unit,
                quality=quality,
                lat=float(station["lat"]),
                lon=float(station["lon"]),
            )

    def _stations(self, region: Region) -> dict[str, Mapping[str, Any]]:
        """Configured stations (by national code) inside the region."""
        stations: Mapping[str, Mapping[str, Any]] = self.config.options["stations"]
        return {code: s for code, s in stations.items() if region.contains(float(s["lat"]), float(s["lon"]))}

    def _download(self, url: str, *, verified: bool) -> bytes:
        if not verified:
            return self.http.get_bytes(url)
        if url not in _VERIFIED_FILES:
            _VERIFIED_FILES[url] = self.http.get_bytes(url)
            log.info("downloaded %s (%d bytes)", url, len(_VERIFIED_FILES[url]))
        return _VERIFIED_FILES[url]

    def _rows_of(self, archive: bytes, part: TimeWindow) -> tuple[bytes, int, datetime | None]:
        """The file's rows whose hour starts inside the window part, as Parquet with the file's own columns.

        Returns:
            The Parquet, its number of rows and the start of the file's last hour in UTC (None for an empty file).
        """
        import pyarrow as pa  # noqa: PLC0415 - only this connector reads Parquet
        import pyarrow.compute as pc  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        offset = timedelta(hours=int(self.config.options["utc_offset_hours"]))
        table = pq.read_table(io.BytesIO(archive))
        # File times are local (UTC+01) without a zone: compare them with the window's bounds in local time.
        start, end = ((t + offset).replace(tzinfo=None) for t in (part.start_dt(), part.end_dt_exclusive()))
        unit = table.schema.field("Start").type
        inside = pc.and_(
            pc.greater_equal(table["Start"], pa.scalar(start, unit)), pc.less(table["Start"], pa.scalar(end, unit))
        )
        kept = table.filter(inside)
        buffer = io.BytesIO()
        pq.write_table(kept, buffer)
        last = pc.max(table["Start"]).as_py()
        return buffer.getvalue(), kept.num_rows, _utc(last) - offset if last is not None else None


def _check_found(payloads: list[RawPayload], latest: list[datetime], window: TimeWindow) -> None:
    """Fail when the search found nothing, or when every file ends before the window (a stale source).

    Raises:
        ConnectorError: no file of the configured stations.
        SourceNotUpdatedError: no row in the window and every file ends before it.
    """
    if not payloads:
        msg = f"EEA search returned no file of the configured stations for {window.start}..{window.end}"
        raise ConnectorError(msg)
    if latest and not any(p.request["rows"] for p in payloads) and max(latest) < window.start_dt():
        msg = f"EEA files end at {max(latest):%Y-%m-%d %H:%M} UTC, before {window.start}: not updated yet"
        raise SourceNotUpdatedError(msg)


def _parts(window: TimeWindow, current_year: int) -> list[tuple[int, TimeWindow]]:
    """The window split by dataset: days before the current year are only in the verified files."""
    new_year = date(current_year, 1, 1)
    parts = []
    if window.start < new_year:
        parts.append((_VERIFIED, TimeWindow(window.start, min(window.end, new_year - timedelta(days=1)))))
    if window.end >= new_year:
        parts.append((_UP_TO_DATE, TimeWindow(max(window.start, new_year), window.end)))
    return parts


def _utc(start: datetime) -> datetime:
    """A plain ``datetime`` in UTC: nanosecond columns come as ``pandas.Timestamp``, which Spark does not accept."""
    return datetime(*start.timetuple()[:6], tzinfo=UTC)


def _number(raw: object) -> float | None:
    """EEA values come as decimal strings (or numbers); empty means no value."""
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw))
    except ValueError:
        return None
