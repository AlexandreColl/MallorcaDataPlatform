"""EEA air quality connector: hourly pollutants of the official stations of Mallorca.

The EEA Air Quality Download Service answers a JSON search (country, pollutants, dates) with the URLs of one
Parquet file per sampling point (a station and a pollutant), each holding the year so far, about two hours behind
real time. ``extract`` keeps the files of the stations listed in ``connector.yaml`` and stores each one untouched in
bronze (base64, with its SHA-256). ``normalize`` reads the Parquet with pyarrow, keeps the hours of the window and
converts them to the common schema:

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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_POLLUTANT_URI = "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/{code}"
_SAMPLING_POINT = re.compile(r"/SP_(?P<station>\d+)_(?P<rest>[^/]+)\.parquet$")


class EeaAirQualityConnector(BaseConnector):
    """Hourly NO2, O3, PM10, PM2.5, SO2 and CO of the official air quality stations in the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Search the files of the window and download those of the configured stations inside the region.

        Raises:
            ConnectorError: if no configured station lies in the region or the search returns none of their files.
        """
        options = self.config.options
        stations = self._stations(region)
        if not stations:
            msg = f"no EEA air quality station configured inside region '{region.name}'"
            raise ConnectorError(msg)
        search = {
            "countries": [options["country"]],
            "cities": [],
            "pollutants": [_POLLUTANT_URI.format(code=c) for c in self.config.datasets["hourly"]["pollutants"]],
            "dataset": int(options["dataset"]),
            "source": "API",
            "dateTimeStart": f"{window.start.isoformat()}T00:00:00Z",
            "dateTimeEnd": f"{window.end.isoformat()}T23:59:59Z",
            "aggregationType": "hour",
        }
        listing = self.http.post_text(f"{options['api_url']}/ParquetFile/urls", json=search)
        urls = [line.strip() for line in listing.splitlines() if line.strip().startswith("http")]
        payloads = []
        unknown: set[str] = set()
        for url in urls:
            match = _SAMPLING_POINT.search(url)
            if match is None:
                continue
            code = match["station"]
            if code not in stations:
                if code.startswith(str(options["province_code"])):
                    unknown.add(code)
                continue
            archive = self.http.get_bytes(url)
            sampling_point = f"{code}_{match['rest']}"
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="hourly",
                    window=window,
                    request={
                        "url": url,
                        "station": code,
                        "sha256": hashlib.sha256(archive).hexdigest(),
                        "bytes": len(archive),
                    },
                    body=base64.b64encode(archive).decode("ascii"),
                    partition=sampling_point,
                )
            )
        if unknown:
            log.warning("EEA Balearic stations not in connector.yaml (ignored): %s", sorted(unknown))
        if not payloads:
            msg = f"EEA search returned no file of the configured stations for {window.start}..{window.end}"
            raise ConnectorError(msg)
        return payloads

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
