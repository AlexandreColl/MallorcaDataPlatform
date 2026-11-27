-- The sea around Mallorca per month, from the satellite: the mean surface temperature of the coastal points, its
-- anomaly against the 1991-2020 climatology of the same days, and the marine heatwave days (the mean of the points,
-- and the days with a heatwave at any of them). The same shape as fct_climate_monthly, so the anomaly of the sea
-- reads next to that of the air.
with points_month as (
    select
        date_trunc('month', day)::date as month,
        point,
        count(*) as days_reported,
        avg(sst_c) as sst_mean_c,
        avg(sst_climatology_c) as sst_climatology_c,
        count(*) filter (where is_marine_heatwave) as heatwave_days,
        bool_or(is_preliminary) as has_preliminary_days
    from {{ ref('fct_sea_temperature_daily') }}
    group by date_trunc('month', day)::date, point
),

any_point as (
    select
        date_trunc('month', day)::date as month,
        count(distinct day) filter (where is_marine_heatwave) as days_with_heatwave
    from {{ ref('fct_sea_temperature_daily') }}
    group by date_trunc('month', day)::date
)

select
    p.month,
    count(*) as points,
    max(p.days_reported) as days_reported,
    round(avg(p.sst_mean_c)::numeric, 2)::numeric(5, 2) as sst_mean_c,
    round(avg(p.sst_climatology_c)::numeric, 2)::numeric(5, 2) as sst_climatology_c,
    round(avg(p.sst_mean_c - p.sst_climatology_c)::numeric, 2)::numeric(5, 2) as sst_anomaly_c,
    round(avg(p.heatwave_days)::numeric, 1)::numeric(4, 1) as heatwave_days,
    max(a.days_with_heatwave) as days_with_heatwave,
    bool_or(p.has_preliminary_days) as has_preliminary_days
from points_month as p
inner join any_point as a on p.month = a.month
group by p.month
