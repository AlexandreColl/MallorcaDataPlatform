"""Every SQL query of the API, in one place, over the gold marts (plus silver.anomalies).

Queries are parametrised (``%(name)s``); identifiers are never built from user input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import date, datetime

    from api.database import Database, Row

# Monthly marts served as they are, by endpoint name. The keys are fixed: user input never reaches the SQL text.
MONTHLY_MARTS = {
    "water": "gold.fct_water_reserves_monthly",
    "climate": "gold.fct_climate_monthly",
    "tourism": "gold.fct_tourism_monthly",
    "resources": "gold.fct_resources_monthly",
    "sea_temperature": "gold.fct_sea_temperature_monthly",
    "unemployment": "gold.fct_unemployment_island_monthly",
}

# The catalogue's texts (label, licence) come in the language asked for, from gold.dim_source_texts; Spanish, the
# reference in gold.dim_sources, fills any text that has no translation.
_SOURCES = """
SELECT h.source, coalesce(t.label, h.label) AS label, kind, last_status, last_run_at, last_success_at, last_loaded_day,
       runs_7d, failed_7d, unavailable_7d, failure_rate_7d,
       latest_observation_ts, data_age_hours, observations,
       domain, owner, coalesce(t.license, h.license) AS license, terms_url, access, personal_data, classification,
       lifecycle, sla_data_age_hours, sla_success_rate, sla_age_met, sla_success_met, sla_met
FROM gold.source_health AS h
LEFT JOIN gold.dim_source_texts AS t ON t.source = h.source AND t.language = %(language)s
WHERE %(source)s::text IS NULL OR h.source = %(source)s
ORDER BY h.source
"""

_LOCATIONS = """
SELECT l.source, coalesce(t.label, s.label) AS label, s.kind, l.entity, l.name, l.lat, l.lon, l.first_seen,
       l.last_seen, l.n_metrics
FROM gold.dim_locations AS l
JOIN gold.dim_sources AS s ON s.source = l.source
LEFT JOIN gold.dim_source_texts AS t ON t.source = l.source AND t.language = %(language)s
WHERE l.lat IS NOT NULL AND l.lon IS NOT NULL
  AND (%(source)s::text IS NULL OR l.source = %(source)s)
ORDER BY l.source, l.entity
"""

_MOBILITY_DAILY = """
SELECT network, local_date, is_weekend, stops, stops_with_service, scheduled_stop_calls, avg_lines_per_served_stop,
       busiest_stop, busiest_stop_name, busiest_stop_departures
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
SELECT o.source AS network, o.entity AS stop, l.name, l.lat, l.lon,
       (o.ts AT TIME ZONE 'Europe/Madrid')::date AS local_date,
       max(o.value) FILTER (WHERE o.metric = 'scheduled_departures') AS departures,
       max(o.value) FILTER (WHERE o.metric = 'lines_served') AS lines
FROM gold.fct_observations AS o
JOIN latest USING (source, ts)
JOIN gold.dim_locations AS l ON l.source = o.source AND l.entity = o.entity
WHERE (%(network)s::text IS NULL OR o.source = %(network)s) AND l.lat IS NOT NULL
GROUP BY o.source, o.entity, l.name, l.lat, l.lon, o.ts
ORDER BY departures DESC NULLS LAST, o.entity
"""

# Every BiciPalma station on the latest day with values: its mean bikes and occupancy and the hours it ran out.
_BIKE_STATIONS = """
SELECT station, station_name AS name, lat, lon, local_date, hours_observed, bikes_available, bikes_available_min,
       bikes_available_max, ebikes_available, docks_available, occupancy_pct, working_docks, hours_empty, hours_full,
       largest_hourly_swing
FROM gold.fct_bike_stations_daily
WHERE local_date = (SELECT max(local_date) FROM gold.fct_bike_stations_daily) AND lat IS NOT NULL
ORDER BY station_name, station
"""

# The whole BiciPalma system per hour: the stations' means added up, and how many ran out of bikes or of docks.
_BIKES_HOURLY = """
SELECT ts, local_date, min(local_hour) AS local_hour, count(*) AS stations,
       sum(bikes_available)::double precision AS bikes_available,
       sum(ebikes_available)::double precision AS ebikes_available,
       sum(docks_available)::double precision AS docks_available,
       round(100 * sum(bikes_available) / nullif(sum(bikes_available + docks_available), 0), 1)::double precision
           AS occupancy_pct,
       count(*) FILTER (WHERE was_empty) AS stations_empty,
       count(*) FILTER (WHERE was_full) AS stations_full
