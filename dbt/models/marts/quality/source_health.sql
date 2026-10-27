-- One row per source: is it up to date, how often it failed lately and how fresh its data is.
with runs as (
    select * from {{ ref('stg_ops__ingestion_runs') }}
    where status <> 'running'
),

last_run as (
    select distinct on (source)
        source,
        status as last_status,
        finished_at as last_run_at,
        error_type as last_error_type
    from runs
    order by source, started_at desc
),

stats as (
    select
        source,
        max(finished_at) filter (where status = 'success') as last_success_at,
        count(*) filter (where started_at > now() - interval '7 days') as runs_7d,
        count(*) filter (where started_at > now() - interval '7 days' and status = 'failed') as failed_7d,
        max(window_end) filter (where status = 'success') as last_loaded_day
    from runs
    group by source
),

data as (
    select source, max(ts) as latest_observation_ts, count(*) as observations
    from {{ ref('fct_observations') }}
    group by source
)

select
    s.source,
    s.label,
    s.kind,
    l.last_status,
    l.last_run_at,
    l.last_error_type,
    st.last_success_at,
    st.last_loaded_day,
    coalesce(st.runs_7d, 0) as runs_7d,
    coalesce(st.failed_7d, 0) as failed_7d,
    round(st.failed_7d::numeric / nullif(st.runs_7d, 0), 3) as failure_rate_7d,
    d.latest_observation_ts,
    round((extract(epoch from now() - d.latest_observation_ts) / 3600)::numeric, 1) as data_age_hours,
    coalesce(d.observations, 0) as observations
from {{ ref('dim_sources') }} as s
left join last_run as l on s.source = l.source
left join stats as st on s.source = st.source
left join data as d on s.source = d.source
