-- Analysis-ready observations: every non-missing value with its quality label.
select
    source,
    entity,
    metric,
    ts,
    local_date,
    value,
    unit,
    quality,
    quality = 'suspect' as is_suspect,
    quality_reasons
from {{ ref('stg_observations') }}
where quality <> 'missing'
