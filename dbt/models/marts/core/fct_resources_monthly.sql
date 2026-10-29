-- One row per month with everything that moves the island's resources: tourism (Dataestur), groundwater reserves,
-- rainfall and temperature (AEMET) and electricity demand (REData). Feeds the "Turismo y recursos" and
-- "Clima y agua" dashboards.
--
-- Every series is seasonal (summer brings the tourists, the heat, the demand peak and the lowest reserves), so
-- comparing raw months mostly shows the calendar. Each series also gets its anomaly against the mean of the same
-- calendar month: that is what can be compared between tourism, water and climate.
with demand as (
    -- monthly demand of the Balearic system; a month counts only with at least 90 % of its hours
    select
        date_trunc('month', local_date)::date as month,
        sum(value) / 1000 as electricity_demand_gwh,
        count(*) as demand_hours
    from {{ ref('stg_redata__observations') }}
    where metric = 'electricity_demand' and not is_missing
    group by 1
),

months as (
    select month from {{ ref('fct_tourism_monthly') }}
    union
    select month from {{ ref('fct_water_reserves_monthly') }}
    union
    select month from {{ ref('fct_climate_monthly') }}
    union
    select month from demand
),

joined as (
    select
        m.month,
        t.international_tourists,
        t.international_spending_eur,
        t.airport_passengers,
        t.hotel_bed_occupancy_pct,
        w.reserves_pct,
        w.change_1m_pts as reserves_change_1m_pts,
        w.anomaly_pts as reserves_anomaly_pts,
        c.rain_mm,
        c.rain_hydrological_year_mm,
        c.rain_anomaly,
        c.temperature_mean_c,
        c.temperature_anomaly_c,
        c.hot_days,
        case
            when d.demand_hours >= 0.9 * 24 * extract(day from m.month + interval '1 month' - interval '1 day')
                then d.electricity_demand_gwh
        end as electricity_demand_gwh
    from months as m
    left join {{ ref('fct_tourism_monthly') }} as t on m.month = t.month
    left join {{ ref('fct_water_reserves_monthly') }} as w on m.month = w.month
    left join {{ ref('fct_climate_monthly') }} as c on m.month = c.month
    left join demand as d on m.month = d.month
),

climatology as (
    select
        *,
        avg(international_tourists) over (partition by extract(month from month)) as tourists_same_month_mean,
        avg(electricity_demand_gwh) over (partition by extract(month from month)) as demand_same_month_mean
    from joined
)

select
    month,
    (extract(year from month) + case when extract(month from month) >= 9 then 1 else 0 end)::integer
        as hydrological_year,
    international_tourists,
    round((international_tourists / nullif(tourists_same_month_mean, 0) - 1)::numeric, 3)::numeric(8, 3)
        as tourists_anomaly,
    international_spending_eur,
    airport_passengers,
    hotel_bed_occupancy_pct,
    round(electricity_demand_gwh::numeric, 1)::numeric(8, 1) as electricity_demand_gwh,
    round((electricity_demand_gwh / nullif(demand_same_month_mean, 0) - 1)::numeric, 3)::numeric(8, 3)
        as electricity_demand_anomaly,
    reserves_pct,
    reserves_change_1m_pts,
    reserves_anomaly_pts,
    rain_mm,
    rain_hydrological_year_mm,
    rain_anomaly,
    temperature_mean_c,
    temperature_anomaly_c,
    hot_days
from climatology
