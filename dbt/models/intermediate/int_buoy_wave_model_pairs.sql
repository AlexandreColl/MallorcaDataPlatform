-- Each SOCIB buoy that measures waves paired with the nearest Open-Meteo Marine point, if one lies within
-- `model_pairing_max_km`: the wave counterpart of int_station_model_pairs.
with buoys as (
    select distinct
        o.entity,
        l.lat,
        l.lon
    from {{ ref('stg_socib__observations') }} as o
    inner join {{ ref('dim_locations') }} as l on o.source = l.source and o.entity = l.entity
    where o.metric = 'wave_height' and l.lat is not null
),

model_points as (
    select
        entity,
        lat,
        lon
    from {{ ref('dim_locations') }}
    where source = 'open_meteo_marine'
)

select
    b.entity as buoy,
    nearest.entity as model_point,
    round(nearest.distance_km::numeric, 1)::double precision as distance_km
from buoys as b
cross join
    lateral (
        select
            m.entity,
            {{ haversine_km('b.lat', 'b.lon', 'm.lat', 'm.lon') }} as distance_km
        from model_points as m
        order by distance_km
        limit 1
    ) as nearest
where nearest.distance_km <= {{ var('model_pairing_max_km') }}
