"""Water reserves connector: Mallorca's groundwater reserves from the Govern's water portal (DG Recursos Hídrics).

The portal publishes, every month, a spreadsheet with the reserves of each groundwater body (MAS) of the islands
over the last 13 months, and one PDF chart per island with its weighted reserves over the last 10 years. Both are
renamed and get a new id every month, so ``extract`` reads the portal page and finds them by their link text.

* ``last_year`` (ODS): one value per aquifer of Mallorca (codes ``18xxMx``) and for the island as a whole, as a
  share of a full aquifer with two decimals. The ODS is read with the standard library (a zip of XML files).
* ``history`` (PDF): the island-wide chart, whose bar labels (whole percentages) are text. Only the months the
  spreadsheet does not cover are loaded, so the precise value wins where both exist.

Values are stored as percentages (0-100), stamped on the first day of the month.
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator

_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
# Month abbreviations of the spreadsheet header (Catalan: Gen-26, Ab-26, Agost-26...).
_MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "ab": 4, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ag": 8, "agost": 8, "set": 9,
    "oct": 10, "nov": 11, "des": 12,
}  # fmt: skip
# Month names of the PDF title (Spanish).
_SPANISH_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                   "noviembre", "diciembre")  # fmt: skip
_AQUIFER_CODE = re.compile(r"^\d{4}M\d$")
_PDF_PERIOD = re.compile(r"\((\w+) de (\d{4})\s*[^\w\s]\s*(\w+) de (\d{4})\)")  # any dash between the months
_PERCENT = re.compile(r"^(\d{1,3})%$")
_FIRST_VALUE = 2  # columns: name, code, then one per month
_EMPTY_RUN = 50  # a longer run of empty cells is the sheet's padding up to its last column


def _month_from_label(label: str) -> date:
    """``Agost-25`` -> 2025-08-01."""
    name, _, year = label.strip().rpartition("-")
    month = _MONTHS.get(name.strip().lower())
    if month is None or not year.isdigit():
        msg = f"unknown month label '{label}'"
        raise ConnectorError(msg)
    return date(2000 + int(year), month, 1)


def _add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def read_ods(archive: bytes) -> list[list[Any]]:
    """Rows of the first sheet of an ODS file: numbers as float (percentages as fractions), text as str."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        root = ET.fromstring(zf.read("content.xml"))  # noqa: S314 - see the import
    sheet = next(root.iter(f"{_TABLE}table"))
    rows: list[list[Any]] = []
    for row in sheet.iter(f"{_TABLE}table-row"):
        cells: list[Any] = []
        for cell in row:
            repeat = int(cell.get(f"{_TABLE}number-columns-repeated", "1"))
            value: Any = cell.get(f"{_OFFICE}value")
            if value is not None:
                value = float(value)
            else:
                value = "".join(p.text or "" for p in cell.iter(f"{_TEXT}p")).strip() or None
            if value is None and repeat > _EMPTY_RUN:
                continue
            cells.extend([value] * repeat)
        while cells and cells[-1] is None:
            cells.pop()
        rows.append(cells)
    return rows


def read_pdf_text(document: bytes) -> str:
    """Text of every page of a PDF."""
    from pypdf import PdfReader  # noqa: PLC0415 - only this dataset needs it

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(document)).pages)


def find_links(page: str) -> dict[str, str]:
    """``{link text: href}`` of the file links (``archivopub.do``) of a portal page."""
    links = {}
    for href, inner in re.findall(r'<a[^>]+href="([^"]*archivopub\.do[^"]*)"[^>]*>(.*?)</a>', page, flags=re.DOTALL):
        text = html.unescape(re.sub(r"<[^>]+>", " ", inner))
        links[" ".join(text.split())] = html.unescape(href)
    return links


