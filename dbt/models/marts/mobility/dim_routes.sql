-- One row per line of the EMT Palma and CTM networks with its path. Its daily trips are the `scheduled_trips`
-- series of the same entity (agg_daily_metrics, fct_observations).
select
    source,
    route,
    short_name,
    name,
    kind,
    color,
    geometry
from {{ ref('stg_silver__routes') }}
