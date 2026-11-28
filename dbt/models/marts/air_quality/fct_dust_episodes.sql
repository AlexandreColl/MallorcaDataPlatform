-- Saharan dust episodes: runs of consecutive dust days (int_dust__daily), with gaps and islands as in
-- fct_weather_episodes. Each one is joined to the PM10 of the official stations (EEA, days with at least 18 valid
-- hours): their mean during the episode against their mean on the days without dust within
-- `dust_baseline_half_days` of it, station by station, so the season and the station cancel out. The CAMS PM10 of the
-- nearest model point on the same days says how far the model the corrections use is from the stations then.
with dust_days as (
    select *
    from {{ ref('int_dust__daily') }}
    where is_dust_day
),

islands as (
    select
        *,
        local_date - (row_number() over (order by local_date))::int as island
    from dust_days
),

peaks as (
    select distinct on (island)
        island,
        local_date as peak_day,
        peak_point
    from islands
    order by island asc, dust_mean_ugm3 desc
),

episodes as (
    select
        island,
        min(local_date) as start_date,
        max(local_date) as end_date,
        count(*)::integer as days,
        max(peak_point_dust_ugm3) as peak_dust_ugm3,
        avg(dust_mean_ugm3) as mean_dust_ugm3,
        max(dust_max_ugm3) as max_hourly_dust_ugm3
    from islands
    group by island
),

pm10 as (
    select
        station,
        local_date,
        station_mean_ugm3,
        model_mean_ugm3
    from {{ ref('fct_air_quality_model_bias_daily') }}
    where metric = 'pm10'
),

calm_days as (
    select local_date
    from {{ ref('int_dust__daily') }}
    where not is_dust_day
),

during as (
    select
        e.island,
        pm.station,
        avg(pm.station_mean_ugm3) as station_pm10,
        avg(pm.model_mean_ugm3) as model_pm10
    from episodes as e
    inner join pm10 as pm on pm.local_date between e.start_date and e.end_date
    group by e.island, pm.station
),

baseline as (
    select
        e.island,
        pm.station,
        avg(pm.station_mean_ugm3) as station_pm10
    from episodes as e
    inner join pm10 as pm
        on
            pm.local_date between e.start_date - {{ var('dust_baseline_half_days') }}
            and e.end_date + {{ var('dust_baseline_half_days') }}
    inner join calm_days as c on pm.local_date = c.local_date
    group by e.island, pm.station
),

stations as (
    select
        d.island,
        count(*) as stations,
        avg(d.station_pm10) as station_pm10,
        avg(b.station_pm10) as baseline_pm10,
        avg(d.model_pm10) as model_pm10
    from during as d
    inner join baseline as b on d.island = b.island and d.station = b.station
    group by d.island
)

select
    {{ dbt_utils.generate_surrogate_key(["e.start_date"]) }} as episode_id,
    e.start_date,
    e.end_date,
    e.days,
    p.peak_day,
    p.peak_point,
    e.peak_dust_ugm3,
    round(e.mean_dust_ugm3::numeric, 1)::double precision as mean_dust_ugm3,
    e.max_hourly_dust_ugm3,
    coalesce(s.stations, 0)::integer as stations,
    round(s.station_pm10::numeric, 1)::double precision as station_pm10_ugm3,
    round(s.baseline_pm10::numeric, 1)::double precision as baseline_pm10_ugm3,
    round((s.station_pm10 - s.baseline_pm10)::numeric, 1)::double precision as pm10_excess_ugm3,
    round(s.model_pm10::numeric, 1)::double precision as model_pm10_ugm3,
    round((s.model_pm10 - s.station_pm10)::numeric, 1)::double precision as model_bias_ugm3
from episodes as e
inner join peaks as p on e.island = p.island
left join stations as s on e.island = s.island
