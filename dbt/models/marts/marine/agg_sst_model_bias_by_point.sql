-- How close the sea surface temperature of Open-Meteo Marine is to the satellite at each coastal point: mean bias,
-- mean absolute error, RMSE and correlation of the daily values, the mean of each side and the days compared.
select
    point,
    count(*) as days_compared,
    round(avg(sst_satellite_c)::numeric, 2)::numeric(5, 2) as sst_satellite_mean_c,
    round(avg(sst_model_c)::numeric, 2)::numeric(5, 2) as sst_model_mean_c,
    round(avg(sst_bias_c)::numeric, 2)::numeric(5, 2) as sst_bias_c,
    round(avg(abs(sst_bias_c))::numeric, 2)::numeric(5, 2) as sst_mae_c,
    round(sqrt(avg(power(sst_bias_c, 2)))::numeric, 2)::numeric(5, 2) as sst_rmse_c,
    round(corr(sst_satellite_c, sst_model_c)::numeric, 3)::numeric(4, 3) as sst_correlation,
    min(day) as first_day,
    max(day) as last_day
from {{ ref('fct_sst_model_comparison_daily') }}
group by point
