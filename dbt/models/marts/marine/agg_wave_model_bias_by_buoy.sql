-- How good the wave model is at each SOCIB buoy: mean bias, mean absolute error, RMSE and correlation of the hourly
-- significant wave height, the mean of each side and the share of the buoy's height the model gives (`model_ratio`):
-- a coastal buoy in a sheltered bay sees less sea than a ~5 km model cell exposed to the open water.
select
    buoy,
    model_point,
    distance_km,
    count(*) as hours_compared,
    round(avg(wave_height_buoy_m)::numeric, 2)::numeric(6, 2) as wave_height_buoy_mean_m,
    round(avg(wave_height_model_m)::numeric, 2)::numeric(6, 2) as wave_height_model_mean_m,
    round(avg(wave_height_bias_m)::numeric, 2)::numeric(6, 2) as wave_height_bias_m,
    round(avg(abs(wave_height_bias_m))::numeric, 2)::numeric(6, 2) as wave_height_mae_m,
    round(sqrt(avg(power(wave_height_bias_m, 2)))::numeric, 2)::numeric(6, 2) as wave_height_rmse_m,
    round(corr(wave_height_buoy_m, wave_height_model_m)::numeric, 3)::numeric(4, 3) as wave_height_correlation,
    round((avg(wave_height_model_m) / nullif(avg(wave_height_buoy_m), 0))::numeric, 2)::numeric(6, 2) as model_ratio,
    min(ts) as first_ts,
    max(ts) as last_ts
from {{ ref('fct_wave_model_comparison_hourly') }}
group by buoy, model_point, distance_km
