import io
import json
import re
import tarfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from connectors.aemet_warnings.extractor import parse_cap
from core.connectors import ConnectorError, registry
from core.models import Region, TimeWindow

FIXTURES = Path(__file__).parent / "fixtures"
# Recorded 2026-11-05. archive.tar: two real issues of 2 Nov 2026 in the archive's layout (cut down to their Balearic
# files). At 01:57 there was a yellow rain warning for 3 Nov 09-23 UTC in the five land zones of Mallorca; the issue
# of 10:24 keeps it only for Sierra Tramontana (645401) and the south (645404): the other three were withdrawn
# without a Cancel. latest.tar: the latest issue of area 64 on 5 Nov (yellow rain for 5 Nov 03-19 UTC).
WINDOW = TimeWindow(date(2026, 11, 3), date(2026, 11, 3))
MALLORCA = Region("mallorca", 39.25, 2.30, 39.97, 3.50)
SECRETS = {"AEMET_API_KEY": "test-key"}


class RecordedAemet:
    """Serves the recorded two-step answers: metadata JSON for API paths, then the tar for the `datos` URL."""

    def __init__(self, *, archive_estado=200):
        self.archive_estado = archive_estado
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, headers))
        if "/archivo/" in url and self.archive_estado != 200:
            return {"descripcion": "No hay datos que satisfagan esos criterios", "estado": self.archive_estado}
        return {"descripcion": "exito", "estado": 200, "datos": "https://datos.test/" + url.rsplit("/", 1)[-1]}

    def get_bytes(self, url, params=None, headers=None):
        self.calls.append((url, headers))
        return (FIXTURES / ("latest.tar" if url.endswith("/64") else "archive.tar")).read_bytes()


def _connector(http=None):
    return registry.load("aemet_warnings", http=http or RecordedAemet(), secrets=SECRETS)


def _observations(http=None):
    connector = _connector(http)
    return [o for p in connector.extract(WINDOW, MALLORCA) for o in connector.normalize(p, MALLORCA)]


def _level(observations, zone, metric, ts):
    return next(o.value for o in observations if o.entity == zone and o.metric == metric and o.ts == ts)


def test_two_step_requests_read_the_archive_from_the_lookback_days():
    http = RecordedAemet()

    payloads = _connector(http).extract(WINDOW, MALLORCA)

    assert [p.dataset for p in payloads] == ["archive", "latest"]
    assert "fechaini/2026-11-02T00:00:00UTC/fechafin/2026-11-03T23:59:59UTC" in payloads[0].request["path"]
    assert payloads[1].request["path"].endswith("/avisos_cap/ultimoelaborado/area/64")
    api_calls = [(url, headers) for url, headers in http.calls if url.startswith("https://opendata.aemet.es")]
    assert all(headers == {"api_key": "test-key"} for _, headers in api_calls)
    assert "test-key" not in json.dumps([p.request for p in payloads])  # the key never lands in bronze


