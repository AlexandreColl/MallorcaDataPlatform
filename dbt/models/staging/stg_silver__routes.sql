-- Lines of the transit networks (silver.routes), one row per source and route, with their path as GeoJSON.
select
    source,
    route,
    short_name,
    name,
    kind,
    color,
    geometry,
    updated_at
from {{ source('silver', 'routes') }}
