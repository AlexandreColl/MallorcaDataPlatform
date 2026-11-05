"""Every SQL query of the API, in one place, over the gold marts (plus silver.anomalies).

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

_LOCATIONS = """
SELECT l.source, s.label, s.kind, l.entity, l.lat, l.lon, l.first_seen, l.last_seen, l.n_metrics
FROM gold.dim_locations AS l
JOIN gold.dim_sources AS s ON s.source = l.source
WHERE l.lat IS NOT NULL AND l.lon IS NOT NULL
  AND (%(source)s::text IS NULL OR l.source = %(source)s)
ORDER BY l.source, l.entity
"""

_MOBILITY_DAILY = """
SELECT network, local_date, is_weekend, stops, stops_with_service, scheduled_stop_calls, avg_lines_per_served_stop,
       busiest_stop, busiest_stop_departures
FROM (
    SELECT 'emt_palma' AS network, * FROM gold.fct_bus_network_daily
    UNION ALL
    SELECT 'ctm' AS network, * FROM gold.fct_island_transit_daily
) AS daily
WHERE local_date BETWEEN %(start)s AND %(end)s
ORDER BY local_date, network
"""

# The service of each stop on the latest day of its network: one value per stop and day, stamped at local midnight.
_MOBILITY_STOPS = """
WITH latest AS (
    SELECT source, max(ts) AS ts
    FROM gold.fct_observations
    WHERE source IN ('emt_palma', 'ctm') AND metric = 'scheduled_departures'
    GROUP BY source
)
SELECT o.source AS network, o.entity AS stop, l.lat, l.lon, (o.ts AT TIME ZONE 'Europe/Madrid')::date AS local_date,
       max(o.value) FILTER (WHERE o.metric = 'scheduled_departures') AS departures,
       max(o.value) FILTER (WHERE o.metric = 'lines_served') AS lines
FROM gold.fct_observations AS o
JOIN latest USING (source, ts)
JOIN gold.dim_locations AS l ON l.source = o.source AND l.entity = o.entity
WHERE (%(network)s::text IS NULL OR o.source = %(network)s) AND l.lat IS NOT NULL
GROUP BY o.source, o.entity, l.lat, l.lon, o.ts
ORDER BY departures DESC NULLS LAST, o.entity
"""

# Island-wide daily weather per source: the mean of its stations or model points.
_WEATHER_DAILY = """
SELECT source, source_label, source_kind, local_date, count(*) AS entities,
       avg(temperature_mean) AS temperature_mean, max(temperature_max) AS temperature_max,
       min(temperature_min) AS temperature_min, avg(precipitation_sum) AS precipitation_mean,
       max(wind_gust_max) AS wind_gust_max
FROM gold.fct_weather_daily
WHERE local_date BETWEEN %(start)s AND %(end)s
GROUP BY source, source_label, source_kind, local_date
ORDER BY local_date, source
"""

_EPISODES = """
SELECT episode_id, start_date, end_date, days, episode_type, peak_rain_mm, peak_rain_station, peak_rain_day,
       max_stations_over_rain_threshold, peak_gust_kmh, peak_wave_m
FROM gold.fct_weather_episodes
WHERE start_date BETWEEN %(start)s AND %(end)s
ORDER BY start_date DESC
"""

_MODEL_BIAS = """
SELECT station_source, station, model_point, distance_km, days_compared, temperature_bias_c, temperature_mae_c,
       temperature_rmse_c, precipitation_bias_total_mm, rain_day_agreement, wind_speed_bias_kmh, first_day, last_day
FROM gold.agg_model_bias_by_station
ORDER BY temperature_mae_c DESC NULLS LAST, station
"""

# The latest hour of each air quality station or model point in the last two days, with its European AQI band.
_AIR_QUALITY_LATEST = """
SELECT DISTINCT ON (a.source, a.entity)
       a.source, a.entity, l.lat, l.lon, a.ts, a.pm2_5, a.pm10, a.no2, a.o3, a.eaqi_band, a.eaqi_label
