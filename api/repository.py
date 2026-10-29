"""Every SQL query of the API, in one place, over the contracted gold marts (plus silver.anomalies).

Queries are parametrised (``%(name)s``); identifiers are never built from user input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from api.database import Database, Row

# Monthly marts served as they are, by endpoint name. The keys are fixed: user input never reaches the SQL text.
MONTHLY_MARTS = {
    "water": "gold.fct_water_reserves_monthly",
    "climate": "gold.fct_climate_monthly",
    "tourism": "gold.fct_tourism_monthly",
    "resources": "gold.fct_resources_monthly",
}

_SOURCES = """
SELECT source, label, kind, last_status, last_run_at, last_success_at, last_loaded_day, runs_7d, failure_rate_7d,
       latest_observation_ts, data_age_hours, observations
FROM gold.source_health
WHERE %(source)s::text IS NULL OR source = %(source)s
ORDER BY source
"""

_OBSERVATIONS = """
SELECT o.source, o.entity, o.metric, o.ts, o.value, o.unit, o.quality, l.lat, l.lon
FROM gold.fct_observations AS o
LEFT JOIN gold.dim_locations AS l ON l.source = o.source AND l.entity = o.entity
WHERE o.source = %(source)s
  AND (%(metric)s::text IS NULL OR o.metric = %(metric)s)
  AND (%(entity)s::text IS NULL OR o.entity = %(entity)s)
  AND o.ts >= %(start)s AND o.ts < %(end)s
ORDER BY o.ts, o.entity, o.metric
LIMIT %(limit)s OFFSET %(offset)s
"""

_ANOMALIES = """
SELECT source, entity, metric, ts, detector, value, expected, score, threshold
FROM silver.anomalies
WHERE (%(source)s::text IS NULL OR source = %(source)s)
  AND (%(detector)s::text IS NULL OR detector = %(detector)s)
  AND ts >= %(start)s AND ts < %(end)s
ORDER BY ts DESC, source, entity, metric, detector
LIMIT %(limit)s OFFSET %(offset)s
"""

_AQUIFERS = """
WITH monthly AS (
    SELECT o.entity, (o.ts AT TIME ZONE 'Europe/Madrid')::date AS month, o.value
    FROM gold.fct_observations AS o
    WHERE o.source = 'water_reserves' AND o.entity IN (SELECT entity FROM gold.dim_aquifers)
),
latest AS (SELECT max(month) AS month FROM monthly)
SELECT a.entity, a.code, a.aquifer, a.hydrogeological_unit, m.month, m.value AS reserves_pct,
       m.value - p.value AS change_12m_pts
FROM gold.dim_aquifers AS a
JOIN monthly AS m ON m.entity = a.entity
JOIN latest ON m.month = latest.month
LEFT JOIN monthly AS p ON p.entity = m.entity AND p.month = (m.month - interval '12 months')::date
ORDER BY m.value, a.aquifer
"""


@dataclass
class Warehouse:
    """Read access to the warehouse for the API."""

    db: Database

    def sources(self, source: str | None = None) -> list[Row]:
        """Every source with its health, or only ``source``."""
        return self.db.fetch_all(_SOURCES, {"source": source})

    def source_exists(self, source: str) -> bool:
        """True when ``source`` is a known source (dim_sources)."""
        return bool(self.db.fetch_all("SELECT 1 FROM gold.dim_sources WHERE source = %(source)s", {"source": source}))

    def observations(  # noqa: PLR0913 - one argument per filter, all keyword-only
        self,
        *,
        source: str,
        metric: str | None,
        entity: str | None,
        start: datetime,
        end: datetime,
        limit: int,
        offset: int,
    ) -> list[Row]:
        """A page of observations of one source, oldest first."""
        params = {"source": source, "metric": metric, "entity": entity, "start": start, "end": end}
        return self.db.fetch_all(_OBSERVATIONS, {**params, "limit": limit, "offset": offset})

    def anomalies(  # noqa: PLR0913 - one argument per filter, all keyword-only
        self,
        *,
        source: str | None,
        detector: str | None,
        start: datetime,
        end: datetime,
        limit: int,
        offset: int,
    ) -> list[Row]:
        """A page of flagged values, newest first."""
        params = {"source": source, "detector": detector, "start": start, "end": end}
        return self.db.fetch_all(_ANOMALIES, {**params, "limit": limit, "offset": offset})

    def monthly(self, mart: str, start: date | None, end: date | None) -> list[Row]:
        """Rows of one monthly mart between two months (both included), oldest first.

        Raises:
            KeyError: for a mart that is not in MONTHLY_MARTS.
        """
        table = MONTHLY_MARTS[mart]
        sql = (
            f"SELECT * FROM {table} "  # noqa: S608 - table comes from the fixed MONTHLY_MARTS mapping
            "WHERE (%(start)s::date IS NULL OR month >= %(start)s) AND (%(end)s::date IS NULL OR month <= %(end)s) "
            "ORDER BY month"
        )
        return self.db.fetch_all(sql, {"start": start, "end": end})

    def aquifers(self) -> list[Row]:
        """Every aquifer of Mallorca in the latest published month, lowest first."""
        return self.db.fetch_all(_AQUIFERS)
