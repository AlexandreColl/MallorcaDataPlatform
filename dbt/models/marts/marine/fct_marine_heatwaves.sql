-- One row per marine heatwave of a coastal point (Hobday et al., 2016; see fct_sea_temperature_daily): its days,
-- its intensity above the climatology (peak, mean and accumulated in degree-days) and the category of Hobday et al.
-- (2018), which counts the peak in multiples of the gap between the 90th percentile and the climatology:
-- 1-2 moderate, 2-3 strong, 3-4 severe, 4 or more extreme.
with heatwave_days as (
    select
        heatwave_id,
        point,
        day,
        sst_c,
        sst_anomaly_c,
        is_preliminary,
        sst_anomaly_c / nullif(sst_p90_c - sst_climatology_c, 0) as threshold_multiple
    from {{ ref('fct_sea_temperature_daily') }}
    where is_marine_heatwave
),

peaks as (
    select distinct on (heatwave_id)
        heatwave_id,
        day as peak_day,
        sst_c as peak_sst_c
    from heatwave_days
    order by heatwave_id asc, sst_anomaly_c desc nulls last
)

select
    h.heatwave_id,
    h.point,
    min(h.day) as start_date,
    max(h.day) as end_date,
    (max(h.day) - min(h.day) + 1)::integer as days,
    max(p.peak_day) as peak_day,
    max(p.peak_sst_c) as peak_sst_c,
    max(h.sst_anomaly_c) as max_intensity_c,
    round(avg(h.sst_anomaly_c), 2)::numeric(5, 2) as mean_intensity_c,
    round(sum(h.sst_anomaly_c), 1)::numeric(7, 1) as cumulative_intensity_c_days,
    case
        when max(h.threshold_multiple) >= 4 then 'extreme'
        when max(h.threshold_multiple) >= 3 then 'severe'
        when max(h.threshold_multiple) >= 2 then 'strong'
        else 'moderate'
    end as category,
    bool_or(h.is_preliminary) as has_preliminary_days
from heatwave_days as h
inner join peaks as p on h.heatwave_id = p.heatwave_id
group by h.heatwave_id, h.point
