-- EMT Palma network per local day: how many stops have service, scheduled bus calls and the busiest stop.
with per_stop as (
    select
        entity as stop,
        local_date,
        max(value) filter (where metric = 'scheduled_departures') as departures,
        max(value) filter (where metric = 'lines_served') as lines
    from {{ ref('stg_emt_palma__observations') }}
    where not is_missing
    group by entity, local_date
),

ranked as (
    select
        *,
        row_number() over (partition by local_date order by departures desc, stop) as rank_in_day
    from per_stop
)

select
    r.local_date,
    d.iso_day_of_week,
    d.is_weekend,
    count(*) as stops,
    count(*) filter (where r.departures > 0) as stops_with_service,
    sum(r.departures) as scheduled_stop_calls,
    round((avg(r.lines) filter (where r.departures > 0))::numeric, 2) as avg_lines_per_served_stop,
    max(r.stop) filter (where r.rank_in_day = 1) as busiest_stop,
    max(r.departures) as busiest_stop_departures
from ranked as r
left join {{ ref('dim_date') }} as d on r.local_date = d.date_day
group by r.local_date, d.iso_day_of_week, d.is_weekend
