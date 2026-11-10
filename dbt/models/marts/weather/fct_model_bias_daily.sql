-- Station vs model, one row per station and day: what the station measured, what the Open-Meteo model said at the
-- nearest point, and the difference (model minus observation: positive = the model overestimates).
-- Only complete days on both sides are compared.
--
-- A mountain station stands hundreds of metres above the terrain of its model cell, so the raw temperature bias
-- mixes the error of the model with the altitude: Lluc (490 m) against a cell at 150 m reads ~2 °C colder for that
-- alone. The `_adjusted` biases first bring the model to the height of the station with the standard lapse rate
-- (`lapse_rate_c_per_km`, 6.5 °C per km) and are what is left of the model's own error. Without both heights the
-- adjustment is 0 and the adjusted bias equals the raw one.
with daily as (
    select * from {{ ref('fct_weather_daily') }}
    where is_complete_day
),

pairs as (
    select
        *,
        -- what the model's temperature changes when brought to the station's height: negative above the cell
        coalesce(-{{ var('lapse_rate_c_per_km') }} * elevation_diff_m / 1000.0, 0) as altitude_adjustment_c
    from {{ ref('int_station_model_pairs') }}
)

select
    p.station_source,
    p.station,
    p.model_point,
    p.distance_km,
    p.elevation_diff_m,
    p.altitude_adjustment_c,
    obs.local_date,
    obs.season,
    obs.temperature_mean as temperature_mean_obs,
    model.temperature_mean as temperature_mean_model,
    model.temperature_mean - obs.temperature_mean as temperature_mean_bias,
    model.temperature_max - obs.temperature_max as temperature_max_bias,
    model.temperature_min - obs.temperature_min as temperature_min_bias,
    model.temperature_mean + p.altitude_adjustment_c - obs.temperature_mean as temperature_mean_bias_adjusted,
    model.temperature_max + p.altitude_adjustment_c - obs.temperature_max as temperature_max_bias_adjusted,
    model.temperature_min + p.altitude_adjustment_c - obs.temperature_min as temperature_min_bias_adjusted,
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
from pairs as p
inner join daily as obs on p.station_source = obs.source and p.station = obs.entity
inner join daily as model
    on model.source = 'open_meteo' and p.model_point = model.entity and obs.local_date = model.local_date
