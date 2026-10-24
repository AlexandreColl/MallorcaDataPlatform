-- Daily statistics per series (local Mallorca day) and completeness.
select
    source,
    entity,
    metric,
    local_date,
    max(unit) as unit,
    count(*) as n_samples,
    count(*) filter (where quality <> 'missing') as n_valid,
    count(*) filter (where quality = 'suspect') as n_suspect,
    min(value) filter (where quality = 'ok') as min_value,
    avg(value) filter (where quality = 'ok') as avg_value,
    max(value) filter (where quality = 'ok') as max_value,
    round(
        (count(*) filter (where quality <> 'missing'))::numeric / nullif(count(*), 0), 4
    ) as completeness
from {{ ref('stg_observations') }}
group by source, entity, metric, local_date