FROM gold.fct_bike_stations_hourly
WHERE local_date BETWEEN %(start)s AND %(end)s
GROUP BY ts, local_date
ORDER BY ts
"""

# The daily series of one source with their names and coverage.
_SERIES = """
SELECT a.source, a.entity, l.name, a.metric, max(a.unit) AS unit,
       min(a.local_date) AS first_day, max(a.local_date) AS last_day, count(*) AS days
FROM gold.agg_daily_metrics AS a
LEFT JOIN gold.dim_locations AS l ON l.source = a.source AND l.entity = a.entity
WHERE a.source = %(source)s
GROUP BY a.source, a.entity, l.name, a.metric
ORDER BY a.metric, coalesce(l.name, a.entity)
"""

# One series per local day, with the instants the detectors flagged that day.
_SERIES_DAILY = """
WITH flagged AS (
    SELECT (ts AT TIME ZONE 'Europe/Madrid')::date AS local_date, count(DISTINCT ts) AS anomalies
    FROM silver.anomalies
    WHERE source = %(source)s AND entity = %(entity)s AND metric = %(metric)s
      AND ts >= %(start)s::timestamp - interval '1 day' AND ts < %(end)s::timestamp + interval '2 days'
    GROUP BY 1
)
SELECT a.local_date, a.n_samples AS samples, a.n_valid AS valid, a.n_suspect AS suspect,
       a.min_value, a.avg_value, a.max_value, a.completeness::double precision AS completeness,
       coalesce(f.anomalies, 0) AS anomalies
FROM gold.agg_daily_metrics AS a
LEFT JOIN flagged AS f ON a.local_date = f.local_date
WHERE a.source = %(source)s AND a.entity = %(entity)s AND a.metric = %(metric)s
  AND a.local_date BETWEEN %(start)s AND %(end)s
ORDER BY a.local_date
"""

# Every line with its path and its departures on the latest day of its network, busiest first.
_MOBILITY_ROUTES = """
WITH latest AS (
    SELECT source, max(local_date) AS local_date
    FROM gold.agg_daily_metrics
    WHERE source IN ('emt_palma', 'ctm') AND metric = 'scheduled_trips'
    GROUP BY source
)
SELECT r.source AS network, r.route, r.short_name, r.name, r.kind, r.color, latest.local_date, a.avg_value AS trips,
       r.geometry
FROM gold.dim_routes AS r
LEFT JOIN latest ON r.source = latest.source
LEFT JOIN gold.agg_daily_metrics AS a
       ON a.source = r.source AND a.entity = r.route AND a.metric = 'scheduled_trips'
      AND a.local_date = latest.local_date
WHERE %(network)s::text IS NULL OR r.source = %(network)s
ORDER BY trips DESC NULLS LAST, r.source, r.route
"""

# Island-wide daily weather per source: the mean of its stations or model points.
_WEATHER_DAILY = """
SELECT w.source, coalesce(t.label, w.source_label) AS source_label, source_kind, local_date, count(*) AS entities,
       avg(temperature_mean) AS temperature_mean, max(temperature_max) AS temperature_max,
       min(temperature_min) AS temperature_min, avg(precipitation_sum) AS precipitation_mean,
       max(wind_gust_max) AS wind_gust_max
FROM gold.fct_weather_daily AS w
LEFT JOIN gold.dim_source_texts AS t ON t.source = w.source AND t.language = %(language)s
WHERE local_date BETWEEN %(start)s AND %(end)s
GROUP BY w.source, coalesce(t.label, w.source_label), source_kind, local_date
ORDER BY local_date, w.source
"""

# One day of one source (by default its latest with temperatures), for every station or point of that source.
_WEATHER_STATIONS = """
WITH latest AS (
    SELECT coalesce(%(day)s::date, max(local_date)) AS local_date
    FROM gold.fct_weather_daily
    WHERE source = %(source)s AND temperature_mean IS NOT NULL
)
SELECT w.source, w.entity, l.name, w.lat, w.lon, w.local_date, w.temperature_mean, w.temperature_max,
       w.temperature_min, w.precipitation_sum, w.wind_gust_max
