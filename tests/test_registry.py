from datetime import timedelta

import pytest

from core.connectors import BaseConnector, ConnectorError, registry
from core.connectors.base import parse_frequency
from core.models import TimeWindow


def test_discovers_open_meteo():
    configs = registry.discover()
    assert "open_meteo" in configs
    cfg = configs["open_meteo"]
    assert cfg.frequency_delta == timedelta(hours=1)
    assert {m.dataset for m in cfg.metrics.values()} <= set(cfg.datasets)


def test_every_connector_loads_and_implements_contract():
    for name in registry.discover():
        connector = registry.load(name, secrets={})
        assert isinstance(connector, BaseConnector)
        assert connector.name == name


def test_unknown_connector():
    with pytest.raises(ConnectorError, match="open_meteo"):
        registry.load("does_not_exist")


def test_window_limit_enforced():
    connector = registry.load("open_meteo")
    too_long = TimeWindow.last_days(connector.config.max_days + 1)
    with pytest.raises(ConnectorError):
        connector.validate_window(too_long)


def _write(tmp_path, folder, body):
    path = tmp_path / folder / "connector.yaml"
    path.parent.mkdir()
    path.write_text(body, encoding="utf-8")
    return tmp_path


def test_name_must_match_folder(tmp_path):
    root = _write(tmp_path, "foo", "name: bar\nentrypoint: x:Y\n")
    with pytest.raises(ConnectorError, match="must match folder"):
        registry.discover(root)


def test_metric_must_reference_dataset(tmp_path):
    root = _write(
        tmp_path,
        "foo",
        "name: foo\nentrypoint: x:Y\ndatasets: {a: {}}\nmetrics: {m: {dataset: b, unit: u}}\n",
    )
    with pytest.raises(ConnectorError, match="unknown datasets"):
        registry.discover(root)


def test_missing_secret_is_reported(tmp_path, monkeypatch):
    root = _write(
        tmp_path,
        "open_meteo",
        "name: open_meteo\nentrypoint: connectors.open_meteo.extractor:OpenMeteoConnector\nsecrets: [MDP_TEST_TOKEN]\n",
    )
    monkeypatch.delenv("MDP_TEST_TOKEN", raising=False)
    with pytest.raises(ConnectorError, match="MDP_TEST_TOKEN"):
        registry.load("open_meteo", connectors_dir=root)


@pytest.mark.parametrize(
    ("freq", "delta"),
    [("15m", timedelta(minutes=15)), ("1h", timedelta(hours=1)), ("1d", timedelta(days=1))],
)
def test_parse_frequency(freq, delta):
    assert parse_frequency(freq) == delta


def test_parse_frequency_invalid():
    with pytest.raises(ConnectorError):
        parse_frequency("hourly")


def test_dataset_frequency_overrides_connector_default():
    cfg = registry.discover()["redata"]
    assert cfg.frequency_for("demand") == timedelta(hours=1)
    assert cfg.frequency_for("generation") == timedelta(days=1)


def test_event_datasets_have_no_frequency():
    cfg = registry.discover()["ign"]
    assert cfg.frequency_for("earthquakes") is None
    assert cfg.is_event_source
    assert not registry.discover()["redata"].is_event_source


def test_invalid_dataset_frequency_fails_on_load(tmp_path):
    root = _write(tmp_path, "foo", "name: foo\nentrypoint: x:Y\ndatasets: {a: {frequency: often}}\n")
    with pytest.raises(ConnectorError, match="invalid frequency 'often'"):
        registry.discover(root)


def test_catch_up_days_defaults_to_max_days_and_is_validated(tmp_path):
    assert registry.discover()["open_meteo"].catch_up_days == registry.discover()["open_meteo"].max_days
    assert registry.discover()["socib"].catch_up_days == 28
    root = _write(tmp_path, "foo", "name: foo\nentrypoint: x:Y\nmax_days: 10\ncatch_up_days: 20\n")
    with pytest.raises(ConnectorError, match="catch_up_days"):
        registry.discover(root)
