"""INE connector: tourist dwellings in the municipalities of Mallorca (experimental statistic of tourist housing).

The INE counts the dwellings listed on the main holiday rental platforms in one reference month, twice a year, and
publishes them in table 39363 of its Tempus API: three series per municipality ("Viviendas turísticas", "Plazas" and
"Plazas por vivienda turística"), each with one value per reference month. The table covers every municipality of
Spain, so the request asks for the municipalities of Mallorca only, with one ``tv`` filter per municipality (their
INE value ids are in the YAML). The answer is stored untouched in bronze; ``normalize`` writes one observation per
municipality, concept and reference month, stamped on the first day of that month at local midnight.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# Tempus id of the "Municipios" variable, the one the tv filter of the request uses.
MUNICIPALITY_VARIABLE = 19
# Period of a monthly data point (M01..M12).
MONTH_PERIOD = re.compile(r"^M(0[1-9]|1[0-2])$")


class IneTouristHousingConnector(BaseConnector):
    """Tourist dwellings, their beds and beds per dwelling in each municipality of Mallorca (INE, experimental)."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset for the months of the window, filtered to the municipalities of the region."""
        options = self.config.options
        municipalities: Mapping[str, Mapping[str, Any]] = options["municipalities"]
        filters = [
            f"{MUNICIPALITY_VARIABLE}:{place['ine_id']}"
            for place in municipalities.values()
            if region.contains(place["lat"], place["lon"])
        ]
        payloads = []
        for dataset, spec in self.config.datasets.items():
            url = f"{options['base_url']}/{spec['path']}"
            # tip=AM adds each series' metadata (municipality code and concept); date limits the reference months.
            params: dict[str, str | list[str]] = {
                "tip": "AM",
                "date": f"{window.start:%Y%m%d}:{window.end:%Y%m%d}",
                "tv": filters,
            }
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
        """One observation per municipality of the region, concept and reference month inside the window.

        Raises:
            ConnectorError: if the answer is not a list of series, none of them is a municipality, or a data point
                is not monthly.
        """
        options = self.config.options
        series = json.loads(payload.body)
        if not isinstance(series, list):
            msg = f"ine_tourist_housing {payload.dataset}: unexpected answer {str(series)[:200]}"
            raise ConnectorError(msg)
        municipalities: Mapping[str, Mapping[str, Any]] = options["municipalities"]
        concepts: Mapping[str, str] = options["concepts"]
        tz = ZoneInfo(str(options["timezone"]))
        window = payload.window

        found = False
        for item in series:
            meta = {m["T3_Variable"]: m for m in item.get("MetaData") or []}
            code = (meta.get("Municipios") or {}).get("Codigo")
            concept = str((meta.get("Concepto turístico") or {}).get("Id"))
            if code is None:
                continue  # a total above the municipalities
            found = True
            place = municipalities.get(code)
            if place is None or concept not in concepts or not region.contains(place["lat"], place["lon"]):
                continue  # another island, or a concept the connector does not map
            metric = self.config.metrics[concepts[concept]]
            for point in item.get("Data") or []:
                period = str(point.get("T3_Periodo"))
                match = MONTH_PERIOD.match(period)
                if match is None:
                    msg = f"ine_tourist_housing {payload.dataset}: period {period} of {code} is not a month"
                    raise ConnectorError(msg)
                month = date(int(point["Anyo"]), int(match.group(1)), 1)
                if not window.start <= month <= window.end:
                    continue
                value = point.get("Valor")
                yield Observation(
                    source=self.name,
                    entity=code,
                    metric=metric.name,
                    ts=datetime.combine(month, time(), tzinfo=tz),
                    value=float(value) if value is not None else None,
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=float(place["lat"]),
                    lon=float(place["lon"]),
                )
        if not found:
            msg = f"ine_tourist_housing {payload.dataset}: no municipal series in the answer; check the table id"
            raise ConnectorError(msg)
