-- One row per earthquake: magnitude, depth and distance from Palma.
with observations as (
    select *
    from {{ ref('stg_observations') }}
    where source = 'ign' and quality <> 'missing'
),

-- Agencies revise locations: a later run may bring the same event with another origin time.
-- Silver keeps every version (its key includes ts); gold uses the latest one ingested.
latest as (
    select distinct on (entity) entity, ts
    from observations
    order by entity, ingested_at desc, ts desc
),

events as (
    select
        o.entity as event_id,
        o.ts,
        min(o.local_date) as local_date,
        round(avg(o.lat)::numeric, 4)::double precision as lat,
        round(avg(o.lon)::numeric, 4)::double precision as lon,
        max(o.value) filter (where o.metric = 'magnitude') as magnitude,
        max(o.value) filter (where o.metric = 'depth_km') as depth_km,
        bool_or(o.quality = 'suspect') as is_suspect,
        string_agg(distinct o.quality_reasons, ';') as quality_reasons
    from observations as o
    inner join latest as l on o.entity = l.entity and o.ts = l.ts
    group by o.entity, o.ts
)

select
    *,
    -- Haversine distance to Palma (39.5696 N, 2.6502 E), in km.
    round((2 * 6371 * asin(sqrt(
        power(sin(radians(lat - 39.5696) / 2), 2)
        + cos(radians(39.5696)) * cos(radians(lat)) * power(sin(radians(lon - 2.6502) / 2), 2)
    )))::numeric, 1)::double precision as distance_to_palma_km
from events
