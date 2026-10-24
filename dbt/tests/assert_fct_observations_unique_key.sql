-- Idempotency guard: a series can only have one value per timestamp.
select source, entity, metric, ts, count(*) as n
from {{ ref('fct_observations') }}
group by source, entity, metric, ts
having count(*) > 1
