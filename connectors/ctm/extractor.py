"""CTM connector: the Consorci de Transports de Mallorca GTFS turned into a daily series per stop.

All the logic lives in :mod:`core.connectors.gtfs`, shared with EMT Palma. The CTM feed has no
``frequencies.txt``: every trip counts once at each stop it calls at, and its seasonal timetables (summer
lines that stop on 31 October) are separate services with their own date range.
"""

from __future__ import annotations

from core.connectors.gtfs import GtfsConnector


class CtmConnector(GtfsConnector):
    """Scheduled TIB bus, SFM train and metro service per stop and day from the CTM static GTFS."""
