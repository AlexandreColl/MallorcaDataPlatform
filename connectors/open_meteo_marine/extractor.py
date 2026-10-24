"""Open-Meteo Marine connector: the Open-Meteo request and parsing at the sea points of ``connector.yaml``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.open_meteo.extractor import OpenMeteoConnector
from core.connectors import ConnectorError
from core.models import Location

if TYPE_CHECKING:
    from core.models import Region


class OpenMeteoMarineConnector(OpenMeteoConnector):
    """Hourly wave and ocean model data at coastal points inside the region."""

    def locations(self, region: Region) -> tuple[Location, ...]:
        """Configured sea points inside the region's bounding box.

        Raises:
            ConnectorError: if no point lies inside the region.
        """
        points = tuple(
            Location(str(p["name"]), float(p["lat"]), float(p["lon"]))
            for p in self.config.options["points"]
            if region.contains(float(p["lat"]), float(p["lon"]))
        )
        if not points:
            msg = f"no Open-Meteo Marine point configured inside region '{region.name}'"
            raise ConnectorError(msg)
        return points
