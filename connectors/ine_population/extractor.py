"""INE connector: population of the municipalities of Mallorca from the continuous municipal register (padrón).

INE's Tempus API serves table 2860 ("Balears, Illes: Población por municipios y sexo") as JSON: one series per
municipality and sex, each with one value per year on 1 January. The answer for the years of the window is stored
untouched in bronze. ``normalize`` keeps the municipalities of the region (their codes and centres are in the YAML)
and writes one observation per municipality, sex and year, stamped on 1 January at local midnight.

The table also holds the Balearic total, which is left out: Mallorca's total is the sum of its municipalities, so
gold computes it and it never double counts.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class InePopulationConnector(BaseConnector):
    """Yearly population of each municipality of Mallorca, by sex (INE, padrón continuo)."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - filtered in normalize
        """One request per dataset for the years between the window's start and end, with the series metadata."""
        options = self.config.options
        payloads = []
        for dataset, spec in self.config.datasets.items():
            url = f"{options['base_url']}/{spec['path']}"
            # tip=AM adds each series' metadata (the INE code of its municipality); date limits the years.
            params = {"tip": "AM", "date": f"{window.start:%Y%m%d}:{window.end:%Y%m%d}"}
            body = self.http.get_json(url, params=params)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset=dataset,
                    window=window,
                    request={"url": url, "params": params},
                    body=json.dumps(body, ensure_ascii=False),
                )
            )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per municipality of the region, sex and year whose 1 January falls inside the window.

        Raises:
            ConnectorError: if the answer is not a list of series, or none of them is a municipality.
        """
        options = self.config.options
        series = json.loads(payload.body)
        if not isinstance(series, list):
            msg = f"ine_population {payload.dataset}: unexpected answer {str(series)[:200]}"
            raise ConnectorError(msg)
        municipalities: Mapping[str, Mapping[str, Any]] = options["municipalities"]
        sexes: Mapping[str, str] = options["sexes"]
        tz = ZoneInfo(str(options["timezone"]))
        years = {d.year for d in payload.window.year_starts()}

        found = False
        for item in series:
            meta = {m["T3_Variable"]: m.get("Codigo") for m in item.get("MetaData") or []}
            code, sex = meta.get("Municipios"), meta.get("Sexo")
            if code is None:  # the Balearic total
                continue
            found = True
            place = municipalities.get(code)
            if place is None or sex not in sexes or not region.contains(place["lat"], place["lon"]):
                continue  # another island, or a dimension value the connector does not map
            metric = self.config.metrics[sexes[sex]]
            for point in item.get("Data") or []:
                year = int(point["Anyo"])
                if year not in years:
                    continue
                value = point.get("Valor")
                yield Observation(
                    source=self.name,
                    entity=code,
                    metric=metric.name,
                    ts=datetime.combine(date(year, 1, 1), time(), tzinfo=tz),
                    value=float(value) if value is not None else None,
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=float(place["lat"]),
                    lon=float(place["lon"]),
                )
        if not found:
            msg = f"ine_population {payload.dataset}: no municipal series in the answer; check the table id"
            raise ConnectorError(msg)
