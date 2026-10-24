"""AEMET connector: daily climatological values of the official stations inside the region.

AEMET OpenData answers every request in two steps: the first call (with the ``api_key`` header) returns a
small JSON with ``estado`` and a temporary ``datos`` URL, and the data itself is downloaded from that URL
(JSON encoded as ISO-8859-15). ``estado`` 404 means "no data for those criteria", which is how AEMET answers
for days it has not published yet.

Per window: the station inventory (to find the stations inside the region and their coordinates, which the
daily values do not carry) and one request per chunk of at most 6 months and group of at most 25 stations
(the API limits). The hourly observation endpoint is not used: it only covers the last hours, never a complete past day.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

log = logging.getLogger(__name__)

_INVENTORY = "/valores/climatologicos/inventarioestaciones/todasestaciones"
_NO_DATA = 404
_TRACE = "Ip"  # precipitation below 0.1 mm


def _dms(raw: str) -> float:
    """``394924N`` / ``025309E`` (degrees, minutes, seconds and hemisphere) as decimal degrees."""
    digits, hemisphere = raw[:-1], raw[-1]
    value = int(digits[:-4]) + int(digits[-4:-2]) / 60 + int(digits[-2:]) / 3600
    return round(-value if hemisphere in {"S", "W"} else value, 6)


def _number(raw: str | None) -> float | None:
    """AEMET numbers are strings with a decimal comma; ``Ip`` is a trace of rain; text such as ``Varias`` is null."""
    if raw is None:
        return None
    text = raw.strip()
    if text == _TRACE:
        return 0.0
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


class AemetConnector(BaseConnector):
    """Daily temperature, rain, humidity, wind, sunshine and pressure of AEMET stations in the region."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Inventory plus one daily-values request per chunk with every station of the region.

        Raises:
            ConnectorError: if no station lies in the region or AEMET answers with an error.
        """
        inventory = self._fetch(_INVENTORY)
        stations = self._stations_in(inventory, region)
        payloads = [
            RawPayload(
                source=self.name, dataset="stations", window=window, request={"path": _INVENTORY}, body=inventory
            )
        ]
        ids = sorted(stations)
        size = int(self.config.options["max_stations_per_request"])
        groups = [ids[i : i + size] for i in range(0, len(ids), size)]
        for chunk in window.split(int(self.config.options["max_days_per_request"])):
            for group in groups:
                path = (
                    f"/valores/climatologicos/diarios/datos/fechaini/{chunk.start.isoformat()}T00:00:00UTC"
                    f"/fechafin/{chunk.end.isoformat()}T23:59:59UTC/estacion/{','.join(group)}"
                )
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset="daily",
                        window=chunk,
                        request={"path": path, "stations": {i: stations[i] for i in group}},
                        body=self._fetch(path),
                        partition=f"{group[0]}-{group[-1]}",  # one bronze object per station group
                    )
                )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - stations were filtered in extract
        """One observation per station, day and variable the station reports."""
        if payload.dataset != "daily":
            return
        variables: Mapping[str, Mapping[str, Any]] = self.config.datasets["daily"]["variables"]
        stations: Mapping[str, Mapping[str, Any]] = payload.request["stations"]
        tz = ZoneInfo(str(self.config.options["timezone"]))
        for record in json.loads(payload.body or "[]"):
            station = stations.get(record.get("indicativo", ""))
            if station is None:
                continue
            ts = datetime.combine(date.fromisoformat(record["fecha"]), time(), tzinfo=tz)
            for field, spec in variables.items():
                if field not in record:  # the station does not measure it (e.g. sunshine)
                    continue
                metric = self.config.metrics[spec["metric"]]
                value = _number(record[field])
                if value is not None:
                    value = round(value * float(spec.get("scale", 1)), 3)
                yield Observation(
                    source=self.name,
                    entity=record["indicativo"],
                    metric=metric.name,
                    ts=ts,
                    value=value,
                    unit=metric.unit,
                    quality=Quality.MISSING if value is None else Quality.OK,
                    lat=float(station["lat"]),
                    lon=float(station["lon"]),
                )

    def _fetch(self, path: str) -> str:
        """Both AEMET steps: metadata call with the key, then the data URL. ``[]`` when AEMET has no data.

        Raises:
            ConnectorError: for any ``estado`` other than 200 or 404 (bad key, rate limit, bad request).
        """
        meta = self.http.get_json(
            f"{self.config.options['base_url']}{path}", headers={"api_key": self.secrets["AEMET_API_KEY"]}
        )
        if not isinstance(meta, dict):
            msg = f"unexpected AEMET answer for {path}"
            raise ConnectorError(msg)
        estado = int(meta.get("estado", 0))
        if estado == _NO_DATA:
            log.warning("AEMET has no data yet for %s (%s)", path, meta.get("descripcion"))
            return "[]"
        if estado != 200 or not meta.get("datos"):  # noqa: PLR2004 - HTTP-like status in the body
            msg = f"AEMET estado {estado} for {path}: {meta.get('descripcion')}"
            raise ConnectorError(msg)
        return self.http.get_text(str(meta["datos"]))

    @staticmethod
    def _stations_in(inventory: str, region: Region) -> dict[str, dict[str, Any]]:
        """Stations of the inventory inside the region's bounding box, by station id.

        Raises:
            ConnectorError: if there are none.
        """
        stations = {}
        for row in json.loads(inventory):
            lat, lon = _dms(row["latitud"]), _dms(row["longitud"])
            if region.contains(lat, lon):
                stations[row["indicativo"]] = {
                    "name": row["nombre"],
                    "lat": lat,
                    "lon": lon,
                    "altitude": row["altitud"],
                }
        if not stations:
            msg = f"no AEMET station inside region '{region.name}'"
            raise ConnectorError(msg)
        return stations