FROM gold.fct_weather_daily AS w
JOIN latest USING (local_date)
LEFT JOIN gold.dim_locations AS l ON l.source = w.source AND l.entity = w.entity
WHERE w.source = %(source)s AND w.lat IS NOT NULL AND w.temperature_mean IS NOT NULL
ORDER BY w.temperature_mean DESC
"""

# AEMET warnings in force or announced: periods that end after `start` and begin before `end`.
_WARNINGS = """
SELECT warning_id, zone, zone_name, zone_kind, phenomenon, level, start_ts, end_ts
FROM gold.fct_weather_warnings
WHERE end_ts > %(start)s AND start_ts < %(end)s
ORDER BY start_ts, level DESC, zone, phenomenon
"""

_WARNING_ZONES = """
SELECT zone, name, kind, polygon FROM gold.dim_warning_zones ORDER BY kind DESC, zone
"""

# Population per municipality and year, filtered by year (both included).
_POPULATION = """
SELECT municipality, municipality_name, year, population, population_men, population_women,
       density_per_km2, population_change, population_change_pct
FROM gold.fct_population_yearly
WHERE year BETWEEN %(from_year)s AND %(to_year)s
ORDER BY year, municipality
"""

# Tourist dwellings per municipality and reference month (INE), filtered by month (both included).
_TOURIST_DWELLINGS = """
SELECT municipality, municipality_name, reference_month, tourist_dwellings, tourist_beds, beds_per_dwelling,
       population_year, dwellings_per_1000_inhabitants, beds_per_100_inhabitants, previous_month, dwellings_change,
       dwellings_change_pct
FROM gold.fct_tourist_dwellings
WHERE (%(start)s::date IS NULL OR reference_month >= %(start)s)
  AND (%(end)s::date IS NULL OR reference_month <= %(end)s)
ORDER BY reference_month, municipality
"""

# Registered unemployment of every municipality (SEPE). Without `from`, the last 12 months loaded: the whole
# history is 53 municipalities x 20 years.
_MUNICIPAL_UNEMPLOYMENT = """
SELECT municipality, municipality_name, month, season, is_suppressed, unemployed, unemployed_men, unemployed_women,
       unemployed_under_25, unemployed_45_plus, unemployed_agriculture, unemployed_industry, unemployed_construction,
       unemployed_services, unemployed_no_previous_job, population_year, population, unemployed_per_1000_inhabitants,
       unemployed_yoy, unemployed_anomaly
FROM gold.fct_unemployment_monthly
WHERE month >= coalesce(
        %(start)s::date,
        (SELECT max(month) - interval '11 months' FROM gold.fct_unemployment_monthly)::date)
  AND (%(end)s::date IS NULL OR month <= %(end)s)
ORDER BY month, municipality
"""

# Winter against summer unemployment per year, of the island and of each municipality.
_UNEMPLOYMENT_SEASONALITY = """
SELECT area, area_name, year, summer_months, winter_months, summer_mean, winter_mean, lowest_month, highest_month,
       winter_summer_ratio
FROM gold.agg_unemployment_seasonality
WHERE %(area)s::text IS NULL OR area = %(area)s
ORDER BY area = 'mallorca' DESC, area, year
"""

# Every bathing water of Mallorca in one season (Náyade); without a season, the latest one loaded.
_BATHING_WATERS = """
SELECT bathing_water, name, municipality, municipality_name, sampling_points, lat, lon, season, samples,
       last_sample_date, worst_e_coli, worst_enterococci, samples_not_fit, restrictions, bans, restricted_days,
       assessed_samples, assessed_seasons, p95_e_coli, p95_enterococci, p90_e_coli, p90_enterococci, quality_class,
       quality, previous_quality_class, quality_class_change
FROM gold.fct_bathing_water_seasons
WHERE season = coalesce(%(season)s::integer, (SELECT max(season) FROM gold.fct_bathing_water_seasons))
ORDER BY quality_class NULLS FIRST, worst_e_coli DESC NULLS LAST, bathing_water
"""

_BATHING_WATER_YEARS = """
SELECT season, bathing_waters, classified, excellent, good, sufficient, poor, excellent_share, downgraded, upgraded,
       samples, samples_not_fit, samples_not_fit_share, restrictions, bans, restricted_days, worst_e_coli,
       worst_enterococci