FROM gold.air_quality_hourly AS a
LEFT JOIN gold.dim_locations AS l ON l.source = a.source AND l.entity = a.entity
WHERE a.ts >= now() - interval '2 days' AND a.eaqi_band IS NOT NULL
ORDER BY a.source, a.entity, a.ts DESC
"""

_SEA_HOURLY = """
SELECT point, lat, lon, ts, wave_height_m, wave_period_s, swell_height_m, sea_temperature_c
FROM gold.fct_sea_conditions_hourly
WHERE ts >= %(start)s AND ts < %(end)s
ORDER BY ts, point
"""

_EARTHQUAKES = """
SELECT event_id, ts, lat, lon, magnitude, depth_km, distance_to_palma_km
FROM gold.fct_earthquakes
WHERE local_date BETWEEN %(start)s AND %(end)s
ORDER BY ts DESC
"""

_QUALITY_RULES = """
SELECT source, rule, target, checked, failed, passed, failed_ratio, checked_at
FROM gold.data_quality_summary
ORDER BY passed, failed_ratio DESC NULLS LAST, source, rule, target
"""

_ANOMALIES_DAILY = """
SELECT (ts AT TIME ZONE 'Europe/Madrid')::date AS local_date, detector, count(*) AS anomalies
FROM silver.anomalies
WHERE ts >= %(start)s AND ts < %(end)s
GROUP BY 1, 2
ORDER BY 1, 2
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

_CORRECTIONS = """
SELECT source, entity, metric, ts, unit, original_quality, original_value, corrected_value,
       correction_method AS method, support_source, support_entity, support_bias AS bias, confidence
FROM gold.fct_observations_corrected
WHERE is_corrected
  AND (%(source)s::text IS NULL OR source = %(source)s)
  AND (%(entity)s::text IS NULL OR entity = %(entity)s)
  AND (%(method)s::text IS NULL OR correction_method = %(method)s)
  AND ts >= %(start)s AND ts < %(end)s
ORDER BY ts DESC, source, entity, metric
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

    def locations(self, source: str | None = None) -> list[Row]:
        """Every place with coordinates (stations, model points, stops), or only those of ``source``."""
        return self.db.fetch_all(_LOCATIONS, {"source": source})

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

    def corrections(  # noqa: PLR0913 - one argument per filter, all keyword-only
        self,
        *,
        source: str | None,
        entity: str | None,
        method: str | None,
        start: datetime,
        end: datetime,
        limit: int,
        offset: int,
    ) -> list[Row]:
        """A page of corrected station values, newest first."""
        params = {"source": source, "entity": entity, "method": method, "start": start, "end": end}
        return self.db.fetch_all(_CORRECTIONS, {**params, "limit": limit, "offset": offset})

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

    def mobility_daily(self, start: date, end: date) -> list[Row]:
        """Scheduled service per day of the EMT and CTM networks, oldest first."""
        return self.db.fetch_all(_MOBILITY_DAILY, {"start": start, "end": end})

    def mobility_stops(self, network: str | None) -> list[Row]:
        """The service of every stop on the latest day of its network, busiest first."""
        return self.db.fetch_all(_MOBILITY_STOPS, {"network": network})

    def weather_daily(self, start: date, end: date) -> list[Row]:
        """Island-wide daily weather per source, oldest first."""
        return self.db.fetch_all(_WEATHER_DAILY, {"start": start, "end": end})

    def episodes(self, start: date, end: date) -> list[Row]:
        """Rain, wind and sea episodes that started in the range, newest first."""
        return self.db.fetch_all(_EPISODES, {"start": start, "end": end})

    def model_bias(self) -> list[Row]:
        """Error of the weather model against each station, largest first."""
        return self.db.fetch_all(_MODEL_BIAS)

    def air_quality_latest(self) -> list[Row]:
        """The latest hour of each air quality station and model point."""
        return self.db.fetch_all(_AIR_QUALITY_LATEST)

    def sea_hourly(self, start: datetime, end: datetime) -> list[Row]:
        """Hourly sea conditions of the coastal points, oldest first."""
        return self.db.fetch_all(_SEA_HOURLY, {"start": start, "end": end})

    def earthquakes(self, start: date, end: date) -> list[Row]:
        """Earthquakes located by the IGN in the range, newest first."""
        return self.db.fetch_all(_EARTHQUAKES, {"start": start, "end": end})

    def quality_rules(self) -> list[Row]:
        """The latest check of every quality rule, failing ones first."""
        return self.db.fetch_all(_QUALITY_RULES)

    def anomalies_daily(self, start: datetime, end: datetime) -> list[Row]:
        """Flagged values per local day and detector."""
        return self.db.fetch_all(_ANOMALIES_DAILY, {"start": start, "end": end})
