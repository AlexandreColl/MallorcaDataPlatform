"""Ibestat connector: the Human Pressure Indicator (IPH) of Mallorca, one value per day.

The IPH estimates the people actually present on an island each day: the registered residents plus the visitors
who arrived by sea or air minus the residents who are away. Ibestat serves it from its eDatos API (dataset
``000011A_000002``) as a flat cube: the dimensions (day, territory, measure) with the code and position of each of
their values, the observations as one ``" | "``-separated string in row-major order, and the status of each one
(``ESTADO_OBSERVACION``) in the same order.

``extract`` asks for the territories of the region and the days of the window only (``dim``), without the dataset
metadata (``fields=-metadata``): a year of Mallorca is about 20 KB instead of the 3 MB of the whole cube. The days
go in the URL, so a long window is split into requests of at most a year.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

_SEPARATOR = " | "
_TIME, _TERRITORY = "TIME_PERIOD", "TERRITORIO"
_STATUS = "ESTADO_OBSERVACION"


def _days(window: TimeWindow) -> list[str]:
    return [(window.start + timedelta(days=i)).isoformat() for i in range(window.n_days)]


class IbestatIphConnector(BaseConnector):
    """Daily Human Pressure Indicator of the islands inside the region (Ibestat)."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset and chunk of at most ``max_days_per_request`` days, for the region's islands.

        Raises:
            ConnectorError: if no configured territory lies in the region.
        """
        options = self.config.options
        territories = self._territories(region)
        if not territories:
            msg = f"no Ibestat territory configured inside region '{region.name}'"
            raise ConnectorError(msg)
        payloads = []
        for dataset, spec in self.config.datasets.items():
            url = f"{options['base_url']}/{spec['path']}/~latest.json"
            for chunk in window.split(int(options["max_days_per_request"])):
                dim = f"{_TERRITORY}:{'|'.join(territories)}:{_TIME}:{'|'.join(_days(chunk))}"
                params = {"dim": dim, "fields": "-metadata"}
                body = self.http.get_json(url, params=params)
                payloads.append(
                    RawPayload(
                        source=self.name,
                        dataset=dataset,
                        window=chunk,
                        request={"url": url, "params": params},
                        body=json.dumps(body, ensure_ascii=False),
                    )
                )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per island of the region and published day of the window.

        A day whose value and status are both blank is not published yet and yields nothing (the gaps rule reports
        it); a value with status O is a missing one.

        Raises:
            ConnectorError: if the answer is not an eDatos dataset or lacks the day or territory dimension.
        """
        options = self.config.options
        territories = self._territories(region)
        metric = self.config.metrics["human_pressure"]
        missing: set[str] = set(options["missing_status"])
        tz = ZoneInfo(str(options["timezone"]))
        cube = _Cube(json.loads(payload.body), payload.dataset)

        for day, territory, value, status in cube.cells():
            place = territories.get(territory)
            if place is None or not payload.window.start <= day <= payload.window.end:
                continue
            if value is None and status is None:  # not published yet
                continue
            quality = Quality.MISSING if value is None or status in missing else Quality.OK
            yield Observation(
                source=self.name,
                entity=str(place["entity"]),
                metric=metric.name,
                ts=datetime.combine(day, time(), tzinfo=tz),
                value=value if quality == Quality.OK else None,
                unit=metric.unit,
                quality=quality,
                lat=float(place["lat"]),
                lon=float(place["lon"]),
            )

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:  # noqa: ARG002 - names from config
        """The name of every island of the region, from ``connector.yaml``."""
        for place in self._territories(region).values():
            yield Entity(source=self.name, entity=str(place["entity"]), name=str(place["name"]))

    def _territories(self, region: Region) -> dict[str, Mapping[str, Any]]:
        """Configured territories (by code) whose centre is inside the region."""
        territories: Mapping[str, Mapping[str, Any]] = self.config.options["territories"]
        return {code: t for code, t in territories.items() if region.contains(float(t["lat"]), float(t["lon"]))}


class _Cube:
    """The ``data`` part of an eDatos dataset answer: dimensions, observations and their status."""

    def __init__(self, answer: Any, dataset: str) -> None:  # noqa: ANN401 - parsed JSON
        try:
            data = answer["data"]
            dimensions = data["dimensions"]["dimension"]
            self.codes = {
                d["dimensionId"]: {int(r["index"]): r["code"] for r in d["representations"]["representation"]}
                for d in dimensions
            }
            self.order = [d["dimensionId"] for d in dimensions]
            self.values = str(data["observations"]).split(_SEPARATOR)
            attributes = (data.get("attributes") or {}).get("attribute") or []
        except (KeyError, TypeError) as exc:
            msg = f"ibestat_iph {dataset}: not an eDatos dataset ({exc!r}): {str(answer)[:200]}"
            raise ConnectorError(msg) from exc
        if _TIME not in self.codes or _TERRITORY not in self.codes:
            msg = f"ibestat_iph {dataset}: no {_TIME} or {_TERRITORY} dimension in {self.order}"
            raise ConnectorError(msg)
        status = next((a["value"] for a in attributes if a.get("id") == _STATUS), "")
        self.status = str(status).split(_SEPARATOR) if status else []
        self.dataset = dataset

    def cells(self) -> Iterator[tuple[date, str, float | None, str | None]]:
        """Every (day, territory, value, status), with blanks as None. Other dimensions must have one value."""
        sizes = [len(self.codes[d]) for d in self.order]
        strides = [1] * len(sizes)
        for i in range(len(sizes) - 2, -1, -1):
            strides[i] = strides[i + 1] * sizes[i + 1]
        if len(self.values) != strides[0] * sizes[0]:
            msg = f"ibestat_iph {self.dataset}: {len(self.values)} observations for dimensions of size {sizes}"
            raise ConnectorError(msg)
        t, g = self.order.index(_TIME), self.order.index(_TERRITORY)
        for day_index, day in self.codes[_TIME].items():
            for territory_index, territory in self.codes[_TERRITORY].items():
                at = day_index * strides[t] + territory_index * strides[g]
                raw = self.values[at].strip()
                status = self.status[at].strip() if at < len(self.status) else ""
                yield date.fromisoformat(day), territory, float(raw) if raw else None, status or None
