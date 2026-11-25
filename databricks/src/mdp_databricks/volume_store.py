"""Bronze on Databricks: raw payloads as files in a Unity Catalog volume, under the same keys as in MinIO.

Same contract as ``core.storage.BronzeStore`` (``put`` and ``get`` by key), on a path such as
``/Volumes/mallorca/bronze/raw``. A volume keeps no versions of an overwritten file: the bronze table that Auto Loader
fills from it only appends, so every past response is still there.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from core.models import RawPayload

if TYPE_CHECKING:
    from core.connectors import BaseConnector
    from core.models import Region, TimeWindow

log = logging.getLogger(__name__)


class VolumeBronzeStore:
    """Raw API responses under their deterministic key, below a volume path."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, payload: RawPayload) -> str:
        """Write a payload under its key and return the key. Re-running a window overwrites the file."""
        path = self.root / payload.key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.to_json(), encoding="utf-8")
        log.info("bronze <- %s", path)
        return payload.key

    def get(self, key: str) -> RawPayload:
        """Read a payload back by its key."""
        return RawPayload.from_json((self.root / key).read_bytes())


def extract_to_volume(
    connector: BaseConnector, window: TimeWindow, region: Region, store: VolumeBronzeStore
) -> list[str]:
    """Call the source API with the connector, as the Airflow task does, and land every response in the volume."""
    connector.validate_window(window)
    return [store.put(p) for p in connector.extract(window, region)]
