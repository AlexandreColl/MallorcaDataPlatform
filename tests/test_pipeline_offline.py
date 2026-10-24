"""Bronze round-trip with in-memory fakes: no network, no MinIO, no Postgres."""

import io
import json
from datetime import date
from pathlib import Path

import pytest

from core.connectors import registry
from core.models import Location, Region, TimeWindow
from core.pipeline import bronze_to_observations, extract_to_bronze
from core.storage import BronzeStore

FIXTURES = Path(__file__).parent.parent / "connectors" / "open_meteo" / "tests" / "fixtures"
REGION = Region(
    "test",
    39.25,
    2.30,
    39.97,
    3.50,
    (Location("palma", 39.5696, 2.6502), Location("inca", 39.7210, 2.9110)),
)
WINDOW = TimeWindow(date(2026, 10, 23), date(2026, 10, 23))


class FakeS3:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803 (boto3 signature)
        self.objects[(Bucket, Key)] = Body
        self.puts += 1

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class RecordedHttp:
    def get_json(self, url, params=None, headers=None):
        name = "air_quality.json" if "air-quality" in url else "weather.json"
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _Settings:
    bronze_bucket = "bronze"


@pytest.fixture
def store():
    return BronzeStore(_Settings(), client=FakeS3())


def test_bronze_roundtrip_and_idempotent_keys(store):
    connector = registry.load("open_meteo", http=RecordedHttp())

    keys_first = extract_to_bronze(connector, WINDOW, REGION, store)
    keys_second = extract_to_bronze(connector, WINDOW, REGION, store)

    assert keys_first == keys_second  # same window -> same objects (overwritten, versioned)
    assert len(store.client.objects) == 2
    observations = bronze_to_observations(connector, keys_first, REGION, store)
    assert len(observations) == 2 * 24 * 10
