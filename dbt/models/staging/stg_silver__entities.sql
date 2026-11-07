-- Names of the stops and stations (silver.entities), one row per source and entity.
select
    source,
    entity,
    name,
    updated_at
from {{ source('silver', 'entities') }}
