-- One row per source: is it up to date, how often it failed lately, how fresh its data is, and whether it meets the
-- SLA agreed in its catalogue entry (dim_sources), next to the rest of its governance.
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
    order by source asc, started_at desc
),

stats as (
    select
        source,
        max(finished_at) filter (where status = 'success') as last_success_at,
        count(*) filter (where started_at > now() - interval '7 days') as runs_7d,
        -- failed: our side (to fix); unavailable: the source was down (it recovers by itself)
        count(*) filter (where started_at > now() - interval '7 days' and status = 'failed') as failed_7d,
        count(*) filter (where started_at > now() - interval '7 days' and status = 'unavailable') as unavailable_7d,
        max(window_end) filter (where status = 'success') as last_loaded_day
    from runs
    group by source
),

data as (
    select
        source,
        max(ts) as latest_observation_ts,
        count(*) as observations
    from {{ ref('fct_observations') }}
    group by source
),

health as (
    select
        s.source,
        s.label,
        s.kind,
        s.domain,
        s.owner,
        s.license,
        s.terms_url,
        s.access,
        s.personal_data,
        s.classification,
        s.lifecycle,
        s.sla_data_age_hours,
        s.sla_success_rate,
        l.last_status,
        l.last_run_at,
        l.last_error_type,
        st.last_success_at,
        st.last_loaded_day,
        coalesce(st.runs_7d, 0) as runs_7d,
        coalesce(st.failed_7d, 0) as failed_7d,
        coalesce(st.unavailable_7d, 0) as unavailable_7d,
        -- every run that did not load counts against the SLA, whoever's fault it was
        round((st.failed_7d + st.unavailable_7d)::numeric / nullif(st.runs_7d, 0), 3) as failure_rate_7d,
        d.latest_observation_ts,
        round((extract(epoch from now() - d.latest_observation_ts) / 3600)::numeric, 1) as data_age_hours,
        coalesce(d.observations, 0) as observations
    from {{ ref('dim_sources') }} as s
    left join last_run as l on s.source = l.source
    left join stats as st on s.source = st.source
    left join data as d on s.source = d.source
),

sla as (
    select
        *,
        -- Unknown (null) when the SLA does not set an age or there is no value yet.
        data_age_hours <= sla_data_age_hours as sla_age_met,
        -- Unknown when the source did not run in the last 7 days.
        case when runs_7d > 0 then 1 - failure_rate_7d >= sla_success_rate end as sla_success_met
    from health
)

select
    *,
    -- Breached if either part is breached, met if a known part is met and none is breached, unknown otherwise.
    case
        when sla_age_met is false or sla_success_met is false then false
        when sla_age_met or sla_success_met then true
    end as sla_met
from sla
