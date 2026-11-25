"""Gold: daily tables rebuilt from silver on every run, in Databricks SQL.

They follow the dbt marts of the local stack (``dbt/models/marts``) for the two sources of this job: the local day
in Europe/Madrid (``local_timezone`` in ``dbt_project.yml``), only ``ok`` values, and a station day that counts only
with at least 18 valid hours (``fct_air_quality_model_bias_daily``). Locally the station-to-model pairs come from
``int_station_model_pairs``; here the nearest Open-Meteo point is picked from the coordinates in silver.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

    from mdp_databricks.catalog import Names

log = logging.getLogger(__name__)

LOCAL_TIMEZONE = "Europe/Madrid"
POLLUTANTS = ("pm10", "pm2_5", "nitrogen_dioxide", "ozone")
MIN_STATION_HOURS = 18
MIN_WEATHER_HOURS = 20


def gold_statements(names: Names) -> dict[str, str]:
    """``CREATE OR REPLACE TABLE`` statements by gold table, in dependency order."""
    pollutants = ", ".join(f"'{p}'" for p in POLLUTANTS)
    local_date = f"to_date(from_utc_timestamp(ts, '{LOCAL_TIMEZONE}'))"
    return {
        "air_quality_daily": f"""
            CREATE OR REPLACE TABLE {names.gold("air_quality_daily")}
            COMMENT 'Daily mean and maximum of each pollutant, per EEA station and Open-Meteo (CAMS model) point'
            AS SELECT
                source,
                entity,
                metric,
                {local_date} AS local_date,
                round(avg(value), 2) AS mean_ugm3,
                round(max(value), 2) AS max_ugm3,
                count(*) AS hours
            FROM {names.silver}
            WHERE source IN ('eea_air_quality', 'open_meteo')
                AND metric IN ({pollutants})
                AND quality = 'ok'
                AND value IS NOT NULL
            GROUP BY source, entity, metric, {local_date}
        """,  # noqa: S608 - the catalog is a checked identifier, the rest are constants
        "station_model_pairs": f"""
            CREATE OR REPLACE TABLE {names.gold("station_model_pairs")}
            COMMENT 'Each EEA station with the nearest Open-Meteo point (great-circle distance)'
            AS WITH points AS (
                SELECT DISTINCT source, entity, lat, lon
                FROM {names.silver}
                WHERE source IN ('eea_air_quality', 'open_meteo') AND lat IS NOT NULL AND lon IS NOT NULL
            ),
            distances AS (
                SELECT
                    s.entity AS station,
                    m.entity AS model_point,
                    2 * 6371 * asin(sqrt(
                        pow(sin(radians(m.lat - s.lat) / 2), 2)
                        + cos(radians(s.lat)) * cos(radians(m.lat)) * pow(sin(radians(m.lon - s.lon) / 2), 2)
                    )) AS distance_km
                FROM points AS s
                CROSS JOIN points AS m
                WHERE s.source = 'eea_air_quality' AND m.source = 'open_meteo'
            )
            SELECT station, model_point, round(distance_km, 2) AS distance_km
            FROM distances
            QUALIFY row_number() OVER (PARTITION BY station ORDER BY distance_km) = 1
        """,  # noqa: S608 - the catalog is a checked identifier, the rest are constants
        "air_quality_model_bias_daily": f"""
            CREATE OR REPLACE TABLE {names.gold("air_quality_model_bias_daily")}
            COMMENT 'Daily air quality of each EEA station next to the CAMS model at the nearest point, and the bias'
            AS SELECT
                p.station,
                p.model_point,
                p.distance_km,
                obs.metric,
                obs.local_date,
                obs.mean_ugm3 AS station_mean_ugm3,
                model.mean_ugm3 AS model_mean_ugm3,
                round(model.mean_ugm3 - obs.mean_ugm3, 2) AS bias_ugm3,
                obs.max_ugm3 AS station_max_ugm3,
                obs.hours AS station_hours
            FROM {names.gold("station_model_pairs")} AS p
            INNER JOIN {names.gold("air_quality_daily")} AS obs
                ON obs.source = 'eea_air_quality' AND obs.entity = p.station
            INNER JOIN {names.gold("air_quality_daily")} AS model
                ON model.source = 'open_meteo'
                AND model.entity = p.model_point
                AND model.metric = obs.metric
                AND model.local_date = obs.local_date
            WHERE obs.hours >= {MIN_STATION_HOURS}
        """,  # noqa: S608 - the catalog is a checked identifier, the rest are constants
        "weather_daily": f"""
            CREATE OR REPLACE TABLE {names.gold("weather_daily")}
            COMMENT 'Daily weather of each Open-Meteo point: temperature, precipitation, humidity and wind'
            AS SELECT
                entity,
                {local_date} AS local_date,
                round(avg(CASE WHEN metric = 'temperature_2m' THEN value END), 2) AS temperature_mean,
                round(min(CASE WHEN metric = 'temperature_2m' THEN value END), 2) AS temperature_min,
                round(max(CASE WHEN metric = 'temperature_2m' THEN value END), 2) AS temperature_max,
                round(sum(CASE WHEN metric = 'precipitation' THEN value END), 2) AS precipitation_sum,
                round(avg(CASE WHEN metric = 'relative_humidity_2m' THEN value END), 2) AS humidity_mean,
                round(avg(CASE WHEN metric = 'wind_speed_10m' THEN value END), 2) AS wind_speed_mean,
                count(CASE WHEN metric = 'temperature_2m' THEN 1 END) AS hours_observed,
                count(CASE WHEN metric = 'temperature_2m' THEN 1 END) >= {MIN_WEATHER_HOURS} AS is_complete_day
            FROM {names.silver}
            WHERE source = 'open_meteo' AND quality = 'ok' AND value IS NOT NULL
            GROUP BY entity, {local_date}
        """,  # noqa: S608 - the catalog is a checked identifier, the rest are constants
    }


def build_gold(spark: SparkSession, names: Names) -> dict[str, int]:
    """Rebuild every gold table. Returns the row count of each."""
    counts: dict[str, int] = {}
    for table, statement in gold_statements(names).items():
        spark.sql(statement)
        counts[table] = spark.table(names.gold(table)).count()
        log.info("gold: %s has %d rows", names.gold(table), counts[table])
    return counts
