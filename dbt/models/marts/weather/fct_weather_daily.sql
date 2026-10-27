-- One row per weather station or model point and local day, comparable across sources:
-- real observations (AEMET, SOCIB) next to the Open-Meteo model.
select
    w.source,
    s.label as source_label,
    s.kind as source_kind,
    w.entity,
    l.lat,
    l.lon,
    w.local_date,
    d.season,
    d.is_weekend,
    w.temperature_mean,
    w.temperature_min,
    w.temperature_max,
    w.precipitation_sum,
    w.humidity_mean,
    w.wind_speed_mean,
    w.wind_gust_max,
    w.hours_observed,
    -- daily at origin, or at least 20 of the 24 hours: safe to compare
    coalesce(w.hours_observed >= 20, true) as is_complete_day
from {{ ref('int_weather__daily') }} as w
inner join {{ ref('dim_sources') }} as s on w.source = s.source
left join {{ ref('dim_locations') }} as l on w.source = l.source and w.entity = l.entity
left join {{ ref('dim_date') }} as d on w.local_date = d.date_day
