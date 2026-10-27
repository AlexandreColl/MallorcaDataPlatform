{#- Standard projection of silver observations, shared by every staging model.
    `connector` = none reads every source; otherwise the source table declared for that connector
    (same physical table, filtered) so freshness and lineage are tracked per connector. -#}
{% macro staging_observations(connector=none) -%}
select
    source,
    entity,
    metric,
    ts,
    (ts at time zone '{{ var("local_timezone") }}')::date as local_date,
    value,
    unit,
    quality,
    quality_reasons,
    quality = 'missing' as is_missing,
    quality = 'suspect' as is_suspect,
    lat,
    lon,
    run_id,
    ingested_at,
    updated_at
{% if connector is none -%}
from {{ source('silver', 'observations') }}
{%- else -%}
from {{ source('silver', connector) }}
where source = '{{ connector }}'
{%- endif %}
{%- endmacro %}
