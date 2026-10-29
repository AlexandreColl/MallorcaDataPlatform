-- Monthly air quality of each official station over two decades: the GOIB history (2002 to June 2021) and the EEA
-- live feed use the same station names, so a station reads as one series. Only measured, valid hours count, and a
-- month is representative with at least 75 % of them (an outage never reads as a clean month).
with hourly as (
    select
        source,
        entity as station,
        metric,
        date_trunc('month', local_date)::date as month,
        value
    from {{ ref('fct_observations') }}
    where
        source in ('goib_air_quality', 'eea_air_quality')
        and not is_missing
        and not is_suspect
)

select
    source,
    station,
    metric,
    month,
    round(avg(value)::numeric, 2)::double precision as mean_ugm3,
    round(max(value)::numeric, 2)::double precision as max_ugm3,
    count(*) as valid_hours,
    -- least(): the local October has 745 hours (the clock goes back), one more than 31 x 24.
    round(
        least(1, count(*) / (24.0 * extract(day from (month + interval '1 month' - interval '1 day'))))::numeric, 3
    )::double precision as coverage,
    count(*) >= 0.75 * 24 * extract(day from (month + interval '1 month' - interval '1 day')) as is_representative
from hourly
group by source, station, metric, month
