-- Proposed corrections of station values (core/corrections), with the local day of each hour.
select
    source,
    entity,
    metric,
    ts,
    (ts at time zone '{{ var("local_timezone") }}')::date as local_date,
    unit,
    original_value,
    original_quality,
    corrected_value,
    method,
    support_source,
    support_entity,
    bias,
    confidence,
    run_id,
    corrected_at
from {{ source('silver', 'corrections') }}
