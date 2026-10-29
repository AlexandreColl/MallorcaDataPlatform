-- Hourly air quality per location with the European Air Quality Index band
-- (1 = good ... 6 = extremely poor), computed from the worst pollutant.
with pivoted as (
    select
        source,
        entity,
        ts,
        max(value) filter (where metric = 'pm2_5') as pm2_5,
        max(value) filter (where metric = 'pm10') as pm10,
        max(value) filter (where metric = 'nitrogen_dioxide') as no2,
        max(value) filter (where metric = 'ozone') as o3,
        max(value) filter (where metric = 'european_aqi') as european_aqi_model,
        bool_or(is_suspect) as has_suspect
    from {{ ref('fct_observations') }}
    where
        metric in ('pm2_5', 'pm10', 'nitrogen_dioxide', 'ozone', 'european_aqi')
        -- The GOIB history (two million station hours up to 2021) would make this table rebuild slowly every run;
        -- it is read monthly in fct_air_quality_monthly.
        and source <> 'goib_air_quality'
    group by source, entity, ts
),

banded as (
    select
        *,
        case
            when pm2_5 is null then null when pm2_5 <= 10 then 1 when pm2_5 <= 20 then 2
            when pm2_5 <= 25 then 3 when pm2_5 <= 50 then 4 when pm2_5 <= 75 then 5 else 6
        end as band_pm2_5,
        case
            when pm10 is null then null when pm10 <= 20 then 1 when pm10 <= 40 then 2
            when pm10 <= 50 then 3 when pm10 <= 100 then 4 when pm10 <= 150 then 5 else 6
        end as band_pm10,
        case
            when no2 is null then null when no2 <= 40 then 1 when no2 <= 90 then 2
            when no2 <= 120 then 3 when no2 <= 230 then 4 when no2 <= 340 then 5 else 6
        end as band_no2,
        case
            when o3 is null then null when o3 <= 50 then 1 when o3 <= 100 then 2
            when o3 <= 130 then 3 when o3 <= 240 then 4 when o3 <= 380 then 5 else 6
        end as band_o3
    from pivoted
)

select
    source,
    entity,
    ts,
    pm2_5,
    pm10,
    no2,
    o3,
    european_aqi_model,
    greatest(band_pm2_5, band_pm10, band_no2, band_o3) as eaqi_band,
    case greatest(band_pm2_5, band_pm10, band_no2, band_o3)
        when 1 then 'good' when 2 then 'fair' when 3 then 'moderate'
        when 4 then 'poor' when 5 then 'very poor' when 6 then 'extremely poor'
    end as eaqi_label,
    has_suspect
from banded
