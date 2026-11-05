-- AEMET warnings as periods: consecutive hours of one zone and phenomenon at the same level (yellow, orange or
-- red), built with gaps and islands. Hours at level 0 (no risk) close a warning; a change of level starts a new one.
with warning_hours as (
    select
        entity as zone,
        metric as phenomenon,
        ts,
        value::int as level
    from {{ ref('stg_aemet_warnings__observations') }}
    where value > 0
),

islands as (
    select
        *,
        ts - (row_number() over (partition by zone, phenomenon, level order by ts)) * interval '1 hour' as island
    from warning_hours
)

select
    {{ dbt_utils.generate_surrogate_key(["i.zone", "i.phenomenon", "min(i.ts)"]) }} as warning_id,
    i.zone,
    z.name as zone_name,
    z.kind as zone_kind,
    replace(i.phenomenon, 'warning_', '') as phenomenon,
    i.level,
    min(i.ts) as start_ts,
    max(i.ts) + interval '1 hour' as end_ts,
    count(*) as hours
from islands as i
left join {{ ref('dim_warning_zones') }} as z on i.zone = z.zone
group by i.zone, z.name, z.kind, i.phenomenon, i.level, i.island
