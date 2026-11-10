-- Names and heights of the stops and stations (silver.entities), one row per source and entity.
select
    source,
    entity,
    name,
    elevation_m,
    updated_at
from {{ source('silver', 'entities') }}
