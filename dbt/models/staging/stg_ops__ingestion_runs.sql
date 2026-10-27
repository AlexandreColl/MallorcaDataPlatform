select
    run_id,
    source,
    region,
    window_start,
    window_end,
    status,
    payloads,
    rows_silver,
    rows_upserted,
    started_at,
    finished_at,
    extract(epoch from finished_at - started_at) as duration_s,
    error,
    -- the exception type recorded by the pipeline (e.g. ConnectTimeout) tells an upstream outage from a bug
    split_part(error, ':', 1) as error_type
from {{ source('ops', 'ingestion_runs') }}
