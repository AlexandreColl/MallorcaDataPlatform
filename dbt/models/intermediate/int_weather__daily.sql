-- Daily weather per station or model point, on the same columns for every source:
-- hourly sources (Open-Meteo model, SOCIB stations) are aggregated to the local day; AEMET is already daily.
-- `hours_observed` says how complete an aggregated day is (null for sources that are daily at origin).
with hourly as (
    select
        source,
        entity,
        local_date,
        metric,
        value
    from {{ ref('stg_open_meteo__observations') }}
    where not is_missing
    union all
    select
        source,
        entity,
        local_date,
        metric,
        value
    from {{ ref('stg_socib__observations') }}
    where not is_missing
),

hourly_to_daily as (
    select
        source,
        entity,
        local_date,
        avg(value) filter (where metric = 'temperature_2m') as temperature_mean,
        min(value) filter (where metric = 'temperature_2m') as temperature_min,
        max(value) filter (where metric = 'temperature_2m') as temperature_max,
        sum(value) filter (where metric = 'precipitation') as precipitation_sum,
        avg(value) filter (where metric = 'relative_humidity_2m') as humidity_mean,
        avg(value) filter (where metric = 'wind_speed_10m') as wind_speed_mean,
        max(value) filter (where metric = 'wind_gusts_10m') as wind_gust_max,
        count(*) filter (where metric = 'temperature_2m') as hours_observed
    from hourly
    group by source, entity, local_date
),

daily_at_source as (
    select
        source,
        entity,
        local_date,
        max(value) filter (where metric = 'temperature_2m_mean') as temperature_mean,
        max(value) filter (where metric = 'temperature_2m_min') as temperature_min,
        max(value) filter (where metric = 'temperature_2m_max') as temperature_max,
        max(value) filter (where metric = 'precipitation_sum') as precipitation_sum,
        max(value) filter (where metric = 'relative_humidity_2m_mean') as humidity_mean,
        max(value) filter (where metric = 'wind_speed_10m_mean') as wind_speed_mean,
        max(value) filter (where metric = 'wind_gusts_10m_max') as wind_gust_max,
        null::bigint as hours_observed
    from {{ ref('stg_aemet__observations') }}
    where not is_missing
    group by source, entity, local_date
)

select * from hourly_to_daily
union all
select * from daily_at_source
