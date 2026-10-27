select
    run_id,
    source,
    rule,
    target,
    checked,
    failed,
    passed,
    details,
    window_start,
    window_end,
    created_at
from {{ source('quality', 'check_results') }}
