"""The months the yearly CSV left out, read from SEPE's monthly PDF of the province.

Recorded 2026-11-28 for 2020-10-15..2020-12-31 (``fixtures_2020``): the yearly file of 2020 (which stops in November),
trimmed to Palma, Pollença, Escorca, Calvià and Maó; the index of the monthly statistics and the page of December 2020,
trimmed to their links; and MUNI_BALEARES_1220.pdf, whole. On 2026-11-28 the PDFs of May to December 2013 matched the
semester XLS of the open data in all 5,088 cells of Mallorca.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from connectors.sepe_unemployment import monthly_pdf
from core.config import load_region
from core.connectors import ConnectorError, registry
from core.connectors.recording import Manifest, RecordedHttp
from core.models import TimeWindow

FIXTURES = Path(__file__).parent / "fixtures_2020"
DECEMBER = datetime(2020, 11, 30, 23, tzinfo=UTC)  # 1 December 2020 00:00 in Madrid
NOVEMBER = datetime(2020, 10, 31, 23, tzinfo=UTC)


@pytest.fixture
def recorded():
    connector = registry.load("sepe_unemployment", http=RecordedHttp(FIXTURES))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def _observations(connector, window, region):
    return [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]


def test_a_month_missing_from_the_csv_comes_from_the_monthly_pdf(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert [p.partition for p in payloads] == ["2020", "pdf-2020-12"]
    pdf = payloads[1]
    assert pdf.request["url"].endswith("/MUNI_BALEARES_1220.pdf")
    assert pdf.request["page"].endswith("/municipios/2020/diciembre.html")
    assert len(pdf.request["sha256"]) == 64


def test_the_pdf_gives_every_municipality_of_mallorca_with_its_cells(recorded):
    connector, window, region = recorded
    observations = _observations(connector, window, region)

    december = [o for o in observations if o.ts == DECEMBER]
    assert len({o.entity for o in december}) == 53  # the whole island, not only the CSV's trimmed lines
    assert len(december) == 53 * 12

    def value(entity, metric, ts=DECEMBER):
        return next(o.value for o in observations if (o.entity, o.metric, o.ts) == (entity, metric, ts))

    assert value("07040", "unemployed") == 34476  # Palma: "34.476" in the PDF
    assert value("07040", "unemployed_no_previous_job") == 2785
    assert value("07019", "unemployed") == 3  # Escorca, exact (no "<5" before 2022)
    assert value("07019", "unemployed_men_under_25") == 0  # an empty cell is a zero
    assert value("07018", "unemployed") == 28  # Deià, "DEYA" in the PDF
    assert value("07051", "unemployed") == 385  # Sant Llorenç des Cardassar, cut short in the table
    assert value("07040", "unemployed", NOVEMBER) > 30000  # November still comes from the CSV


def test_no_pdf_when_the_csv_has_the_month():
    class Http:
        urls: list[str] = []  # noqa: RUF012 - a test double

        def get_bytes(self, url, params=None, headers=None):
            Http.urls.append(url)
            line = "202012;Diciembre de 2020;4;Balears, Illes;7;Balears, Illes;07040;Palma;34476" + ";0" * 11 + "\n"
            return (";;;;PARO\nCódigo mes ;mes;x;x;Codigo Provincia;x;Codigo Municipio\n" + line).encode("latin-1")

    connector = registry.load("sepe_unemployment", http=Http())
    payloads = connector.extract(TimeWindow(date(2020, 11, 15), date(2020, 12, 31)), load_region("mallorca"))

    assert [p.partition for p in payloads] == ["2020"]  # a later CSV that has December wins: nothing else is asked


def test_names_fold_to_the_register():
    assert monthly_pdf.fold("POBLA, SA") == monthly_pdf.fold("Sa Pobla") == "SA POBLA"
    assert monthly_pdf.fold("SALINES, SES") == monthly_pdf.fold("ses Salines")
    assert monthly_pdf.fold("POLLENÇA") == monthly_pdf.fold("Pollença") == "POLLENCA"
    assert monthly_pdf.fold("Santa María del Camí") == "SANTA MARIA DEL CAMI"


def test_a_line_whose_cells_do_not_add_up_is_an_error():
    # As pypdf reads it: one space per cell, an empty cell (a zero) between two, one more when the last cell is empty.
    text = "DICIEMBRE 2020\nESCORCA 3  1 1  1    1 2  \nPARO REGISTRADO\n"
    assert monthly_pdf.parse_rows(text, date(2020, 12, 1))["ESCORCA"] == [3, 0, 1, 1, 0, 1, 0, 0, 0, 1, 2, 0]

    with pytest.raises(ConnectorError, match="do not add up"):
        monthly_pdf.parse_rows("DICIEMBRE 2020\nESCORCA 4  1 1  1    1 2  \n", date(2020, 12, 1))
    with pytest.raises(ConnectorError, match="is not of MAYO 2013"):
        monthly_pdf.parse_rows(text, date(2013, 5, 1))


def test_a_municipality_missing_from_the_pdf_is_an_error():
    rows = {"ESCORCA": [3.0] + [0.0] * 11}

    with pytest.raises(ConnectorError, match="07042"):
        monthly_pdf.by_code(rows, {"07019": "Escorca", "07042": "Pollença"}, {})
