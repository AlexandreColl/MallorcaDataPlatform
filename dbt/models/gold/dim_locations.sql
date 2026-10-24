select
    source,
    entity,
    avg(lat) as lat,
    avg(lon) as lon,
    min(ts) as first_seen,
    max(ts) as last_seen,
    count(distinct metric) as n_metrics
from {{ ref('stg_observations') }}
group by source, entity