FROM gold.fct_bathing_water_island_yearly
ORDER BY season
"""

# People present in Mallorca each day (Ibestat IPH) against its registered residents.
_HUMAN_PRESSURE = """
SELECT local_date, is_weekend, people_present, residents, register_year, people_over_residents, pressure_ratio
FROM gold.fct_human_pressure_daily
WHERE local_date BETWEEN %(start)s AND %(end)s
ORDER BY local_date
"""

_MUNICIPALITIES = """
SELECT municipality, name, lat, lon, area_km2, polygon FROM gold.dim_municipalities ORDER BY municipality
"""

_EPISODES = """
SELECT episode_id, start_date, end_date, days, episode_type, peak_rain_mm, peak_rain_station, peak_rain_day,
       max_stations_over_rain_threshold, peak_gust_kmh, peak_wave_m
FROM gold.fct_weather_episodes
WHERE start_date BETWEEN %(start)s AND %(end)s
ORDER BY start_date DESC
"""

_MODEL_BIAS = """
SELECT b.station_source, b.station, l.name AS station_name, b.model_point, b.distance_km, b.elevation_diff_m,
       b.days_compared, b.temperature_bias_c, b.temperature_mae_c, b.temperature_rmse_c, b.temperature_bias_adjusted_c,
       b.temperature_mae_adjusted_c, b.temperature_rmse_adjusted_c, b.precipitation_bias_total_mm,
       b.rain_day_agreement, b.wind_speed_bias_kmh, b.first_day, b.last_day
FROM gold.agg_model_bias_by_station AS b
LEFT JOIN gold.dim_locations AS l ON l.source = b.station_source AND l.entity = b.station
ORDER BY b.temperature_mae_adjusted_c DESC NULLS LAST, b.station
"""

_WAVE_MODEL_BIAS = """
SELECT b.buoy, l.name AS buoy_name, b.model_point, m.name AS model_point_name, b.distance_km, b.hours_compared,
       b.wave_height_buoy_mean_m, b.wave_height_model_mean_m, b.wave_height_bias_m, b.wave_height_mae_m,
       b.wave_height_rmse_m, b.wave_height_correlation, b.model_ratio, b.first_ts, b.last_ts
FROM gold.agg_wave_model_bias_by_buoy AS b
LEFT JOIN gold.dim_locations AS l ON l.source = 'socib' AND l.entity = b.buoy
LEFT JOIN gold.dim_locations AS m ON m.source = 'open_meteo_marine' AND m.entity = b.model_point
ORDER BY b.buoy
"""

# The latest hour of each air quality station or model point in the last two days, with its European AQI band.
_AIR_QUALITY_LATEST = """
SELECT DISTINCT ON (a.source, a.entity)
       a.source, a.entity, l.name, l.lat, l.lon, a.ts, a.pm2_5, a.pm10, a.no2, a.o3, a.eaqi_band, a.eaqi_label
FROM gold.air_quality_hourly AS a
LEFT JOIN gold.dim_locations AS l ON l.source = a.source AND l.entity = a.entity
WHERE a.ts >= now() - interval '2 days' AND a.eaqi_band IS NOT NULL
ORDER BY a.source, a.entity, a.ts DESC
"""

_SEA_HOURLY = """
SELECT s.point, l.name, s.lat, s.lon, s.ts, s.wave_height_m, s.wave_period_s, s.swell_height_m, s.sea_temperature_c
FROM gold.fct_sea_conditions_hourly AS s
LEFT JOIN gold.dim_locations AS l ON l.source = 'open_meteo_marine' AND l.entity = s.point
WHERE s.ts >= %(start)s AND s.ts < %(end)s
ORDER BY s.ts, s.point
"""

# Satellite sea temperature per coastal point and day (NOAA OISST), with its anomaly and marine heatwave days.
_SEA_TEMPERATURE_DAILY = """
SELECT s.point, l.name, s.lat, s.lon, s.day, s.sst_c, s.is_preliminary, s.sst_climatology_c, s.sst_p90_c,
       s.sst_anomaly_c, s.is_marine_heatwave, s.heatwave_id
