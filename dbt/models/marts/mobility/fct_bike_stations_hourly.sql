-- BiciPalma, one row per station and UTC hour: free bikes, e-bikes and free docks (mean, minimum and maximum of the
-- 5-minute snapshots of that hour) and the mean occupancy. `was_empty` and `was_full` say whether the station ran out
-- of bikes or of docks at some moment of the hour, which the mean hides.
--
-- Incremental (delete+insert): only the station-hours whose silver rows changed since the last build are recomputed.
{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['station', 'ts'],
        on_schema_change='append_new_columns',
        indexes=[{'columns': ['station', 'ts'], 'unique': true}, {'columns': ['local_date']}],
    )
}}

with observations as (
    select *
    from {{ ref('stg_bicipalma__observations') }}
    where not is_missing
),

{% if is_incremental() %}
changed as (
    select distinct
        entity,
        ts
    from observations
    where updated_at > (
        select
            coalesce(max(built.last_updated_at), '-infinity'::timestamptz)
            - interval '{{ var("incremental_lookback") }}'
        from {{ this }} as built
    )
),
{% endif %}

hours as (
    select
        o.entity as station,
        o.ts,
        min(o.local_date) as local_date,
        avg(o.lat) as lat,
        avg(o.lon) as lon,
        max(o.value) filter (where o.metric = 'bikes_available') as bikes_available,
        max(o.value) filter (where o.metric = 'bikes_available_min') as bikes_available_min,
        max(o.value) filter (where o.metric = 'bikes_available_max') as bikes_available_max,
        max(o.value) filter (where o.metric = 'ebikes_available') as ebikes_available,
        max(o.value) filter (where o.metric = 'docks_available') as docks_available,
        max(o.value) filter (where o.metric = 'docks_available_min') as docks_available_min,
        max(o.value) filter (where o.metric = 'docks_available_max') as docks_available_max,
        max(o.value) filter (where o.metric = 'occupancy') as occupancy_pct,
        bool_or(o.is_suspect) as has_suspect,
        max(o.updated_at) as last_updated_at
    from observations as o
    {% if is_incremental() %}
    inner join changed as c on o.entity = c.entity and o.ts = c.ts
    {% endif %}
    group by o.entity, o.ts
)

select
    h.station,
    e.name as station_name,
    round(h.lat::numeric, 6)::double precision as lat,
    round(h.lon::numeric, 6)::double precision as lon,
    h.ts,
    h.local_date,
    extract(hour from h.ts at time zone '{{ var("local_timezone") }}')::integer as local_hour,
    round(h.bikes_available::numeric, 2)::numeric(6, 2) as bikes_available,
    h.bikes_available_min::integer as bikes_available_min,
    h.bikes_available_max::integer as bikes_available_max,
    round(h.ebikes_available::numeric, 2)::numeric(6, 2) as ebikes_available,
    round(h.docks_available::numeric, 2)::numeric(6, 2) as docks_available,
    h.docks_available_min::integer as docks_available_min,
    h.docks_available_max::integer as docks_available_max,
    round(h.occupancy_pct::numeric, 1)::numeric(5, 1) as occupancy_pct,
    h.bikes_available_min = 0 as was_empty,
    h.docks_available_min = 0 as was_full,
    h.has_suspect,
    h.last_updated_at
from hours as h
left join {{ ref('stg_silver__entities') }} as e on e.source = 'bicipalma' and h.station = e.entity
