-- Each observation station (AEMET, SOCIB) paired with the nearest Open-Meteo model point, if one lies within
-- `model_pairing_max_km`. The pairing is what lets us measure how far the model is from reality. The heights of
-- both (where the source publishes them) let fct_model_bias_daily compare them at the same altitude.
with stations as (
    select
        l.source,
        l.entity,
        l.lat,
        l.lon,
        l.elevation_m
    from {{ ref('dim_locations') }} as l
    inner join {{ ref('dim_sources') }} as s on l.source = s.source
    where s.kind = 'observation' and l.lat is not null
),

model_points as (
    select
        entity,
        lat,
        lon,
        elevation_m
    from {{ ref('dim_locations') }}
    where source = 'open_meteo'
)

select
    st.source as station_source,
    st.entity as station,
    nearest.entity as model_point,
    round(nearest.distance_km::numeric, 1)::double precision as distance_km,
    st.elevation_m as station_elevation_m,
    nearest.elevation_m as model_elevation_m,
    -- positive = the station stands higher than the terrain the model sees; null if either height is unknown
    st.elevation_m - nearest.elevation_m as elevation_diff_m
from stations as st
cross join
    lateral (
        select
            m.entity,
            m.elevation_m,
            {{ haversine_km('st.lat', 'st.lon', 'm.lat', 'm.lon') }} as distance_km
        from model_points as m
        order by distance_km
        limit 1
    ) as nearest
where nearest.distance_km <= {{ var('model_pairing_max_km') }}
