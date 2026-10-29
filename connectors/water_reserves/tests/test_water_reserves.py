import base64
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from connectors.water_reserves.extractor import find_links, read_ods
from core.connectors import ConnectorError, registry
from core.models import Quality, Region, TimeWindow

# The portal page and its files as published on 2026-10-28 (data up to August 2026): the spreadsheet of the last
# 13 months and the 10-year PDF chart of Mallorca.
FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "index.html").read_text(encoding="utf-8")
FILES = {
    "569422": "Reservas_Hidricas_2026_08_cast.ods",
    "569419": "Reservas_Hidricas_Mallorca_2026_08_cast.pdf",
}
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
# What a run on 2026-10-28 asks for: 365 days ending 62 days before yesterday, so September 2025 to August 2026.
WINDOW = TimeWindow(date(2025, 8, 27), date(2026, 8, 26))
AQUIFERS = 18


class RecordedPortal:
    def __init__(self, files=FILES) -> None:
        self.files = files
        self.calls: list[str] = []

    def get_text(self, url, params=None, headers=None):
        self.calls.append(url)
        return PAGE

    def get_bytes(self, url, params=None, headers=None):
        self.calls.append(url)
        file_id = url.rsplit("id=", 1)[-1]
        return (FIXTURES / self.files[file_id]).read_bytes() if file_id in self.files else b"<html>not found</html>"


def _normalize(window=WINDOW, http=None):
    connector = registry.load("water_reserves", http=http or RecordedPortal())
    return [o for p in connector.extract(window, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _value(observations, entity, month):
    return next(o.value for o in observations if o.entity == entity and o.ts.date() == month)


def test_the_files_are_found_by_their_link_text():
    links = find_links(PAGE)
    http = RecordedPortal()
    connector = registry.load("water_reserves", http=http)

    payloads = connector.extract(WINDOW, MALLORCA)

    assert len(links) == 5  # spreadsheet, three island PDFs and the method
    assert [p.dataset for p in payloads] == ["last_year", "history"]
    assert http.calls[1].endswith("archivopub.do?ctrl=MCRST259ZI569422&id=569422")
    assert base64.b64decode(payloads[0].body) == (FIXTURES / FILES["569422"]).read_bytes()


def test_the_spreadsheet_reader_expands_repeated_cells():
    rows = read_ods((FIXTURES / FILES["569422"]).read_bytes())
    pollenca = next(r for r in rows if len(r) > 1 and r[1] == "1805M1")

    # "31 %" four months in a row is stored once with number-columns-repeated="4".
    assert pollenca[2:] == pytest.approx([0.30, 0.31, 0.31, 0.31, 0.31, 0.33, 0.34, 0.31, 0.32, 0.31, 0.31, 0.31, 0.30])


def test_aquifers_and_island_from_the_spreadsheet():
    observations = _normalize()

    assert len({o.entity for o in observations}) == AQUIFERS + 1
    assert len(observations) == (AQUIFERS + 1) * 12  # September 2025 to August 2026
    assert _value(observations, "mallorca", date(2026, 2, 1)) == 59.0
    assert _value(observations, "mallorca", date(2026, 8, 1)) == 38.0
    assert _value(observations, "aquifer_1816m2", date(2026, 8, 1)) == 9.0  # Son Real, the lowest
    assert {o.unit for o in observations} == {"%"}
    assert {o.quality for o in observations} == {Quality.OK}
    assert observations[0].ts == datetime(2025, 8, 31, 22, tzinfo=UTC)  # 1 September 2025, local midnight


def test_the_pdf_adds_the_years_before_the_spreadsheet():
    observations = _normalize(TimeWindow(date(2016, 7, 1), date(2026, 8, 26)))

    island = {o.ts.date(): o.value for o in observations if o.entity == "mallorca"}
    assert len(island) == 121  # August 2016 to August 2026, each month once
    assert island[date(2016, 8, 1)] == 40.0  # from the PDF (whole percentages)
    assert island[date(2017, 2, 1)] == 76.0
    assert island[date(2025, 7, 1)] == 45.0  # last month taken from the PDF
    assert island[date(2025, 8, 1)] == 43.0  # first month of the spreadsheet (the PDF says 41)
    aquifer_months = {o.ts.date() for o in observations if o.entity == "aquifer_1805m1"}
    assert min(aquifer_months) == date(2025, 8, 1)  # aquifers only come from the spreadsheet


def test_a_title_that_wraps_before_the_year():
    # The PDF published on 2026-10-29 (up to September 2026) breaks its title before the last year:
    # "(septiembre de 2016 <dash> septiembre de \n2026)".
    http = RecordedPortal({**FILES, "569419": "Reservas_Hidricas_Mallorca_2026_09_cast.pdf"})

    observations = _normalize(TimeWindow(date(2016, 7, 1), date(2026, 8, 26)), http)

    island = {o.ts.date(): o.value for o in observations if o.entity == "mallorca"}
    assert island[date(2016, 9, 1)] == 39.0  # first bar of the new chart
    assert island[date(2016, 10, 1)] == 42.0
    assert date(2016, 8, 1) not in island


def test_a_missing_link_or_a_page_instead_of_the_file_is_an_error():
    with pytest.raises(ConnectorError, match="not a pdf file"):
        _normalize(http=RecordedPortal({"569422": FILES["569422"]}))

    connector = registry.load("water_reserves", http=RecordedPortal())
    connector.config.datasets["history"]["link_text"] = "durante los 20 últimos años"
    with pytest.raises(ConnectorError, match="no link containing"):
        connector.extract(WINDOW, MALLORCA)


def test_other_regions_are_rejected():
    connector = registry.load("water_reserves", http=RecordedPortal())
    with pytest.raises(ConnectorError, match="do not cover"):
        connector.extract(WINDOW, Region("ibiza", 38.8, 1.2, 39.2, 1.7))
