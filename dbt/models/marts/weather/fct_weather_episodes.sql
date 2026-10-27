-- Weather episodes: runs of consecutive days with heavy rain, strong wind or rough sea anywhere around the island
-- (thresholds in `vars`). Gaps and islands: consecutive dates minus their row number give the same anchor date,
-- so each run of episode days becomes one group.
with episode_days as (
    select *
    from {{ ref('int_weather_extremes__daily') }}
    where is_heavy_rain or is_strong_wind or is_rough_sea
),

islands as (
    select
        *,
        local_date - (row_number() over (order by local_date))::int as island
    from episode_days
),

peaks as (
    select distinct on (island)
        island,
        max_rain_station as peak_rain_station,
        local_date as peak_rain_day
    from islands
    order by island, max_rain_mm desc nulls last
)

select
    {{ dbt_utils.generate_surrogate_key(["min(i.local_date)"]) }} as episode_id,
    min(i.local_date) as start_date,
    max(i.local_date) as end_date,
    count(*) as days,
    concat_ws(
        ' + ',
        case when bool_or(i.is_heavy_rain) then 'rain' end,
        case when bool_or(i.is_strong_wind) then 'wind' end,
        case when bool_or(i.is_rough_sea) then 'sea' end
    ) as episode_type,
    max(i.max_rain_mm) as peak_rain_mm,
    max(p.peak_rain_station) as peak_rain_station,
    max(p.peak_rain_day) as peak_rain_day,
    max(i.stations_over_rain_threshold) as max_stations_over_rain_threshold,
    max(i.max_gust_kmh) as peak_gust_kmh,
    max(i.max_wave_m) as peak_wave_m
from islands as i
inner join peaks as p on i.island = p.island
group by i.island
