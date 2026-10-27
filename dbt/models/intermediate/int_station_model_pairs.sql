-- Each observation station (AEMET, SOCIB) paired with the nearest Open-Meteo model point, if one lies within
-- `model_pairing_max_km`. The pairing is what lets us measure how far the model is from reality.
with stations as (
    select
        l.source,
        l.entity,
        l.lat,
        l.lon
    from {{ ref('dim_locations') }} as l
    inner join {{ ref('dim_sources') }} as s on l.source = s.source
    where s.kind = 'observation' and l.lat is not null
),

model_points as (
    select
        entity,
        lat,
        lon
    from {{ ref('dim_locations') }}
    where source = 'open_meteo'
)

select
    st.source as station_source,
    st.entity as station,
    nearest.entity as model_point,
    round(nearest.distance_km::numeric, 1)::double precision as distance_km
from stations as st
cross join
    lateral (
        select
            m.entity,
            {{ haversine_km('st.lat', 'st.lon', 'm.lat', 'm.lon') }} as distance_km
        from model_points as m
        order by distance_km
        limit 1
    ) as nearest
where nearest.distance_km <= {{ var('model_pairing_max_km') }}
