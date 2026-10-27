-- Island-wide extremes per local day from every real or modelled source: the wettest AEMET station, the
-- strongest gust measured by any station and the highest modelled wave, each flagged against its threshold.
with rain as (
    select distinct on (local_date)
        local_date,
        precipitation_sum as max_rain_mm,
        entity as max_rain_station
    from {{ ref('fct_weather_daily') }}
    where source = 'aemet' and precipitation_sum is not null
    order by local_date asc, precipitation_sum desc, entity asc
),

rain_stations as (
    select
        local_date,
        count(*) as stations_over_rain_threshold
    from {{ ref('fct_weather_daily') }}
    where source = 'aemet' and precipitation_sum >= {{ var('episode_rain_mm') }}
    group by local_date
),

gust as (
    select
        local_date,
        max(wind_gust_max) as max_gust_kmh
    from {{ ref('fct_weather_daily') }}
    where source_kind = 'observation'
    group by local_date
),

waves as (
    select
        local_date,
        max(wave_height_m) as max_wave_m
    from {{ ref('fct_sea_conditions_hourly') }}
    group by local_date
),

days as (
    select local_date from rain
    union
    select local_date from gust
    union
    select local_date from waves
)

select
    d.local_date,
    r.max_rain_mm,
    r.max_rain_station,
    coalesce(rs.stations_over_rain_threshold, 0) as stations_over_rain_threshold,
    g.max_gust_kmh,
    w.max_wave_m,
    coalesce(r.max_rain_mm >= {{ var('episode_rain_mm') }}, false) as is_heavy_rain,
    coalesce(g.max_gust_kmh >= {{ var('episode_gust_kmh') }}, false) as is_strong_wind,
    coalesce(w.max_wave_m >= {{ var('episode_wave_m') }}, false) as is_rough_sea
from days as d
left join rain as r on d.local_date = r.local_date
left join rain_stations as rs on d.local_date = rs.local_date
left join gust as g on d.local_date = g.local_date
left join waves as w on d.local_date = w.local_date
