-- Analysis-ready observations: every non-missing value with its quality label.
--
-- Incremental: each run merges only the silver rows inserted or changed since the last build (silver's
-- `updated_at` is the watermark, minus a safety lookback for rows committed while dbt was reading). Sources
-- that publish late (AEMET) need nothing special: a late day gets a new `updated_at` when it lands.
-- A value that becomes missing in silver is merged too and then removed by the post-hook, so the table never
-- keeps a stale value. `dbt build --full-refresh` rebuilds it from scratch.
{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['source', 'entity', 'metric', 'ts'],
        on_schema_change='append_new_columns',
        post_hook="delete from {{ this }} where is_missing",
        indexes=[
            {'columns': ['source', 'entity', 'metric', 'ts'], 'unique': true},
            {'columns': ['metric', 'ts']},
            {'columns': ['updated_at']},
        ],
    )
}}

select
    source,
    entity,
    metric,
    ts,
    local_date,
    value,
    unit,
    quality,
    is_suspect,
    is_missing,
    quality_reasons,
    updated_at
from {{ ref('stg_silver__observations') }}
{% if is_incremental() %}
where
    updated_at > (
        select coalesce(max(built.updated_at), '-infinity'::timestamptz) - interval '{{ var("incremental_lookback") }}'
        from {{ this }} as built
    )
{% else %}
where not is_missing
{% endif %}
