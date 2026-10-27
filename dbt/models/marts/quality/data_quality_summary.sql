-- Latest result of every quality check per source / rule / target.
with ranked as (
    select
        *,
        row_number() over (
            partition by source, rule, target order by created_at desc
        ) as rn
    from {{ ref('stg_quality__check_results') }}
)

select
    source,
    rule,
    target,
    checked,
    failed,
    passed,
    case when checked > 0 then round(failed::numeric / checked, 4) end as failed_ratio,
    details,
    window_start,
    window_end,
    run_id,
    created_at as checked_at
from ranked
where rn = 1
