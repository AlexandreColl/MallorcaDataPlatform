-- Every source in silver needs a row in the dim_sources seed (label and kind used by Grafana).
select distinct source
from {{ ref('stg_silver__observations') }}
where source not in (select source from {{ ref('dim_sources') }})
