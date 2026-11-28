"""SEPE's monthly statistics per province: the months the yearly open data CSV left out.

The yearly CSV of 2013 stops in April and the one of 2020 in November. The same figures are in SEPE's monthly
statistics (``Paro registrado y contratos por municipios``), one PDF per province and month, linked from a page per
month. Each PDF has one line per municipality (uppercase name, no code) with the total, the six bands of sex and age
and the five sectors, in the order of the CSV; an empty cell is a zero. The province's XLS is a damaged OLE file that
no reader opens, so the connector reads the PDF.

Every line is checked: the six bands and the five sectors must each add up to the total, so a cell read in the wrong
column fails instead of being loaded.
"""

from __future__ import annotations

import io
import re
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from core.connectors import ConnectorError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

SPANISH_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                  "noviembre", "diciembre")  # fmt: skip
CELLS = 12  # total, 3 bands of men, 3 of women, 5 sectors
_BANDS = slice(1, 7)
_SECTORS = slice(7, 12)
# "POBLA, SA" -> "SA POBLA": the PDF puts the article after the name.
_ARTICLE = re.compile(r"^(?P<name>.+), (?P<article>ES|SA|SES|S'|EL|LA|LES|ELS)$")
_HREF = re.compile(r'href="([^"]+)"')


def fold(name: str) -> str:
    """Uppercase, without accents and with the article in front: ``"Sa Pobla"`` and ``"POBLA, SA"`` -> ``SA POBLA``."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    plain = " ".join(plain.replace("\u2019", "'").upper().split())
    match = _ARTICLE.match(plain)
    return f"{match['article']} {match['name']}" if match else plain


def month_page(index_html: str, index_url: str, month: date) -> str:
    """URL of the page of one month, linked from the index (``2020/diciembre.html``, ``2013/mayo-2013.html``).

    Raises:
        ConnectorError: if the index has no link to that month.
    """
    name = SPANISH_MONTHS[month.month - 1]
    pattern = re.compile(rf"/municipios/{month.year}/{name}(?:-{month.year})?\.html$")
    for href in _HREF.findall(index_html):
        if pattern.search(href):
            return urljoin(index_url, href)
    msg = f"sepe_unemployment: no page for {name} {month.year} in {index_url}"
    raise ConnectorError(msg)


def pdf_link(page_html: str, page_url: str, file_prefix: str) -> str:
    """URL of the province's PDF on a month page (``MUNI_BALEARES_1220.pdf``).

    Raises:
        ConnectorError: if the page has no such link.
    """
    for href in _HREF.findall(page_html):
        if file_prefix in href and href.lower().endswith(".pdf"):
            return urljoin(page_url, href)
    msg = f"sepe_unemployment: no {file_prefix} PDF on {page_url}"
    raise ConnectorError(msg)


def pdf_text(document: bytes) -> str:
    """Text of the pages with the registered unemployment (the contracts' pages are left out)."""
    from pypdf import PdfReader  # noqa: PLC0415 - only the missing months need it

    pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(document)).pages]
    return "\n".join(p for p in pages if "PARO REGISTRADO" in p)


def _count(cell: str) -> float:
    return float(cell.replace(".", "")) if cell else 0.0


def parse_rows(text: str, month: date) -> dict[str, list[float]]:
    """``{folded name: [total, 6 bands, 5 sectors]}`` of every municipality line of the PDF text.

    A line is the name, then the twelve cells separated by one space; an empty cell (a zero) leaves two spaces in a
    row, and a line whose last cell is empty ends with one space more.

    Raises:
        ConnectorError: if the text is not of ``month`` or the bands or sectors of a line do not add up to its total.
    """
    title = f"{SPANISH_MONTHS[month.month - 1].upper()} {month.year}"
    if title not in text:
        msg = f"sepe_unemployment: the PDF is not of {title}"
        raise ConnectorError(msg)
    rows: dict[str, list[float]] = {}
    for line in text.splitlines():
        first_digit = next((i for i, c in enumerate(line) if c.isdigit()), None)
        if first_digit is None or first_digit == 0 or line[first_digit - 1] != " ":
            continue  # a heading, a title or the footer
        name, cells = line[: first_digit - 1], line[first_digit:]
        cells = cells.removesuffix(" ")
        parts = cells.split(" ")
        if len(parts) != CELLS or not all(re.fullmatch(r"[\d.]*", p) for p in parts):
            continue  # the month title ("DICIEMBRE 2020"); a municipality read wrong is caught by `by_code`
        values = [_count(p) for p in parts]
        if sum(values[_BANDS]) != values[0] or sum(values[_SECTORS]) != values[0]:
            msg = f"sepe_unemployment {title}: the bands or the sectors of {name} do not add up to {values[0]:.0f}"
            raise ConnectorError(msg)
        rows[fold(name)] = values
    return rows


def by_code(
    rows: Mapping[str, list[float]], names: Mapping[str, str], aliases: Mapping[str, str]
) -> dict[str, list[float]]:
    """The rows of the municipalities in ``names`` (``{INE code: name}``), by INE code.

    ``aliases`` maps a PDF name that differs from the register's (``DEYA``, ``PALMA DE MALLORCA``, the truncated
    ``SANT LLORENÇ DES CARDA``) to its INE code.

    Raises:
        ConnectorError: if a municipality is not in the PDF.
    """
    wanted = {fold(name): code for code, name in names.items()} | {fold(k): v for k, v in aliases.items()}
    found = {wanted[name]: values for name, values in rows.items() if name in wanted}
    missing = sorted(set(names) - set(found))
    if missing:
        msg = f"sepe_unemployment: municipalities {missing} are not in the PDF"
        raise ConnectorError(msg)
    return found