FROM gold.fct_sea_temperature_daily AS s
LEFT JOIN gold.dim_locations AS l ON l.source = 'noaa_oisst' AND l.entity = s.point
WHERE s.day BETWEEN %(start)s AND %(end)s
ORDER BY s.day, s.point
"""

# Marine heatwaves of the coastal points that overlap a range of days, newest first.
_MARINE_HEATWAVES = """
SELECT h.heatwave_id, h.point, l.name, h.start_date, h.end_date, h.days, h.peak_day, h.peak_sst_c, h.max_intensity_c,
       h.mean_intensity_c, h.cumulative_intensity_c_days, h.category, h.has_preliminary_days
FROM gold.fct_marine_heatwaves AS h
LEFT JOIN gold.dim_locations AS l ON l.source = 'noaa_oisst' AND l.entity = h.point
WHERE h.end_date >= %(start)s AND h.start_date <= %(end)s
ORDER BY h.start_date DESC, h.point
"""

# Pollen, Saharan dust and UV per model point and local day (Open-Meteo CAMS).
_POLLEN_DUST_DAILY = """
SELECT p.point, l.name, p.local_date, p.olive_pollen_mean, p.olive_pollen_max, p.olive_pollen_level,
       p.grass_pollen_mean, p.grass_pollen_max, p.grass_pollen_level, p.dust_mean_ugm3, p.dust_max_ugm3,
       p.is_dust_over_threshold, p.uv_index_max
FROM gold.fct_pollen_dust_daily AS p
LEFT JOIN gold.dim_locations AS l ON l.source = 'open_meteo' AND l.entity = p.point
WHERE p.local_date BETWEEN %(start)s AND %(end)s
ORDER BY p.local_date, p.point
"""

# Saharan dust episodes that overlap a range of days, newest first, with the PM10 of the stations during them.
_DUST_EPISODES = """
SELECT e.episode_id, e.start_date, e.end_date, e.days, e.peak_day, e.peak_point, l.name AS peak_point_name,
       e.peak_dust_ugm3, e.mean_dust_ugm3, e.max_hourly_dust_ugm3, e.stations, e.station_pm10_ugm3,
       e.baseline_pm10_ugm3, e.pm10_excess_ugm3, e.model_pm10_ugm3, e.model_bias_ugm3
FROM gold.fct_dust_episodes AS e
LEFT JOIN gold.dim_locations AS l ON l.source = 'open_meteo' AND l.entity = e.peak_point
WHERE e.end_date >= %(start)s AND e.start_date <= %(end)s
ORDER BY e.start_date DESC
"""

_DUST_PM10 = """
SELECT d.station, l.name, d.model_point, d.dust_days, d.other_days, d.pm10_dust_days_ugm3, d.pm10_other_days_ugm3,
       d.pm10_excess_ugm3, d.model_bias_dust_days_ugm3, d.model_bias_other_days_ugm3, d.first_day, d.last_day
FROM gold.agg_dust_pm10_by_station AS d
LEFT JOIN gold.dim_locations AS l ON l.source = 'eea_air_quality' AND l.entity = d.station
ORDER BY d.pm10_excess_ugm3 DESC NULLS LAST, d.station
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

