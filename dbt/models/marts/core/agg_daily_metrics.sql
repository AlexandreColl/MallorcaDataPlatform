-- Daily statistics per series (local Mallorca day) and completeness.
--
-- Incremental (delete+insert): only the series-days touched by silver rows changed since the last build are
-- recomputed, always from every sample of that day, so a late hour updates its day instead of adding a row.
{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key=['source', 'entity', 'metric', 'local_date'],
        on_schema_change='append_new_columns',
        indexes=[{'columns': ['source', 'entity', 'metric', 'local_date'], 'unique': true}],
    )
}}

with observations as (
    select *
    from {{ ref('stg_silver__observations') }}
    where source not in {{ event_sources() }}
),

{% if is_incremental() %}
changed_days as (
    select distinct source, entity, metric, local_date
    from observations
    where updated_at > (
        select coalesce(max(last_updated_at), '-infinity'::timestamptz) - interval '{{ var("incremental_lookback") }}'
        from {{ this }}
    )
),
{% endif %}

days as (
    select o.*
    from observations as o
    {% if is_incremental() %}
    inner join changed_days using (source, entity, metric, local_date)
    {% endif %}
)

select
    source,
    entity,
    metric,
    local_date,
    max(unit) as unit,
    count(*) as n_samples,
    count(*) filter (where not is_missing) as n_valid,
    count(*) filter (where is_suspect) as n_suspect,
    min(value) filter (where quality = 'ok') as min_value,
    avg(value) filter (where quality = 'ok') as avg_value,
    max(value) filter (where quality = 'ok') as max_value,
    round((count(*) filter (where not is_missing))::numeric / nullif(count(*), 0), 4) as completeness,
    max(updated_at) as last_updated_at
from days
group by source, entity, metric, local_date
