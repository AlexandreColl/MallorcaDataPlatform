from datetime import UTC, date, datetime

import pytest

from core.config import load_region
from core.connectors import ConnectorError, registry
from core.models import RawPayload, TimeWindow
from mdp_databricks.volume_store import VolumeBronzeStore, extract_to_volume

WINDOW = TimeWindow(date(2026, 11, 20), date(2026, 11, 22))


def _payload(body, partition=None):
    return RawPayload(
        source="open_meteo",
        dataset="weather",
        window=WINDOW,
        request={"url": "https://api.open-meteo.com/v1/forecast"},
        body=body,
        fetched_at=datetime(2026, 11, 23, 6, tzinfo=UTC),
        partition=partition,
    )


class FakeConnector:
    def __init__(self, payloads, max_days=31):
        self.payloads = payloads
        self.max_days = max_days

    def validate_window(self, window):
        if window.n_days > self.max_days:
            raise ConnectorError(window)

    def extract(self, window, region):
        return self.payloads


def test_put_writes_the_minio_key_below_the_volume(tmp_path):
    store = VolumeBronzeStore(tmp_path)

    key = store.put(_payload({"hourly": [1, 2]}, partition="palma"))

    assert key == "open_meteo/weather/partition=palma/window=20261120_20261122/payload.json"
    assert (tmp_path / key).is_file()


def test_get_reads_back_the_same_payload(tmp_path):
    store = VolumeBronzeStore(tmp_path)
    payload = _payload({"hourly": {"temperature_2m": [12.5, None]}})

    assert store.get(store.put(payload)) == payload


def test_put_overwrites_a_rerun_of_the_same_window(tmp_path):
    store = VolumeBronzeStore(tmp_path)
    store.put(_payload({"v": 1}))

    key = store.put(_payload({"v": 2}))

    assert store.get(key).body == {"v": 2}
    assert len(list(tmp_path.rglob("payload.json"))) == 1


def test_extract_to_volume_lands_every_payload(tmp_path):
    store = VolumeBronzeStore(tmp_path)
    connector = FakeConnector([_payload({}, partition="a"), _payload({}, partition="b")])

    keys = extract_to_volume(connector, WINDOW, load_region("mallorca"), store)

    assert [k.split("/")[2] for k in keys] == ["partition=a", "partition=b"]


def test_extract_to_volume_rejects_a_window_the_source_does_not_serve(tmp_path):
    with pytest.raises(ConnectorError):
        extract_to_volume(FakeConnector([], max_days=2), WINDOW, load_region("mallorca"), VolumeBronzeStore(tmp_path))


@pytest.mark.parametrize("name", ["open_meteo", "eea_air_quality"])
def test_the_job_sources_need_no_secret(name):
    # The job loads them with secrets={}: a source with an API key would need a Databricks secret scope first.
    assert registry.load(name, secrets={}).config.secrets == ()
