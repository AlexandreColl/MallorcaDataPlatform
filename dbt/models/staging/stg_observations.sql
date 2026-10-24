select
    source,
    entity,
    metric,
    ts,
    (ts at time zone 'Europe/Madrid')::date as local_date,
    value,
    unit,
    quality,
    quality_reasons,
    lat,
    lon,
    run_id,
    ingested_at
from {{ source('silver', 'observations') }}
