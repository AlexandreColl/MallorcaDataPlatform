-- Metric dimension: one row per source and metric. Grouping by unit too means a metric with two units yields two
-- rows, which the primary key of the contract rejects.
select
    source,
    metric,
    unit,
    count(distinct entity) as n_entities,
    min(local_date) as first_date,
    max(local_date) as last_date
from {{ ref('agg_daily_metrics') }}
group by source, metric, unit
