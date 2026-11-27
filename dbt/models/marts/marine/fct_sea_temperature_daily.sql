-- The satellite sea surface temperature of every coastal point and day since 1981, with its anomaly against the
-- 1991-2020 climatology of the same day of the year (dim_sea_temperature_climatology) and the marine heatwaves of
-- Hobday et al. (2016): at least `sst_heatwave_min_days` days in a row above the 90th percentile of the
-- climatology; two of them separated by `sst_heatwave_max_gap_days` days or less are one heatwave, gap included.
--
-- Gaps and islands, as in fct_weather_episodes: consecutive days minus their row number give the same anchor date,
-- so each run of days above the threshold is one island. A day without a value breaks the run.
with daily as (
    select
        d.point,
        d.day,
        d.sst_c,
        d.sst_preliminary_c,
        d.is_preliminary,
        d.lat,
        d.lon,
        c.sst_climatology_c,
        c.sst_p90_c
    from {{ ref('int_sea_temperature__daily') }} as d
    left join {{ ref('dim_sea_temperature_climatology') }} as c
        on d.point = c.point and {{ day_of_year_366('d.day') }} = c.day_of_year
),

above as (
    select
        point,
        day,
        day - (row_number() over (partition by point order by day))::integer as island
    from daily
    where sst_c > sst_p90_c
),

runs as (
    select
        point,
        min(day) as start_date,
        max(day) as end_date
    from above
    group by point, island
    having count(*) >= {{ var('sst_heatwave_min_days') }}
),

starts as (
    select
        *,
        case
            when
                start_date - lag(end_date) over (partition by point order by start_date)
                <= {{ var('sst_heatwave_max_gap_days') }} + 1
                then 0
            else 1
        end as is_new
    from runs
),

numbered as (
    select
        *,
        sum(is_new) over (partition by point order by start_date) as heatwave_number
    from starts
),

heatwaves as (
    select
        point,
        min(start_date) as start_date,
        max(end_date) as end_date
    from numbered
    group by point, heatwave_number
)

select
    d.point,
    d.day,
    d.lat,
    d.lon,
    round(d.sst_c::numeric, 2)::numeric(5, 2) as sst_c,
    d.is_preliminary,
    round(d.sst_preliminary_c::numeric, 2)::numeric(5, 2) as sst_preliminary_c,
    d.sst_climatology_c,
    d.sst_p90_c,
    round((d.sst_c - d.sst_climatology_c)::numeric, 2)::numeric(5, 2) as sst_anomaly_c,
    coalesce(d.sst_c > d.sst_p90_c, false) as is_above_p90,
    h.start_date is not null as is_marine_heatwave,
    case
        when h.start_date is not null then {{ dbt_utils.generate_surrogate_key(["d.point", "h.start_date"]) }}
    end as heatwave_id
from daily as d
left join heatwaves as h on d.point = h.point and d.day between h.start_date and h.end_date
