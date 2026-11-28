"""Náyade connector: the samples of the bathing waters of Mallorca (Ministerio de Sanidad).

Náyade, the national information system of bathing waters, has no API: it is a web application of forms. Three of
its pages, which answer a plain GET without a session, are enough:

* ``ciudadanoListaZonaAction.do?codCCAA&codProvincia&codMunicipio``: the bathing waters of one municipality, each
  one a ``verZona('<id>')`` link;
* ``ciudadanoVerZonaAction.do?codZona=<id>&pestanya=1``: the bathing water (name, island, season) and its sampling
  points, each with its UTM coordinates;
* the same page with ``pestanya=3``: per sampling point, every sample of the last four seasons (date, E. coli,
  intestinal enterococci and the advice that came with it) and the restrictions ("incidentes": opening and closing
  day and the measure).

``extract`` walks the municipalities of the region and keeps, per bathing water, the part of those pages below their
menus (the scripts and the navigation are the same on every page); ``normalize`` reads the tables. The entity is the
sampling point, ``<municipality>_<bathing water>_<point>`` (``07040_1033_PM3``): a bathing water may have up to six,
and the municipality in the id links it with ``dim_municipalities`` in gold.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from datetime import date, datetime, time
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from core.connectors import BaseConnector, ConnectorError
from core.models import Entity, Observation, Quality, RawPayload, Region

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from core.models import TimeWindow

ZONE_LINK = re.compile(r"verZona\('(\d+)'\)")
DAY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# A result: "340 NMP/100 mL" or "20 UFC/100 mL".
RESULT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:NMP|UFC)\s*/\s*100\s*mL$", re.IGNORECASE)
POINT_SUFFIX = re.compile(r"\s+(PM\s*\d+)$", re.IGNORECASE)
# Where the content of a zone page starts: everything above it is scripts and menus.
CONTENT_START = 'class="tituloMenu'  # the tabs of the bathing water (Localización, Playa, Muestreos...)
# Words kept in lower case when the upper-case names of Náyade are written as titles.
_LOWER_WORDS = frozenset(
    {"de", "del", "dels", "des", "d", "la", "las", "les", "los", "el", "els", "es", "ses", "sa", "s", "i", "y", "en"}
)


class _Cells(HTMLParser):
    """The text of every table cell of a page, row by row (nested tables become rows of their own)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002 - parser API
        if tag == "tr":
            self.rows.append([])
        elif tag == "td":
            if not self.rows:
                self.rows.append([])
            self._cell = []
            self.rows[-1].append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None:
            self.rows[-1][-1] = " ".join(" ".join(self._cell).split())
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def table_rows(html: str) -> list[list[str]]:
    """The non-empty cells of each table row of ``html``, in document order (rows without text are dropped)."""
    parser = _Cells()
    parser.feed(html)
    parser.close()
    rows = [[cell for cell in row if cell] for row in parser.rows]
    return [row for row in rows if row]


def title_case(name: str) -> str:
    """``PLAYA DELS TAMARELLS (PORT DE POLLENÇA)`` -> ``Playa dels Tamarells (Port de Pollença)``.

    A bracket glued to a word (``LLENAIRE(PORT DE POLLENÇA)``) gets its space back first.
    """
    words = []
    for index, word in enumerate(re.sub(r"\s*\(\s*", " (", name).strip().lower().split()):
        head, _, rest = word.partition("'")
        if rest:  # S'ARENAL -> s'Arenal, D'EN -> d'en
            joined = f"{head}'{rest if rest in _LOWER_WORDS else rest[:1].upper() + rest[1:]}"
            words.append(joined if index else joined[:1].upper() + joined[1:])
            continue
        lead = word[:1] if word[:1] in '(«"' else ""
        core = word[len(lead) :]
        keep_lower = core in _LOWER_WORDS and index > 0 and not lead
        words.append(lead + (core if keep_lower else core[:1].upper() + core[1:]))
    return " ".join(words)


