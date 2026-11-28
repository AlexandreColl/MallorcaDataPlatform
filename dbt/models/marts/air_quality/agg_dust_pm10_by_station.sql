-- PM10 of each official station (EEA) on dust days and on the other days, with the CAMS PM10 of its nearest model
-- point: how much the Saharan dust adds at the station, and how far the model is from it on each kind of day. The
-- PM10 corrections fill station gaps with CAMS (config/corrections.yaml), so a model that errs more on dust days
-- shows here.
with days as (
    select
        pm.station,
        pm.model_point,
        pm.local_date,
        pm.station_mean_ugm3,
        pm.model_mean_ugm3,
        d.is_dust_day
    from {{ ref('fct_air_quality_model_bias_daily') }} as pm
    inner join {{ ref('int_dust__daily') }} as d on pm.local_date = d.local_date
    where pm.metric = 'pm10'
)

select
    station,
    max(model_point) as model_point,
    (count(*) filter (where is_dust_day))::integer as dust_days,
    (count(*) filter (where not is_dust_day))::integer as other_days,
    round((avg(station_mean_ugm3) filter (where is_dust_day))::numeric, 1)::double precision as pm10_dust_days_ugm3,
    round((avg(station_mean_ugm3) filter (where not is_dust_day))::numeric, 1)::double precision
        as pm10_other_days_ugm3,
    round(
        (
            avg(station_mean_ugm3) filter (where is_dust_day)
            - avg(station_mean_ugm3) filter (where not is_dust_day)
        )::numeric,
        1
    )::double precision as pm10_excess_ugm3,
    round((avg(model_mean_ugm3 - station_mean_ugm3) filter (where is_dust_day))::numeric, 1)::double precision
        as model_bias_dust_days_ugm3,
    round((avg(model_mean_ugm3 - station_mean_ugm3) filter (where not is_dust_day))::numeric, 1)::double precision
        as model_bias_other_days_ugm3,
    min(local_date) as first_day,
    max(local_date) as last_day
from days
group by station
