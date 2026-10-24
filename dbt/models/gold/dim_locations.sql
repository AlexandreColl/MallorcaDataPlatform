select
    source,
    entity,
    -- avg() over thousands of identical doubles adds float noise (39.4983999999987); 6 decimals is ~0.1 m.
    round(avg(lat)::numeric, 6)::double precision as lat,
    round(avg(lon)::numeric, 6)::double precision as lon,
    min(ts) as first_seen,
    max(ts) as last_seen,
    count(distinct metric) as n_metrics
from {{ ref('stg_observations') }}
where source not in {{ event_sources() }}  -- each earthquake is an event, not a location: see fct_earthquakes
group by source, entity
