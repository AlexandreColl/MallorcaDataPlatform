"""AEMET warnings connector: the Meteoalerta warnings of the region's zones, as an hourly level per phenomenon.

AEMET OpenData publishes its warnings in CAP (Common Alerting Protocol) XML, one file per zone and phenomenon, in two
ways, both behind the usual two-step call (``api_key`` header, then the ``datos`` URL):

* ``/avisos_cap/archivo/fechaini/.../fechafin/...``: every issue of the period for the whole of Spain. The answer is
  a tar with one ``.gz`` per issue (named after its time), and each of those is a gzipped tar with the CAP files in
  force at that time.
* ``/avisos_cap/ultimoelaborado/area/<area>``: the latest issue of one area, a tar with its CAP files.

**Every issue is a snapshot of the warnings in force.** A warning that is no longer in a later issue was withdrawn:
AEMET does not always send a ``Cancel`` or a green message for it. So the level of an hour comes from the snapshot in
force at that hour (the latest issue published before it): the level of its message for that zone and phenomenon,
or 0 when it has none. ``verde`` is 0, ``amarillo`` 1, ``naranja`` 2 and ``rojo`` 3.

``extract`` keeps the CAP files of the configured area (``*AFAZ64*`` for the Balearics) untouched, grouped by issue,
in the body of the bronze payload; the files of other areas are not stored. Each payload only writes its own hours,
so the datasets never overlap: ``archive`` the hours of its chunk of the window (reading the archive from
``lookback_days`` before, so the first hours have their snapshot), and ``latest`` the hours after the window, which
the next day's archive run settles with the snapshots that were really in force.
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator

_CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
_LEVELS = {"verde": 0, "amarillo": 1, "naranja": 2, "rojo": 3}
_HOUR = timedelta(hours=1)
_NO_DATA = 404
_ISSUE_TIME = re.compile(r"_(\d{14})_")  # Z_CAP_C_LEMM_20261102102407_AFAE.gz: issued at 2026-11-02 10:24:07 UTC


@dataclass(frozen=True)
class Zone:
    """A warning zone of AEMET (Meteoalerta): its polygon (lat, lon vertices) and the centre of it."""

    code: str
    name: str
    lat: float
    lon: float
    polygon: tuple[tuple[float, float], ...]

    def touches(self, region: Region) -> bool:
        """Whether any vertex lies in the region: coastal zones reach far out to sea, so their centre may not."""
        return any(region.contains(lat, lon) for lat, lon in self.polygon)


@dataclass(frozen=True)
class Message:
    """One CAP message for one zone: a phenomenon at one level between ``onset`` and ``expires``."""

    zone: Zone
    phenomenon: str
    level: int
    onset: datetime
    expires: datetime
    sent: datetime


def _vertices(polygon: str) -> tuple[tuple[float, float], ...]:
    """The vertices of a CAP polygon (``lat,lon lat,lon ...``)."""
    return tuple((float(lat), float(lon)) for lat, lon in (pair.split(",") for pair in polygon.split()))


def _value(block: ET.Element, tag: str, name: str) -> str | None:
    """The ``value`` of the ``eventCode``/``parameter``/``geocode`` called ``name``."""
    for item in block.iter(f"{_CAP}{tag}"):
        if item.findtext(f"{_CAP}valueName") == name:
            return item.findtext(f"{_CAP}value")
    return None


def parse_cap(xml: str) -> list[Message]:
    """The messages of one CAP file: one per zone of its Spanish ``info`` block. Empty if it is not a warning."""
    root = ET.fromstring(xml)  # noqa: S314 - AEMET's own files
    sent = datetime.fromisoformat(root.findtext(f"{_CAP}sent", "")).astimezone(UTC)
    cancelled = root.findtext(f"{_CAP}msgType") == "Cancel"
    messages = []
    for info in root.findall(f"{_CAP}info"):
        if info.findtext(f"{_CAP}language") != "es-ES":
            continue  # the English block repeats the same warning
        phenomenon = (_value(info, "eventCode", "AEMET-Meteoalerta fenomeno") or "").split(";")[0]
        level = _LEVELS.get(_value(info, "parameter", "AEMET-Meteoalerta nivel") or "")
        onset, expires = info.findtext(f"{_CAP}onset"), info.findtext(f"{_CAP}expires")
        if not phenomenon or level is None or not onset or not expires:
            continue
        for area in info.findall(f"{_CAP}area"):
            code, polygon = _value(area, "geocode", "AEMET-Meteoalerta zona"), area.findtext(f"{_CAP}polygon")
            if not code or not polygon:
                continue
            vertices = _vertices(polygon)
            zone = Zone(
                code=code,
                name=area.findtext(f"{_CAP}areaDesc", ""),
                lat=round(sum(v[0] for v in vertices) / len(vertices), 4),
                lon=round(sum(v[1] for v in vertices) / len(vertices), 4),
                polygon=vertices,
            )
            messages.append(
                Message(
                    zone=zone,
                    phenomenon=phenomenon,
                    level=0 if cancelled else level,
                    onset=datetime.fromisoformat(onset).astimezone(UTC),
                    expires=datetime.fromisoformat(expires).astimezone(UTC),
                    sent=sent,
                )
            )
    return messages


@dataclass(frozen=True)
class Snapshot:
    """The warnings in force after one issue, published at ``issued``."""

    issued: datetime
    messages: tuple[Message, ...]

    def level(self, zone: str, phenomenon: str, hour: datetime) -> int:
        """Highest level of this snapshot for the hour (a zone may have two messages, e.g. a day and an update)."""
        levels = [
            m.level
            for m in self.messages
            if m.zone.code == zone and m.phenomenon == phenomenon and m.onset <= hour < m.expires
        ]
        return max(levels, default=0)


def hourly_levels(snapshots: list[Snapshot], start: datetime, end: datetime) -> dict[tuple[Zone, str, datetime], int]:
    """Level of every zone and phenomenon of the snapshots, hour by hour in ``[start, end)``.

    Each hour takes the snapshot in force (the latest one issued before it). Hours before the first snapshot have
    no level: nothing says which warnings were in force then.
    """
    ordered = sorted(snapshots, key=lambda s: s.issued)
    if not ordered:
        return {}
    zones = {m.zone.code: m.zone for s in ordered for m in s.messages}
    pairs = sorted({(m.zone.code, m.phenomenon) for s in ordered for m in s.messages})
    levels: dict[tuple[Zone, str, datetime], int] = {}
    hour = max(start, ordered[0].issued.replace(minute=0, second=0, microsecond=0) + _HOUR)
    current = 0
    while hour < end:
        while current + 1 < len(ordered) and ordered[current + 1].issued <= hour:
            current += 1
        snapshot = ordered[current]
        for code, phenomenon in pairs:
            levels[(zones[code], phenomenon, hour)] = snapshot.level(code, phenomenon, hour)
        hour += _HOUR
    return levels


class AemetWarningsConnector(BaseConnector):
    """Hourly warning level per zone and phenomenon (rain, storms, wind, coast...) for the region's AEMET zones."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - zones are filtered in normalize
        """The archive of the window (plus the lookback days), by chunks, and the latest issue of the area."""
        options = self.config.options
        lookback = timedelta(days=int(options["lookback_days"]))
        payloads = []
        # Each chunk of the window reads the archive from `lookback` days before it and only writes its own hours.
        for chunk in window.split(int(options["max_days_per_request"])):
            path = (
                f"/avisos_cap/archivo/fechaini/{(chunk.start - lookback).isoformat()}T00:00:00UTC"
                f"/fechafin/{chunk.end.isoformat()}T23:59:59UTC"
            )
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="archive",
                    window=chunk,
                    request={"path": path, "area": options["area"]},
                    body=json.dumps(self._issues(self._fetch(path)), ensure_ascii=False, sort_keys=True),
                    partition=chunk.slug,  # one bronze object per archive request
                )
            )
        path = f"/avisos_cap/ultimoelaborado/area/{options['area']}"
        latest = self._area_files(self._fetch(path))
        payloads.append(
            RawPayload(
                source=self.name,
                dataset="latest",
                window=window,
                request={"path": path, "area": options["area"]},
                body=json.dumps({"latest": latest} if latest else {}, ensure_ascii=False, sort_keys=True),
            )
        )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per zone of the region, phenomenon and hour: the level in force at that hour."""
        issues: dict[str, dict[str, str]] = json.loads(payload.body or "{}")
        snapshots = []
        for issue, files in issues.items():
            messages = tuple(m for xml in files.values() for m in parse_cap(xml) if m.zone.touches(region))
            if not messages:
                continue
            found = _ISSUE_TIME.search(issue)
            # The latest issue has no archive name: it is in force since its newest message was sent.
            issued = (
                datetime.strptime(found.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                if found
                else max(m.sent for m in messages)
            )
            snapshots.append(Snapshot(issued, messages))
        if payload.dataset == "archive":
            start, end = payload.window.start_dt(), payload.window.end_dt_exclusive()
        else:  # the latest issue settles the hours after the window, up to its last warning
            start = payload.window.end_dt_exclusive()
            end = max((m.expires for s in snapshots for m in s.messages), default=start)
            snapshots = [Snapshot(min(s.issued, start), s.messages) for s in snapshots]
        phenomena: dict[str, str] = self.config.options.get("phenomena") or {}
        for (zone, phenomenon, hour), level in hourly_levels(snapshots, start, end).items():
            metric = self.config.metrics.get(phenomena.get(phenomenon, ""))
            if metric is None:
                continue  # a phenomenon this connector does not declare
            yield Observation(
                source=self.name,
                entity=zone.code,
                metric=metric.name,
                ts=hour,
                value=float(level),
                unit=metric.unit,
                quality=Quality.OK,
                lat=zone.lat,
                lon=zone.lon,
            )

    def _issues(self, archive: bytes) -> dict[str, dict[str, str]]:
        """The archive's issues (one ``.gz`` each), with the CAP files of the configured area of each one."""
        issues: dict[str, dict[str, str]] = {}
        if not archive:
            return issues
        with tarfile.open(fileobj=io.BytesIO(archive)) as outer:
            for issue in outer.getmembers():
                data = outer.extractfile(issue) if issue.isfile() else None
                if data is not None:
                    files = self._area_files(data.read(), mode="r:gz")
                    if files:
                        issues[issue.name.removeprefix("./")] = files
        return issues

    def _area_files(self, archive: bytes, mode: str = "r") -> dict[str, str]:
        """The CAP files of the configured area in a tar, by file name."""
        marker = f"AFAZ{self.config.options['area']}"
        files: dict[str, str] = {}
        if not archive:
            return files
        with tarfile.open(fileobj=io.BytesIO(archive), mode=mode) as tar:
            for member in tar.getmembers():
                if member.isfile() and marker in member.name and member.name.endswith(".xml"):
                    data = tar.extractfile(member)
                    if data is not None:
                        files[member.name.removeprefix("./")] = data.read().decode("utf-8")
        return files

    def _fetch(self, path: str) -> bytes:
        """Both AEMET steps: metadata with the key, then the tar. Empty when AEMET has no warnings for the period.

        Raises:
            ConnectorError: for any ``estado`` other than 200 or 404.
        """
        meta = self.http.get_json(
            f"{self.config.options['base_url']}{path}", headers={"api_key": self.secrets["AEMET_API_KEY"]}
        )
        if not isinstance(meta, dict):
            msg = f"unexpected AEMET answer for {path}"
            raise ConnectorError(msg)
        estado = int(meta.get("estado", 0))
        if estado == _NO_DATA:
            return b""
        if estado != 200 or not meta.get("datos"):  # noqa: PLR2004 - HTTP-like status in the body
            msg = f"AEMET estado {estado} for {path}: {meta.get('descripcion')}"
            raise ConnectorError(msg)
        return self.http.get_bytes(str(meta["datos"]))
