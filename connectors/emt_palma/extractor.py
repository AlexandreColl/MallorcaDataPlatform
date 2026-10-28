"""EMT Palma connector: static GTFS turned into a daily series per stop.

All the logic lives in :mod:`core.connectors.gtfs`, shared with the CTM island network. EMT publishes
headway-based trips (``frequencies.txt``), so a trip running every 15 min from 07:00 to 08:00 counts as
4 departures.
"""

from __future__ import annotations

from core.connectors.gtfs import GtfsConnector


class EmtPalmaConnector(GtfsConnector):
    """Scheduled bus service per stop and day from EMT Palma's static GTFS."""
