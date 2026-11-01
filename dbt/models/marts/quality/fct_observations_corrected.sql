-- Station observations with their proposed corrections side by side: the original value, the corrected one and
-- `value`, the corrected value where there is one and the original elsewhere. silver.observations is never changed.
-- Hours without a valid value (missing, suspect or without a row) that core/corrections could estimate get a row
-- with the method, the support series and the confidence; hours it could not estimate keep no value.
-- Only the sources and the period with corrections are kept, so the table stays small.
with corrections as (
    select * from {{ ref('stg_silver__corrections') }}
),

observed as (
    select
        source,
        entity,
        metric,
        ts,
        local_date,
        value,
        unit,
        quality
    from {{ ref('fct_observations') }}
    where
        source in (select distinct c.source from corrections as c)
        and ts >= (select min(c.ts) from corrections as c)
)

select
    coalesce(o.source, c.source) as source,
    coalesce(o.entity, c.entity) as entity,
    coalesce(o.metric, c.metric) as metric,
    coalesce(o.ts, c.ts) as ts,
    coalesce(o.local_date, c.local_date) as local_date,
    coalesce(o.unit, c.unit) as unit,
    coalesce(o.quality, c.original_quality) as original_quality,
    coalesce(o.value, c.original_value) as original_value,
    c.corrected_value,
    coalesce(c.corrected_value, o.value) as value,
    c.corrected_value is not null as is_corrected,
    c.method as correction_method,
    c.support_source,
    c.support_entity,
    c.bias as support_bias,
    c.confidence
from observed as o
full outer join corrections as c
    on
        o.source = c.source
        and o.entity = c.entity
        and o.metric = c.metric
        and o.ts = c.ts