def test_bronze_keeps_the_balearic_cap_files_by_issue_untouched():
    archive = json.loads(_connector().extract(WINDOW, MALLORCA)[0].body)

    assert sorted(archive) == ["Z_CAP_C_LEMM_20261102015751_AFAE.gz", "Z_CAP_C_LEMM_20261102102407_AFAE.gz"]
    files = archive["Z_CAP_C_LEMM_20261102102407_AFAE.gz"]
    assert all("AFAZ64" in name for name in files)
    assert all(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>') for xml in files.values())


def test_each_hour_takes_the_snapshot_in_force_and_a_withdrawn_warning_goes_back_to_zero():
    observations = _observations()
    noon = datetime(2026, 11, 3, 12, tzinfo=UTC)

    assert _level(observations, "645401", "warning_rain", noon) == 1  # Sierra Tramontana: kept at 10:24
    assert _level(observations, "645404", "warning_rain", noon) == 1  # south: kept
    assert _level(observations, "645402", "warning_rain", noon) == 0  # north: withdrawn at 10:24, no Cancel
    assert _level(observations, "645401", "warning_rain", datetime(2026, 11, 3, 8, tzinfo=UTC)) == 0  # before onset
    assert _level(observations, "645401", "warning_rain", datetime(2026, 11, 3, 22, tzinfo=UTC)) == 1  # until 22:59:59


def test_archive_rows_stay_in_the_window_and_the_latest_issue_writes_the_hours_after_it():
    observations = _observations()
    archive = [o for o in observations if o.ts < WINDOW.end_dt_exclusive()]
    latest = [o for o in observations if o.ts >= WINDOW.end_dt_exclusive()]

    assert {o.ts.date() for o in archive} == {date(2026, 11, 3)}
    assert len({o.ts for o in archive}) == 24  # every hour of the window
    assert _level(latest, "645403", "warning_rain", datetime(2026, 11, 5, 10, tzinfo=UTC)) == 1  # 5 Nov 03-19 UTC
    assert _level(latest, "645403", "warning_rain", datetime(2026, 11, 5, 20, tzinfo=UTC)) == 0


def test_only_the_zones_of_the_region_with_one_metric_per_phenomenon():
    observations = _observations()

    zones = {o.entity for o in observations}
    assert {"645401", "645402", "645403", "645404", "645405"} <= zones  # the five land zones of Mallorca
    assert "645401C" in zones  # and their coastal zones
    assert not {"645301", "645501"} & zones  # Ibiza and Menorca are outside the region
    assert {o.metric for o in observations} <= {
        "warning_rain", "warning_storms", "warning_wind", "warning_coastal", "warning_max_temperature",
        "warning_min_temperature", "warning_snow", "warning_fog", "warning_rissaga", "warning_dust",
    }  # fmt: skip
    assert {o.unit for o in observations} == {"level"}
    assert all(0 <= o.value <= 3 for o in observations)
    north = next(o for o in observations if o.entity == "645402")
    assert (north.lat, north.lon) == pytest.approx((39.7724, 3.1764))  # centre of the zone's polygon


def test_a_cancel_message_sets_the_level_to_zero():
    with tarfile.open(FIXTURES / "latest.tar") as tar:
        name = next(n for n in tar.getnames() if "645403" in n)
        xml = tar.extractfile(name).read().decode()

    alert, cancel = parse_cap(xml), parse_cap(xml.replace("<msgType>Alert</msgType>", "<msgType>Cancel</msgType>"))

    assert [m.level for m in alert] == [1]
    assert [m.level for m in cancel] == [0]


def test_a_period_without_warnings_is_empty_and_a_bad_answer_fails():
    archive_404 = RecordedAemet(archive_estado=404)
    payloads = _connector(archive_404).extract(WINDOW, MALLORCA)
    assert json.loads(payloads[0].body) == {}

    with pytest.raises(ConnectorError, match="estado 401"):
        _connector(RecordedAemet(archive_estado=401)).extract(WINDOW, MALLORCA)


def test_the_archive_layout_is_a_tar_of_gzipped_tars():
    with tarfile.open(FIXTURES / "archive.tar") as outer:
        issue = outer.extractfile(outer.getmembers()[0]).read()
    with tarfile.open(fileobj=io.BytesIO(issue), mode="r:gz") as inner:
        assert all("AFAZ64" in n for n in inner.getnames())


def test_a_long_window_is_read_in_requests_of_at_most_two_days():
    """AEMET rejects archive ranges over 2 days ("El rango de fechas no puede ser superior a 2 dias")."""
    week = TimeWindow(date(2026, 10, 28), date(2026, 11, 3))

    payloads = _connector().extract(week, MALLORCA)

    archive = payloads[:-1]
    for p in archive:
        start, end = (date.fromisoformat(day) for day in re.findall(r"/(\d{4}-\d{2}-\d{2})T", p.request["path"]))
        assert (end - start).days <= 2
    assert [p.window.n_days for p in archive] == [2, 2, 2, 1]  # the window, chunk by chunk, without gaps
