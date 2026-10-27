-- Sea state per coastal point and hour (Open-Meteo Marine model), one column per variable.
select
    o.entity as point,
    l.lat,
    l.lon,
    o.ts,
    o.local_date,
    max(o.value) filter (where o.metric = 'wave_height') as wave_height_m,
    max(o.value) filter (where o.metric = 'wave_period') as wave_period_s,
    max(o.value) filter (where o.metric = 'wave_direction') as wave_direction_deg,
    max(o.value) filter (where o.metric = 'swell_wave_height') as swell_height_m,
    max(o.value) filter (where o.metric = 'sea_surface_temperature') as sea_temperature_c,
    max(o.value) filter (where o.metric = 'ocean_current_velocity') as current_kmh,
    max(o.value) filter (where o.metric = 'sea_level_height_msl') as sea_level_m,
    bool_or(o.is_suspect) as has_suspect
from {{ ref('stg_open_meteo_marine__observations') }} as o
left join {{ ref('dim_locations') }} as l on o.source = l.source and o.entity = l.entity
where not o.is_missing
group by o.entity, l.lat, l.lon, o.ts, o.local_date
