"""SEPE connector: registered unemployment in each municipality of Mallorca, per month.

SEPE (Servicio Público de Empleo Estatal) publishes one CSV per year with the people registered as unemployed on the
last working day of each month in every municipality of Spain: the total, six bands of sex and age and five economic
sectors. A file is ~10 MB (latin1, ``;``-separated, a title line above the header, header names with stray spaces)
and grows by one month in the middle of the next one.

``extract`` downloads the files of the years the window touches and keeps, for bronze, the title, the header and the
lines of the province of the window's months, with the SHA-256 and size of the whole file. ``normalize`` keeps the
municipalities of the region and writes one observation per municipality, column and month, stamped on the first
day of the month at local midnight. Since 2022 every count from 1 to 4 is published as ``<5``: it is stored as a null
value, and the metrics declare ``suppressed_below`` so the quality rules do not count it as missing or as a gap.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# Columns of the identity of a line (header names with their spaces trimmed).
MONTH, PROVINCE, MUNICIPALITY = "Código mes", "Codigo Provincia", "Codigo Municipio"
# The mark of a count from 1 to 4 (statistical secrecy).
SUPPRESSED = "<5"
_DELIMITER = ";"
_TITLE_LINES = 1  # the report title above the header


def month_of(code: str) -> date:
    """``202610`` -> 2026-10-01.

    Raises:
        ConnectorError: if the code is not a month.
    """
    code = code.strip()
    if len(code) != 6 or not code.isdigit() or not 1 <= int(code[4:]) <= 12:  # noqa: PLR2004 - YYYYMM
        msg = f"sepe_unemployment: '{code}' is not a YYYYMM month"
        raise ConnectorError(msg)
    return date(int(code[:4]), int(code[4:]), 1)


def parse_count(raw: str) -> float | None:
    """A cell as a number: ``"12"`` -> 12.0; ``"<5"`` (a count from 1 to 4) -> None.

    Raises:
        ConnectorError: for anything else, an empty cell included (the files have none).
    """
    raw = raw.strip()
    if raw == SUPPRESSED:
        return None
    try:
        return float(raw)
    except ValueError:
        msg = f"sepe_unemployment: unexpected count '{raw}'"
        raise ConnectorError(msg) from None


def lines_of(text: str, province: str, months: set[date]) -> list[str]:
    """The title, the header and the lines of ``province`` whose month is in ``months``, as they are in the file."""
    lines = text.splitlines(keepends=True)
    kept = lines[: _TITLE_LINES + 1]
    for line in lines[_TITLE_LINES + 1 :]:
        fields = line.split(_DELIMITER, 5)
        if len(fields) < 6 or fields[4].strip().lstrip("0") != province:  # noqa: PLR2004 - the province is field 5
            continue
        try:
            month = month_of(fields[0])
        except ConnectorError:
            continue  # a blank or footer line
        if month in months:
            kept.append(line)
    return kept


class SepeUnemploymentConnector(BaseConnector):
    """Registered unemployment of every municipality of Mallorca, by sex and age and by sector, per month (SEPE)."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - see normalize
        """One payload per yearly file the window touches, with the province's lines of the window's months."""
        options = self.config.options
        months = set(window.month_starts())
        first_year = max(window.start.year, int(options["first_year"]))
        payloads = []
        for year in range(first_year, window.end.year + 1):
            year_months = {m for m in months if m.year == year}
            if not year_months:
                continue  # the window starts after the last month start of this year
            url = str(options["url"]).format(year=year)
            content = self.http.get_bytes(url)
            lines = lines_of(content.decode(str(options["encoding"])), str(options["province"]), year_months)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset="municipalities",
                    window=window,
                    request={
                        "url": url,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "bytes": len(content),
                        "province": options["province"],
                        "lines": len(lines) - _TITLE_LINES - 1,
                    },
                    body="".join(lines),
                    partition=str(year),
                )
            )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per municipality of the region, mapped column and month inside the window.

        Raises:
            ConnectorError: if the header lacks a column of the YAML or the identity columns.
        """
        options = self.config.options
        municipalities: Mapping[str, Mapping[str, Any]] = options["municipalities"]
        columns: Mapping[str, str] = options["columns"]
        tz = ZoneInfo(str(options["timezone"]))
        months = set(payload.window.month_starts())

        rows = csv.reader(payload.body.splitlines()[_TITLE_LINES:], delimiter=_DELIMITER)
        header = [name.strip() for name in next(rows, [])]
        missing = sorted({MONTH, MUNICIPALITY, *columns} - set(header))
        if missing:
            msg = f"sepe_unemployment {payload.partition}: columns {missing} not in the header {header}"
            raise ConnectorError(msg)
        index = {name: i for i, name in enumerate(header)}

        for row in rows:
            if len(row) < len(header):
                continue  # a blank line
            code = row[index[MUNICIPALITY]].strip().zfill(5)
            place = municipalities.get(code)
            if place is None or not region.contains(place["lat"], place["lon"]):
                continue  # another island
            month = month_of(row[index[MONTH]])
            if month not in months:
                continue
            ts = datetime.combine(month, time(), tzinfo=tz)
            for column, metric_name in columns.items():
                metric = self.config.metrics[metric_name]
                value = parse_count(row[index[column]])
                yield Observation(
                    source=self.name,
                    entity=code,
                    metric=metric.name,
                    ts=ts,
                    value=value,
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=float(place["lat"]),
                    lon=float(place["lon"]),
                )
