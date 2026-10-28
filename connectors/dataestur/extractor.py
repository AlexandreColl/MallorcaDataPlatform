"""Dataestur connector: monthly tourism tables of SEGITTUR's API (FRONTUR, EGATUR, hotel occupancy, AENA).

Every table is downloaded as an xlsx sheet for the months the window covers and stored untouched in bronze
(base64, with its SHA-256). ``normalize`` reads the sheet with the standard library (an xlsx is a zip of XML
files, so the image needs no openpyxl), keeps the rows of ``where``, and turns each mapped column into one
value per month: added up over the kept rows with ``sum_rows`` (one row per country of residence), otherwise
taken from the month's single row.

A misspelt filter makes the API answer HTTP 200 with an empty sheet. The window always covers published months
(``min_days``), so an empty sheet is reported as an error instead of being loaded as "no data".
"""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_YEAR, _MONTH = "AÑO", "MES"


def read_sheet(archive: bytes) -> list[dict[str, str | None]]:
    """Rows of the first worksheet of an xlsx, keyed by the header row (empty cells are None)."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = zf.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))  # noqa: S314 - see the import
            shared = ["".join(t.text or "" for t in si.iter(f"{_SHEET_NS}t")) for si in root.iter(f"{_SHEET_NS}si")]
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))  # noqa: S314 - see the import
    rows: list[list[str | None]] = []
    for row in sheet.iter(f"{_SHEET_NS}row"):
        cells: dict[int, str | None] = {}
        for cell in row.iter(f"{_SHEET_NS}c"):
            value = cell.find(f"{_SHEET_NS}v")
            text = value.text if value is not None else "".join(t.text or "" for t in cell.iter(f"{_SHEET_NS}t"))
            if cell.get("t") == "s" and text:
                text = shared[int(text)]
            cells[_column_index(cell.get("r", ""))] = text or None
        rows.append([cells.get(i) for i in range(max(cells, default=-1) + 1)])
    if not rows:
        return []
    header = [str(h) for h in rows[0]]
    return [dict(zip(header, row + [None] * (len(header) - len(row)), strict=False)) for row in rows[1:]]


def _column_index(ref: str) -> int:
    """Zero-based column of a cell reference such as ``C12``."""
    index = 0
    for char in ref:
        if not char.isalpha():
            break
        index = index * 26 + ord(char.upper()) - ord("A") + 1
    return index - 1


class DataesturConnector(BaseConnector):
    """Monthly Balearic tourism statistics from Dataestur (SEGITTUR)."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """One request per dataset for the months from the window's start to its end.

        Raises:
            ConnectorError: if the region is not covered by the Balearic statistics.
        """
        options = self.config.options
        if region.name not in options["covers_regions"]:
            msg = f"Dataestur Balearic statistics do not cover region '{region.name}'"
            raise ConnectorError(msg)
        payloads = []
        for dataset, spec in self.config.datasets.items():
            url = f"{options['base_url']}/{spec['path']}"
            params = {
                "desde (año)": str(window.start.year),
                "desde (mes)": str(window.start.month),
                "hasta (año)": str(window.end.year),
                "hasta (mes)": str(window.end.month),
                **{str(k): str(v) for k, v in (spec.get("filters") or {}).items()},
            }
            archive = self.http.get_bytes(url, params=params)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset=dataset,
                    window=window,
                    request={
                        "url": url,
                        "params": params,
                        "sha256": hashlib.sha256(archive).hexdigest(),
                        "bytes": len(archive),
                    },
                    body=base64.b64encode(archive).decode("ascii"),
                )
            )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - region-wide source
        """One observation per mapped column and month whose first day falls inside the window.

        Raises:
            ConnectorError: if the sheet has no rows (a misspelt filter), or a month has several rows of a
                dataset without ``sum_rows``.
        """
        spec = self.config.datasets[payload.dataset]
        rows = read_sheet(base64.b64decode(payload.body))
        if not rows:
            msg = f"dataestur {payload.dataset}: empty sheet for {payload.request.get('params')}; check the filters"
            raise ConnectorError(msg)
        kept = [r for r in rows if _matches(r, spec.get("where") or {})]
        by_month: dict[date, list[dict[str, str | None]]] = defaultdict(list)
        for row in kept:
            by_month[date(int(str(row[_YEAR])), int(str(row[_MONTH])), 1)].append(row)

        tz = ZoneInfo(str(self.config.options["timezone"]))
        months = set(payload.window.month_starts())
        for month, month_rows in sorted(by_month.items()):
            if month not in months:
                continue
            if len(month_rows) > 1 and not spec.get("sum_rows"):
                msg = (
                    f"dataestur {payload.dataset}: {len(month_rows)} rows for {month:%Y-%m}; add `where` or `sum_rows`"
                )
                raise ConnectorError(msg)
            ts = datetime.combine(month, time(), tzinfo=tz)
            for column, metric_name in spec["columns"].items():
                metric = self.config.metrics[metric_name]
                value = _total(month_rows, column)
                yield Observation(
                    source=self.name,
                    entity=str(spec["entity"]),
                    metric=metric.name,
                    ts=ts,
                    value=value,
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                )


def _matches(row: Mapping[str, Any], where: Mapping[str, list[str]]) -> bool:
    return all(row.get(column) in values for column, values in where.items())


def _total(rows: list[dict[str, str | None]], column: str) -> float | None:
    """Sum of a column over the rows (None when no row has a value)."""
    values = [float(v) for r in rows if (v := r.get(column)) is not None]
    return sum(values) if values else None
