-- Station vs model, one row per station and day: what the station measured, what the Open-Meteo model said at the
-- nearest point, and the difference (model minus observation: positive = the model overestimates).
-- Only complete days on both sides are compared.
with daily as (
    select * from {{ ref('fct_weather_daily') }}
    where is_complete_day
)

select
    p.station_source,
    p.station,
    p.model_point,
    p.distance_km,
    obs.local_date,
    obs.season,
    obs.temperature_mean as temperature_mean_obs,
    model.temperature_mean as temperature_mean_model,
    model.temperature_mean - obs.temperature_mean as temperature_mean_bias,
    model.temperature_max - obs.temperature_max as temperature_max_bias,
    model.temperature_min - obs.temperature_min as temperature_min_bias,
    obs.precipitation_sum as precipitation_obs,
    model.precipitation_sum as precipitation_model,
    model.precipitation_sum - obs.precipitation_sum as precipitation_bias,
    -- did both agree on whether it was a rainy day (>= 1 mm)?
    case
        when obs.precipitation_sum is null or model.precipitation_sum is null then null
        else (obs.precipitation_sum >= 1) = (model.precipitation_sum >= 1)
    end as rain_day_agrees,
    model.wind_speed_mean - obs.wind_speed_mean as wind_speed_bias,
    model.humidity_mean - obs.humidity_mean as humidity_bias
from {{ ref('int_station_model_pairs') }} as p
inner join daily as obs on p.station_source = obs.source and p.station = obs.entity
inner join daily as model
    on model.source = 'open_meteo' and p.model_point = model.entity and obs.local_date = model.local_date
