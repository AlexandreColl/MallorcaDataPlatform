"""``make new-connector NAME=x``: the folder of a new connector, ready to fill in (docs/adding-a-connector.md).

The connector starts disabled, with one dataset and one metric to replace, an extractor that asks a JSON API for
the window and reads a list of records, and a test that replays the responses ``make record-fixtures`` records.
The test fails until there are recordings and the connector turns them into observations that fit its YAML.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.connectors.base import ConnectorError

if TYPE_CHECKING:
    from pathlib import Path

_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

CONNECTOR_YAML = """\
name: {name}
description: {title}. Replace with what the source publishes, how often and whether it needs a key
entrypoint: connectors.{name}.extractor:{cls}
enabled: false         # true once its tests pass on recorded responses and `make run CONNECTORS={name}` works
frequency: 1h          # expected spacing between values: 1h, 1d, 1mo, 1y or event (see docs/adding-a-connector.md)
max_days: 31           # longest window the API serves in one run
secrets: []            # env vars it needs in .env (pass them in x-platform-env of docker-compose.yml too)

datasets:
  main:
    url: https://example.org/api/values   # replace with the endpoint

# metric name -> dataset, canonical unit, valid physical range (values outside it are labelled suspect)
metrics:
  value: {{dataset: main, unit: "1", min: 0, max: 1000}}
"""

EXTRACTOR = '''\
"""{title} connector. Replace with where the data comes from and how it is asked for."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.connectors import BaseConnector, ConnectorError
from core.models import Observation, Quality, RawPayload, Region, TimeWindow

if TYPE_CHECKING:
    from collections.abc import Iterator


class {cls}(BaseConnector):
    """Replace with what one run downloads and from where."""

    def extract(self, window: TimeWindow, region: Region) -> list[RawPayload]:  # noqa: ARG002 - see normalize
        """One request per dataset for the whole window, kept exactly as the API returns it."""
        payloads = []
        for dataset, spec in self.config.datasets.items():
            params = {{"start": window.start.isoformat(), "end": window.end.isoformat()}}
            body = self.http.get_json(spec["url"], params=params)
            request = {{"url": spec["url"], "params": params}}
            payloads.append(RawPayload(source=self.name, dataset=dataset, window=window, request=request, body=body))
        return payloads

    def normalize(self, payload: RawPayload, region: Region) -> Iterator[Observation]:
        """One observation per record and metric: replace the field names with those of the API.

        Raises:
            ConnectorError: when the body is not a list of records.
        """
        if not isinstance(payload.body, list):
            msg = f"{{self.name}}: expected a list of records, got {{type(payload.body).__name__}}"
            raise ConnectorError(msg)
        for record in payload.body:
            lat, lon = record.get("lat"), record.get("lon")
            if lat is not None and lon is not None and not region.contains(lat, lon):
                continue
            for metric in self.config.metrics_for(payload.dataset):
                value = record.get(metric.name)
                yield Observation(
                    source=self.name,
                    entity=str(record["entity"]),
                    metric=metric.name,
                    ts=datetime.fromisoformat(record["ts"]).astimezone(UTC),
                    value=None if value is None else float(value),
                    unit=metric.unit,
                    quality=Quality.OK if value is not None else Quality.MISSING,
                    lat=lat,
                    lon=lon,
                )
'''

TEST = '''\
"""{title} against the responses recorded with `make record-fixtures CONNECTOR={name}` (no network)."""

from pathlib import Path

import pytest

from core.config import load_region
from core.connectors import registry
from core.connectors.recording import Manifest, RecordedHttp

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def recorded():
    """The connector answering from the recordings, with the window and region they were made for."""
    http = RecordedHttp(FIXTURES)
    config = registry.discover()["{name}"]
    connector = registry.load("{name}", http=http, secrets=dict.fromkeys(config.secrets, "recorded"))
    manifest = Manifest.load(FIXTURES)
    return connector, manifest.window, load_region(manifest.region)


def test_extract_asks_only_for_what_was_recorded(recorded):
    connector, window, region = recorded

    payloads = connector.extract(window, region)

    assert payloads
    assert {{p.dataset for p in payloads}} <= set(connector.config.datasets)


def test_every_observation_fits_the_connector_yaml(recorded):
    connector, window, region = recorded

    observations = [o for p in connector.extract(window, region) for o in connector.normalize(p, region)]

    assert observations, "the recorded responses gave no observation"
    for o in observations:
        spec = connector.config.metrics[o.metric]
        assert o.source == "{name}"
        assert o.unit == spec.unit
        assert window.start <= o.ts.date() <= window.end
        if o.value is not None and spec.min is not None and spec.max is not None:
            assert spec.min <= o.value <= spec.max, o
'''

README = """\
# {title}

Replace with: what the source publishes, its licence and terms, who owns it, how often it is updated, how far back
it goes and its quirks (late publication, gaps, units).

- **API:** `https://example.org/api/values`
- **Key:** none
- **Frequency:** hourly

## Recording the fixtures

```bash
make record-fixtures CONNECTOR={name} DAYS=1
```

The responses go to `tests/fixtures/`, listed in `recorded.json`; the tests replay them without a network.
"""


def class_name(name: str) -> str:
    """``water_quality`` -> ``WaterQualityConnector``."""
    return "".join(part.capitalize() for part in name.split("_")) + "Connector"


def new_connector(name: str, connectors_dir: Path) -> list[Path]:
    """Write the folder of connector ``name`` and return the files written.

    Raises:
        ConnectorError: if the name is not a short snake_case word or the folder exists.
    """
    if not _NAME.match(name):
        msg = f"'{name}' is not a connector name: lower case letters, digits and _, starting with a letter"
        raise ConnectorError(msg)
    folder = connectors_dir / name
    if folder.exists():
        msg = f"{folder} already exists"
        raise ConnectorError(msg)
    values = {"name": name, "cls": class_name(name), "title": name.replace("_", " ").capitalize()}
    files = {
        folder / "__init__.py": f'"""{values["title"]} connector."""\n',
        folder / "connector.yaml": CONNECTOR_YAML.format(**values),
        folder / "extractor.py": EXTRACTOR.format(**values),
        folder / "README.md": README.format(**values),
        folder / "tests" / f"test_{name}.py": TEST.format(**values),
        folder / "tests" / "fixtures" / ".gitkeep": "",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return list(files)
