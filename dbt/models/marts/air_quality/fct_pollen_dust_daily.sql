-- Pollen, Saharan dust and UV of every Open-Meteo model point per local day (CAMS Europe, ~11 km). The pollen level
-- is that of the daily mean, as the aerobiology networks report it, with the thresholds of the Red Española de
-- Aerobiología (`vars.pollen_levels`). Before November 2023 CAMS served pollen only in its season: the days outside
-- it have no pollen value, not a zero.
with hourly as (
    select
        entity as point,
        local_date,
        metric,
        value
    from {{ ref('stg_open_meteo__observations') }}
    where
        metric in ('olive_pollen', 'grass_pollen', 'dust', 'uv_index')
        and not is_missing
        and not is_suspect
),

daily as (
    select
        point,
        local_date,
        avg(value) filter (where metric = 'olive_pollen') as olive_pollen_mean,
        max(value) filter (where metric = 'olive_pollen') as olive_pollen_max,
        avg(value) filter (where metric = 'grass_pollen') as grass_pollen_mean,
        max(value) filter (where metric = 'grass_pollen') as grass_pollen_max,
        avg(value) filter (where metric = 'dust') as dust_mean_ugm3,
        max(value) filter (where metric = 'dust') as dust_max_ugm3,
        max(value) filter (where metric = 'uv_index') as uv_index_max
    from hourly
    group by point, local_date
)

select
    point,
    local_date,
    round(olive_pollen_mean::numeric, 1)::double precision as olive_pollen_mean,
    round(olive_pollen_max::numeric, 1)::double precision as olive_pollen_max,
    {{ pollen_level('olive_pollen_mean', 'olive_pollen') }} as olive_pollen_level,
    round(grass_pollen_mean::numeric, 1)::double precision as grass_pollen_mean,
    round(grass_pollen_max::numeric, 1)::double precision as grass_pollen_max,
    {{ pollen_level('grass_pollen_mean', 'grass_pollen') }} as grass_pollen_level,
    round(dust_mean_ugm3::numeric, 1)::double precision as dust_mean_ugm3,
    round(dust_max_ugm3::numeric, 1)::double precision as dust_max_ugm3,
    coalesce(dust_mean_ugm3 >= {{ var('dust_episode_ugm3') }}, false) as is_dust_over_threshold,
    round(uv_index_max::numeric, 1)::double precision as uv_index_max
from daily
