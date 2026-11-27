-- BiciPalma, one row per station and local day: how many hours it was observed, its mean bikes and occupancy, the
-- hours it ran out of bikes or of docks at some moment, and its busiest swing (the largest hourly range of bikes).
select
    station,
    max(station_name) as station_name,
    round(avg(lat)::numeric, 6)::double precision as lat,
    round(avg(lon)::numeric, 6)::double precision as lon,
    local_date,
    count(*)::integer as hours_observed,
    round(avg(bikes_available), 2)::numeric(6, 2) as bikes_available,
    min(bikes_available_min)::integer as bikes_available_min,
    max(bikes_available_max)::integer as bikes_available_max,
    round(avg(ebikes_available), 2)::numeric(6, 2) as ebikes_available,
    round(avg(docks_available), 2)::numeric(6, 2) as docks_available,
    round(avg(occupancy_pct), 1)::numeric(5, 1) as occupancy_pct,
    -- What the station can hold with its working docks: bikes plus free docks, at the hour they added up most.
    round(max(bikes_available + docks_available))::integer as working_docks,
    (count(*) filter (where was_empty))::integer as hours_empty,
    (count(*) filter (where was_full))::integer as hours_full,
    max(bikes_available_max - bikes_available_min)::integer as largest_hourly_swing
from {{ ref('fct_bike_stations_hourly') }}
group by station, local_date
