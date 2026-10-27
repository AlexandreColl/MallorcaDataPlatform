-- How good is the model at each station: mean bias, mean absolute error and RMSE of the daily mean temperature,
-- total rain bias and how often model and station agree on a rainy day. Input for the future corrections phase.
select
    station_source,
    station,
    model_point,
    distance_km,
    count(*) as days_compared,
    round(avg(temperature_mean_bias)::numeric, 2) as temperature_bias_c,
    round(avg(abs(temperature_mean_bias))::numeric, 2) as temperature_mae_c,
    round(sqrt(avg(power(temperature_mean_bias, 2)))::numeric, 2) as temperature_rmse_c,
    round(sum(precipitation_bias)::numeric, 1) as precipitation_bias_total_mm,
    round(avg(rain_day_agrees::int)::numeric, 3) as rain_day_agreement,
    round(avg(wind_speed_bias)::numeric, 2) as wind_speed_bias_kmh,
    min(local_date) as first_day,
    max(local_date) as last_day
from {{ ref('fct_model_bias_daily') }}
group by station_source, station, model_point, distance_km
