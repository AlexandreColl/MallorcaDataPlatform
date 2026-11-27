-- The satellite sea surface temperature of NOAA OISST, one row per coastal point and day: the final value when it is
-- published (about 16 days later), the preliminary one until then. OISST stamps each analysis at 00:00 UTC of the
-- UTC day it describes, so that day is the date of the row (the same as the local date at midnight UTC).
with observations as (
    select
        entity as point,
        (ts at time zone 'UTC')::date as day,
        metric,
        value,
        lat,
        lon
    from {{ ref('stg_noaa_oisst__observations') }}
    where not is_missing and not is_suspect
)

select
    point,
    day,
    coalesce(
        max(value) filter (where metric = 'sea_surface_temperature'),
        max(value) filter (where metric = 'sea_surface_temperature_preliminary')
    ) as sst_c,
    max(value) filter (where metric = 'sea_surface_temperature_preliminary') as sst_preliminary_c,
    not bool_or(metric = 'sea_surface_temperature') as is_preliminary,
    max(lat) as lat,
    max(lon) as lon
from observations
group by point, day
