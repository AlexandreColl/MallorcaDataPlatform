-- One row per earthquake: magnitude, depth and distance from Palma.
with observations as (
    select *
    from {{ ref('stg_ign__observations') }}
    where not is_missing
),

-- Agencies revise locations: a later run may bring the same event with another origin time.
-- Silver keeps every version (its key includes ts); gold uses the latest one ingested.
latest as (
    select distinct on (entity)
        entity,
        ts
    from observations
    order by entity asc, ingested_at desc, ts desc
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
    -- distance to Palma (var palma: 39.5696 N, 2.6502 E)
    round({{ haversine_km(var("palma")["lat"], var("palma")["lon"], "lat", "lon") }}::numeric, 1)::double precision
        as distance_to_palma_km
from events