_DETECTOR_BENCHMARK = """
SELECT source, detector, fault, events, events_detected, event_recall, recall, precision, false_alarms,
       window_start, window_end, evaluated_at
FROM gold.fct_anomaly_evaluations
WHERE is_latest
ORDER BY source, detector, fault
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
# The same rows without paging, for the exports, and how many they are.
_OBSERVATIONS_ALL = _OBSERVATIONS.removesuffix("LIMIT %(limit)s OFFSET %(offset)s\n")
_OBSERVATIONS_COUNT = f"SELECT count(*) AS n FROM ({_OBSERVATIONS_ALL}) AS export"  # noqa: S608 - constant SQL

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
SELECT c.source, c.entity, l.name, c.metric, c.ts, c.unit, c.original_quality, c.original_value, c.corrected_value,
       c.correction_method AS method, c.support_source, c.support_entity, c.support_bias AS bias, c.confidence
FROM gold.fct_observations_corrected AS c
LEFT JOIN gold.dim_locations AS l ON l.source = c.source AND l.entity = c.entity
WHERE c.is_corrected
  AND (%(source)s::text IS NULL OR c.source = %(source)s)
  AND (%(entity)s::text IS NULL OR c.entity = %(entity)s)
  AND (%(method)s::text IS NULL OR c.correction_method = %(method)s)
  AND c.ts >= %(start)s AND c.ts < %(end)s
ORDER BY c.ts DESC, c.source, c.entity, c.metric
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

    def sources(self, source: str | None = None, *, language: str = "es") -> list[Row]:
        """Every source with its health, or only ``source``; its label and licence in ``language``."""
        return self.db.fetch_all(_SOURCES, {"source": source, "language": language})

    def source_exists(self, source: str) -> bool:
        """True when ``source`` is a known source (dim_sources)."""
        return bool(self.db.fetch_all("SELECT 1 FROM gold.dim_sources WHERE source = %(source)s", {"source": source}))

    def locations(self, source: str | None = None, *, language: str = "es") -> list[Row]:
        """Every place with coordinates (stations, model points, stops), or only those of ``source``."""
        return self.db.fetch_all(_LOCATIONS, {"source": source, "language": language})

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

    def observations_count(
        self, *, source: str, metric: str | None, entity: str | None, start: datetime, end: datetime
    ) -> int:
        """How many observations an export of these filters would have."""
        params = {"source": source, "metric": metric, "entity": entity, "start": start, "end": end}
        return int(self.db.fetch_all(_OBSERVATIONS_COUNT, params)[0]["n"])

    def observations_stream(
        self, *, source: str, metric: str | None, entity: str | None, start: datetime, end: datetime
    ) -> Iterator[Row]:
        """Every observation of these filters, oldest first, one row at a time."""
        params = {"source": source, "metric": metric, "entity": entity, "start": start, "end": end}
        return self.db.stream(_OBSERVATIONS_ALL, params)

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

    def bike_stations(self) -> list[Row]:
        """Every BiciPalma station on the latest day with values, by name."""
        return self.db.fetch_all(_BIKE_STATIONS)

    def bikes_hourly(self, start: date, end: date) -> list[Row]:
        """The BiciPalma system hour by hour between two local days, oldest first."""
        return self.db.fetch_all(_BIKES_HOURLY, {"start": start, "end": end})

    def series(self, source: str) -> list[Row]:
        """The daily series of a source with their names and coverage, by metric and name."""
        return self.db.fetch_all(_SERIES, {"source": source})

    def series_daily(self, source: str, entity: str, metric: str, start: date, end: date) -> list[Row]:
        """One series per local day, oldest first, with its flagged instants."""
        params = {"source": source, "entity": entity, "metric": metric, "start": start, "end": end}
        return self.db.fetch_all(_SERIES_DAILY, params)

    def mobility_routes(self, network: str | None) -> list[Row]:
        """Every line with its path and its departures on the latest day of its network, busiest first."""
        return self.db.fetch_all(_MOBILITY_ROUTES, {"network": network})

    def weather_daily(self, start: date, end: date, *, language: str = "es") -> list[Row]:
        """Island-wide daily weather per source, oldest first, with the sources' labels in ``language``."""
        return self.db.fetch_all(_WEATHER_DAILY, {"start": start, "end": end, "language": language})

    def weather_stations(self, source: str, day: date | None = None) -> list[Row]:
        """Every station or point of ``source`` on ``day`` (by default its latest with temperatures), warmest first."""
        return self.db.fetch_all(_WEATHER_STATIONS, {"source": source, "day": day})

    def warnings(self, start: datetime, end: datetime) -> list[Row]:
        """AEMET warning periods that overlap ``[start, end)``, earliest first."""
        return self.db.fetch_all(_WARNINGS, {"start": start, "end": end})

    def warning_zones(self) -> list[Row]:
        """The AEMET warning zones of Mallorca with their polygons."""
        return self.db.fetch_all(_WARNING_ZONES)

    def population(self, from_year: int, to_year: int) -> list[Row]:
        """Population of every municipality per year in ``[from_year, to_year]``, oldest first."""
        return self.db.fetch_all(_POPULATION, {"from_year": from_year, "to_year": to_year})

    def tourist_dwellings(self, start: date | None, end: date | None) -> list[Row]:
        """Tourist dwellings of every municipality per reference month in ``[start, end]``, oldest first."""
        return self.db.fetch_all(_TOURIST_DWELLINGS, {"start": start, "end": end})

    def municipal_unemployment(self, start: date | None, end: date | None) -> list[Row]:
        """Registered unemployment of every municipality per month in ``[start, end]`` (default: the last 12 months)."""
        return self.db.fetch_all(_MUNICIPAL_UNEMPLOYMENT, {"start": start, "end": end})

    def unemployment_seasonality(self, area: str | None) -> list[Row]:
        """Winter against summer unemployment per year, of the island first, then of each municipality."""
        return self.db.fetch_all(_UNEMPLOYMENT_SEASONALITY, {"area": area})

    def bathing_waters(self, season: int | None) -> list[Row]:
        """Every bathing water in one season (default: the latest), worst classified first."""
        return self.db.fetch_all(_BATHING_WATERS, {"season": season})

    def bathing_water_years(self) -> list[Row]:
        """The island's bathing waters per season, oldest first."""
        return self.db.fetch_all(_BATHING_WATER_YEARS)

    def human_pressure(self, start: date, end: date) -> list[Row]:
        """People present in Mallorca per day in ``[start, end]``, oldest first."""
        return self.db.fetch_all(_HUMAN_PRESSURE, {"start": start, "end": end})

    def municipalities(self) -> list[Row]:
        """The municipalities of Mallorca with their boundaries."""
        return self.db.fetch_all(_MUNICIPALITIES)

    def episodes(self, start: date, end: date) -> list[Row]:
        """Rain, wind and sea episodes that started in the range, newest first."""
        return self.db.fetch_all(_EPISODES, {"start": start, "end": end})

    def model_bias(self) -> list[Row]:
        """Error of the weather model against each station, largest first."""
        return self.db.fetch_all(_MODEL_BIAS)

    def wave_model_bias(self) -> list[Row]:
        """Error of the wave model against each SOCIB buoy."""
        return self.db.fetch_all(_WAVE_MODEL_BIAS)

    def air_quality_latest(self) -> list[Row]:
        """The latest hour of each air quality station and model point."""
        return self.db.fetch_all(_AIR_QUALITY_LATEST)

    def sea_hourly(self, start: datetime, end: datetime) -> list[Row]:
        """Hourly sea conditions of the coastal points, oldest first."""
        return self.db.fetch_all(_SEA_HOURLY, {"start": start, "end": end})

    def sea_temperature_daily(self, start: date, end: date) -> list[Row]:
        """Satellite sea temperature of the coastal points per day in ``[start, end]``, oldest first."""
        return self.db.fetch_all(_SEA_TEMPERATURE_DAILY, {"start": start, "end": end})

    def marine_heatwaves(self, start: date, end: date) -> list[Row]:
        """Marine heatwaves of the coastal points that overlap ``[start, end]``, newest first."""
        return self.db.fetch_all(_MARINE_HEATWAVES, {"start": start, "end": end})

    def pollen_dust_daily(self, start: date, end: date) -> list[Row]:
        """Pollen, dust and UV of every model point per local day in ``[start, end]``."""
        return self.db.fetch_all(_POLLEN_DUST_DAILY, {"start": start, "end": end})

    def dust_episodes(self, start: date, end: date) -> list[Row]:
        """Saharan dust episodes that overlap ``[start, end]``, newest first."""
        return self.db.fetch_all(_DUST_EPISODES, {"start": start, "end": end})

    def dust_pm10(self) -> list[Row]:
        """PM10 of every official station on dust days and on the other days, largest excess first."""
        return self.db.fetch_all(_DUST_PM10)

    def earthquakes(self, start: date, end: date) -> list[Row]:
        """Earthquakes located by the IGN in the range, newest first."""
        return self.db.fetch_all(_EARTHQUAKES, {"start": start, "end": end})

    def quality_rules(self) -> list[Row]:
        """The latest check of every quality rule, failing ones first."""
        return self.db.fetch_all(_QUALITY_RULES)

    def anomalies_daily(self, start: datetime, end: datetime) -> list[Row]:
        """Flagged values per local day and detector."""
        return self.db.fetch_all(_ANOMALIES_DAILY, {"start": start, "end": end})

    def detector_benchmark(self) -> list[Row]:
        """The latest fault-injection benchmark of every source, per detector and fault kind."""
        return self.db.fetch_all(_DETECTOR_BENCHMARK)
