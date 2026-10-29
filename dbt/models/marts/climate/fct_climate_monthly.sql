-- Climate of Mallorca per month from the official AEMET stations: rainfall and temperature with their anomaly
-- against the same calendar month of the other years loaded, hot and wet days, and the rainfall accumulated in the
-- hydrological year (September to August), which is what refills the aquifers.
--
-- A station counts for a month only if it reported at least 90 % of its days, so a missing week never reads as a
-- dry month; the island value is the mean of the complete stations.
with daily as (
    select
        entity as station,
        local_date,
        date_trunc('month', local_date)::date as month,
        temperature_mean,
        temperature_max,
        precipitation_sum
    from {{ ref('int_weather__daily') }}
    where source = 'aemet'
),

station_month as (
    select
        station,
        month,
        extract(day from month + interval '1 month' - interval '1 day') as days_in_month,
        count(precipitation_sum) as rain_days_reported,
        sum(precipitation_sum) as rain_mm,
        count(*) filter (where precipitation_sum >= 1) as wet_days,
        count(temperature_mean) as temperature_days_reported,
        avg(temperature_mean) as temperature_mean_c,
        max(temperature_max) as temperature_max_c,
        count(*) filter (where temperature_max >= 30) as hot_days
    from daily
    group by station, month
),

island as (
    select
        month,
        count(*) filter (where rain_days_reported >= 0.9 * days_in_month) as rain_stations,
        avg(rain_mm) filter (where rain_days_reported >= 0.9 * days_in_month) as rain_mm,
        avg(wet_days) filter (where rain_days_reported >= 0.9 * days_in_month) as wet_days,
        count(*) filter (where temperature_days_reported >= 0.9 * days_in_month) as temperature_stations,
        avg(temperature_mean_c) filter (where temperature_days_reported >= 0.9 * days_in_month)
            as temperature_mean_c,
        max(temperature_max_c) filter (where temperature_days_reported >= 0.9 * days_in_month)
            as temperature_max_c,
        avg(hot_days) filter (where temperature_days_reported >= 0.9 * days_in_month) as hot_days
    from station_month
    group by month
),

with_year as (
    select
        *,
        (extract(year from month) + case when extract(month from month) >= 9 then 1 else 0 end)::integer
            as hydrological_year
    from island
    where rain_stations > 0 or temperature_stations > 0
),

accumulated as (
    select
        *,
        sum(rain_mm) over (partition by hydrological_year order by month) as rain_hydrological_year_mm
    from with_year
),

climatology as (
    select
        *,
        avg(rain_mm) over (partition by extract(month from month)) as rain_same_month_mean_mm,
        avg(temperature_mean_c) over (partition by extract(month from month)) as temperature_same_month_mean_c,
        avg(rain_hydrological_year_mm) over (partition by extract(month from month))
            as rain_hydrological_year_mean_mm,
        count(rain_mm) over (partition by extract(month from month)) as same_month_years
    from accumulated
)

select
    month,
    hydrological_year,
    rain_stations,
    round(rain_mm::numeric, 1)::numeric(7, 1) as rain_mm,
    round(rain_same_month_mean_mm::numeric, 1)::numeric(7, 1) as rain_same_month_mean_mm,
    round((rain_mm / nullif(rain_same_month_mean_mm, 0) - 1)::numeric, 3)::numeric(8, 3) as rain_anomaly,
    round(rain_hydrological_year_mm::numeric, 1)::numeric(7, 1) as rain_hydrological_year_mm,
    round(rain_hydrological_year_mean_mm::numeric, 1)::numeric(7, 1) as rain_hydrological_year_mean_mm,
    round(wet_days::numeric, 1)::numeric(4, 1) as wet_days,
    temperature_stations,
    round(temperature_mean_c::numeric, 2)::numeric(5, 2) as temperature_mean_c,
    round((temperature_mean_c - temperature_same_month_mean_c)::numeric, 2)::numeric(5, 2) as temperature_anomaly_c,
    temperature_max_c,
    round(hot_days::numeric, 1)::numeric(4, 1) as hot_days,
    same_month_years
from climatology