def _fold(text: str) -> str:
    """Lowercase without accents, to match link texts written with or without them."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


class WaterReservesConnector(BaseConnector):
    """Monthly groundwater reserves of Mallorca, per aquifer and island-wide."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Find this month's files on the portal page and download them (one payload per dataset).

        Raises:
            ConnectorError: if the region is not Mallorca, a link is missing or a file has another format.
        """
        options = self.config.options
        if region.name not in options["covers_regions"]:
            msg = f"water reserves of Mallorca do not cover region '{region.name}'"
            raise ConnectorError(msg)
        page_url = str(options["page_url"])
        links = find_links(self.http.get_text(page_url))
        payloads = []
        for dataset, spec in self.config.datasets.items():
            wanted = _fold(str(spec["link_text"]))
            href = next((h for text, h in links.items() if wanted in _fold(text)), None)
            if href is None:
                msg = f"water_reserves {dataset}: no link containing '{spec['link_text']}' on {page_url}"
                raise ConnectorError(msg)
            url = page_url + href if not href.startswith("http") else href
            document = self.http.get_bytes(url)
            magic = b"PK" if spec["format"] == "ods" else b"%PDF"
            if not document.startswith(magic):
                msg = f"water_reserves {dataset}: {url} is not a {spec['format']} file"
                raise ConnectorError(msg)
            payloads.append(
                RawPayload(
                    source=self.name,
                    dataset=dataset,
                    window=window,
                    request={"url": url, "sha256": hashlib.sha256(document).hexdigest(), "bytes": len(document)},
                    body=base64.b64encode(document).decode("ascii"),
                )
            )
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:  # noqa: ARG002 - one island
        """One observation per entity and month whose first day falls inside the window."""
        document = base64.b64decode(payload.body)
        values = self._last_year(document) if payload.dataset == "last_year" else self._history(document)
        tz = ZoneInfo(str(self.config.options["timezone"]))
        metric = self.config.metrics["water_reserves"]
        months = set(payload.window.month_starts())
        for (entity, month), value in sorted(values.items()):
            if month not in months:
                continue
            yield Observation(
                source=self.name,
                entity=entity,
                metric=metric.name,
                ts=datetime.combine(month, time(), tzinfo=tz),
                value=value,
                unit=metric.unit,
                quality=Quality.OK if value is not None else Quality.MISSING,
            )

    def _last_year(self, archive: bytes) -> dict[tuple[str, date], float | None]:
        """Aquifers of the island and the island row, from the spreadsheet (fractions -> percentages)."""
        rows = read_ods(archive)
        header = next((r for r in rows if len(r) > _FIRST_VALUE and r[1] == "Codi"), None)
        if header is None:
            msg = "water_reserves last_year: no header row with 'Codi' in the spreadsheet"
            raise ConnectorError(msg)
        months = [_month_from_label(str(label)) for label in header[_FIRST_VALUE:] if label]
        island = str(self.config.options["island"]).upper()
        prefix = str(self.config.options["aquifer_code_prefix"])
        values: dict[tuple[str, date], float | None] = {}
        for row in rows:
            name = str(row[0]) if row and row[0] else ""
            code = str(row[1]) if len(row) > 1 and row[1] is not None else ""
            if _AQUIFER_CODE.match(code) and code.startswith(prefix):
                entity = f"aquifer_{code.lower()}"
            elif name.upper().startswith(island):  # "MALLORCA Conjunt (mitjana ponderada)", merged over the code
                entity = "mallorca"
            else:
                continue
            cells = row[_FIRST_VALUE:]
            for i, month in enumerate(months):
                cell = cells[i] if i < len(cells) else None
                values[entity, month] = round(cell * 100, 2) if isinstance(cell, float) else None
        if "mallorca" not in {entity for entity, _ in values}:
            msg = f"water_reserves last_year: no '{island}' row in the spreadsheet"
            raise ConnectorError(msg)
        return values

    def _history(self, document: bytes) -> dict[tuple[str, date], float | None]:
        """Island-wide bar labels of the 10-year chart, without the months the spreadsheet holds."""
        text = read_pdf_text(document)
        period = _PDF_PERIOD.search(text)
        if period is None:
            msg = "water_reserves history: no '(<month> de <year> - <month> de <year>)' period in the PDF"
            raise ConnectorError(msg)
        first = date(int(period[2]), _SPANISH_MONTHS.index(period[1].lower()) + 1, 1)
        last = date(int(period[4]), _SPANISH_MONTHS.index(period[3].lower()) + 1, 1)
        n_months = (last.year - first.year) * 12 + last.month - first.month + 1
        labels = [int(m[1]) for token in text.split() if (m := _PERCENT.match(token))]
        bars = labels[-n_months:]  # the axis ticks (0 %..100 %) come first
        if len(labels) < n_months or any(v > 100 for v in bars):  # noqa: PLR2004 - a percentage
            msg = f"water_reserves history: {len(labels)} percentage labels for {n_months} months"
            raise ConnectorError(msg)
        keep = n_months - int(self.config.datasets["history"].get("skip_last_months", 13))
        return {("mallorca", _add_months(first, i)): float(v) for i, v in enumerate(bars[:keep])}
