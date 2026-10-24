select *
from {{ ref('agg_daily_metrics') }}
where completeness < 0 or completeness > 1