def utm_to_latlon(easting: float, northing: float, zone: int) -> tuple[float, float]:
    """Latitude and longitude of a UTM point of the northern hemisphere (GRS80/WGS84 ellipsoid, Snyder 1987).

    Náyade gives the sampling points in ETRS89 UTM; at the scale of a beach map ETRS89 and WGS84 are the same.
    """
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0 = 0.9996
    x = easting - 500000.0
    m = northing / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sin1**2)
    t1 = tan1**2
    c1 = ep2 * cos1**2
    r1 = a * (1 - e2) / (1 - e2 * sin1**2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tan1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = (
        d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos1
    central = math.radians(zone * 6 - 183)
    return math.degrees(lat), math.degrees(central + lon)


def _day(text: str) -> date | None:
    match = DAY.match(text)
    return date(int(match.group(3)), int(match.group(2)), int(match.group(1))) if match else None


def _result(text: str) -> float | None:
    match = RESULT.match(text)
    return float(match.group(1).replace(",", ".")) if match else None


def point_code(name: str, index: int) -> str:
    """``PLAYA DE PALMA PM3`` -> ``PM3``; a point named without it is numbered by its order on the page."""
    match = POINT_SUFFIX.search(name)
    return match.group(1).replace(" ", "").upper() if match else f"PM{index}"


def parse_location(html: str) -> dict[str, Any]:
    """Name, island and sampling points (name and UTM coordinates) of a bathing water, from its first tab.

    Raises:
        ConnectorError: if the page has no bathing water name or a point has no coordinates.
    """
    fields: dict[str, str] = {}
    points: list[dict[str, Any]] = []
    for row in table_rows(html):
        for label, value in itertools.pairwise(row):
            if label == "Denominación:":
                points.append({"name": value})
            elif label in {"X:", "Y:", "Huso:"} and points:
                points[-1][label[:-1].lower()] = value
            elif label in {"Zona Agua Baño:", "Isla:", "Temporada:", "Municipio:"}:
                fields.setdefault(label[:-1], value)
    if "Zona Agua Baño" not in fields:
        msg = "nayade: a bathing water page without its name; has the page changed?"
        raise ConnectorError(msg)
    for point in points:
        if not {"x", "y"} <= point.keys():
            msg = f"nayade: sampling point {point['name']} without UTM coordinates"
            raise ConnectorError(msg)
    return {
        "name": fields["Zona Agua Baño"],
        "island": fields.get("Isla"),
        "season": fields.get("Temporada"),
        "points": points,
    }


def parse_samples(html: str) -> dict[str, dict[str, list[list[str]]]]:
    """The sample and incident rows of each sampling point, from the third tab of a bathing water.

    Per point name: its samples (day, E. coli, enterococci, advice) and its restrictions (opening day, closing day,
    measure).
    """
    points: dict[str, dict[str, list[list[str]]]] = {}
    current: dict[str, list[list[str]]] | None = None
    section = ""
    for row in table_rows(html):
        if row[0] == "Punto Muestreo:" and len(row) > 1:
            current = points.setdefault(row[1], {"samples": [], "incidents": []})
            section = ""
        elif row[0] in {"Muestreos:", "Incidentes:"}:
            section = "samples" if row[0] == "Muestreos:" else "incidents"
        elif current is not None and section and _day(row[0]) is not None:
            current[section].append(row)
    return points


class NayadeConnector(BaseConnector):
    """Samples (E. coli, enterococci, advice) and bathing restrictions of every bathing water of Mallorca (Náyade)."""

    def _zones(self, municipality: str) -> list[str]:
        options = self.config.options
        html = self.http.get_text(
            f"{options['base_url']}/ciudadanoListaZonaAction.do",
            params={
                "codCCAA": str(options["region_id"]),
                "codProvincia": str(options["province_id"]),
                "codMunicipio": str(int(municipality)),
            },
        )
        return list(dict.fromkeys(ZONE_LINK.findall(html)))

    def _page(self, zone: str, tab: int) -> str:
        html = self.http.get_text(
            f"{self.config.options['base_url']}/ciudadanoVerZonaAction.do",
            params={"codZona": zone, "pestanya": str(tab)},
        )
        start = html.rfind("<table", 0, max(html.find(CONTENT_START), 0))
        if CONTENT_START not in html or start < 0:
            msg = f"nayade: bathing water {zone} answered a page without its content (tab {tab}); has it moved?"
            raise ConnectorError(msg)
        return html[start:]

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:
        """Every bathing water of the municipalities of the region: its location and its samples (two pages each).

        Náyade always answers the last four seasons whatever the window, so the window only filters ``normalize``.

        Raises:
            ConnectorError: if no municipality of the region has a bathing water (the list page has changed).
        """
        municipalities: Mapping[str, Mapping[str, Any]] = self.config.options["municipalities"]
        zones = [
            {"municipality": code, "zone": zone, "location": self._page(zone, 1), "samples": self._page(zone, 3)}
            for code, place in municipalities.items()
            if region.contains(place["lat"], place["lon"])
            for zone in self._zones(code)
        ]
        if not zones:
            msg = "nayade: no bathing water in any municipality of the region; has the list page changed?"
            raise ConnectorError(msg)
        body = json.dumps(zones, ensure_ascii=False)
        request = {"url": self.config.options["base_url"], "municipalities": sorted(municipalities)}
        return [RawPayload(source=self.name, dataset="bathing_waters", window=window, request=request, body=body)]

    def _points(self, payload: RawPayload, region: Region) -> Iterator[tuple[str, str, dict[str, Any], dict]]:
        """(entity, display name, location point, tables) of every sampling point of the region in the payload."""
        zone_utm = int(self.config.options["utm_zone"])
        for zone in json.loads(payload.body):
            location = parse_location(zone["location"])
            tables = parse_samples(zone["samples"])
            name = title_case(location["name"])
            many = len(location["points"]) > 1
            for index, point in enumerate(location["points"], start=1):
                lat, lon = utm_to_latlon(float(point["x"]), float(point["y"]), int(point.get("huso") or zone_utm))
                if not region.contains(lat, lon):
                    continue
                code = point_code(point["name"], index)
                entity = f"{zone['municipality']}_{zone['zone']}_{code}"
                point_tables = tables.get(point["name"], {"samples": [], "incidents": []})
                yield entity, (f"{name} ({code})" if many else name), {**point, "lat": lat, "lon": lon}, point_tables

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per sampling point, metric and sampling (or restriction opening) day inside the window.

        Raises:
            ConnectorError: for an advice or measure the YAML does not map.
        """
        yield from self._samples(payload, region)
        yield from self._incidents(payload, region)

    def _observation(self, entity: str, metric: str, day: date, value: float, point: Mapping[str, Any]) -> Observation:
        spec = self.config.metrics[metric]
        tz = ZoneInfo(str(self.config.options["timezone"]))
        return Observation(
            source=self.name,
            entity=entity,
            metric=metric,
            ts=datetime.combine(day, time(), tzinfo=tz),
            value=value,
            unit=spec.unit,
            quality=Quality.OK,
            lat=round(point["lat"], 6),
            lon=round(point["lon"], 6),
        )

    def _advice(self, text: str, entity: str) -> float | None:
        if not text:
            return None
        advice: Mapping[str, int] = self.config.options["advice"]
        if text not in advice:
            msg = f"nayade: unknown advice '{text}' at {entity}; add it to options.advice"
            raise ConnectorError(msg)
        return float(advice[text])

    def _samples(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        window = payload.window
        for entity, _, point, tables in self._points(payload, region):
            # A point sampled twice the same day (a repeat after a bad result) keeps the worst value of each metric:
            # silver has one value per series and day, and the directive is about the risk.
            days: dict[date, dict[str, float | None]] = {}
            for row in tables["samples"]:
                day = _day(row[0])
                if day is None or not window.start <= day <= window.end:
                    continue
                cells = [*row[1:], "", "", ""][:3]
                # A sample without results has the advice in the first column (a restriction kept in force).
                values = {
                    "e_coli": _result(cells[0]),
                    "enterococci": _result(cells[1]),
                    "bathing_advice": self._advice(next((c for c in cells if _result(c) is None), ""), entity),
                }
                kept = days.setdefault(day, dict.fromkeys(values))
                for metric, value in values.items():
                    current = kept[metric]
                    if value is not None and (current is None or value > current):
                        kept[metric] = value
            # A result or an advice Náyade leaves blank was not reported: there is no row for it, not a null.
            for day, values in days.items():
                for metric, value in values.items():
                    if value is not None:
                        yield self._observation(entity, metric, day, value, point)

    def _incidents(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        window = payload.window
        advice: Mapping[str, int] = self.config.options["advice"]
        for entity, _, point, tables in self._points(payload, region):
            opened: dict[date, tuple[float | None, float]] = {}
            for row in tables["incidents"]:
                start = _day(row[0])
                if start is None or not window.start <= start <= window.end:
                    continue
                end = _day(row[1]) if len(row) > 1 else None
                measure = next((c for c in row[1:] if _day(c) is None), "")
                level = advice.get(measure)
                if not level:
                    msg = f"nayade: unknown restriction '{measure}' at {entity}; add it to options.advice"
                    raise ConnectorError(msg)
                days = float((end - start).days) if end is not None else None
                previous = opened.get(start)
                if previous is None or level > previous[1]:
                    opened[start] = (days, float(level))
            for start, (days, level) in opened.items():
                if days is not None:  # a restriction still in force has no length yet
                    yield self._observation(entity, "incident_days", start, days, point)
                yield self._observation(entity, "incident_level", start, level, point)

    def describe(self, payload: RawPayload, region: Region) -> Iterator[Entity]:
        """The name of every sampling point: its bathing water, plus the point when the water has more than one."""
        for entity, name, _, _ in self._points(payload, region):
            yield Entity(source=self.name, entity=entity, name=name)
