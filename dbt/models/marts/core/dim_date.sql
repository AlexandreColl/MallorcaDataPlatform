-- Calendar dimension: one row per day from `date_spine_start` to a year ahead.
with days as (
    select generate_series(
        '{{ var("date_spine_start") }}'::date,
        (current_date + interval '1 year')::date,
        interval '1 day'
    )::date as date_day
)

select
    date_day,
    extract(year from date_day)::int as year,
    extract(quarter from date_day)::int as quarter,
    extract(month from date_day)::int as month,
    extract(day from date_day)::int as day_of_month,
    extract(isodow from date_day)::int as iso_day_of_week,
    extract(isodow from date_day) in (6, 7) as is_weekend,
    to_char(date_day, 'IYYY-"W"IW') as iso_week,
    -- meteorological seasons (whole months), the ones used for climate statistics
    case
        when extract(month from date_day) in (12, 1, 2) then 'winter'
        when extract(month from date_day) in (3, 4, 5) then 'spring'
        when extract(month from date_day) in (6, 7, 8) then 'summer'
        else 'autumn'
    end as season
from days
