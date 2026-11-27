-- The usual sea surface temperature of every coastal point and day of the year, as Hobday et al. (2016) define it
-- for marine heatwaves: the final OISST values of the baseline years (`sst_baseline`, 1991-2020) within
-- `sst_window_half_days` of that day in every year (an 11-day window), their mean and 90th percentile, then a
-- moving mean of 2 x `sst_smoothing_half_days` + 1 days (31) that smooths the noise of 30 years. Days are numbered
-- on a 366-day calendar (29 February is day 60 in every year) and the windows wrap around the new year.
{%- set half = var('sst_window_half_days') %}
{%- set smoothing = var('sst_smoothing_half_days') %}
with baseline as (
    select
        point,
        {{ day_of_year_366('day') }} as day_of_year,
        sst_c
    from {{ ref('int_sea_temperature__daily') }}
    where
        not is_preliminary
        and day between '{{ var("sst_baseline")["start"] }}' and '{{ var("sst_baseline")["end"] }}'
),

calendar as (
    select generate_series(1, 366) as day_of_year
),

windowed as (
    select
        b.point,
        c.day_of_year,
        avg(b.sst_c) as sst_mean_c,
        percentile_cont({{ var('sst_heatwave_percentile') }}) within group (order by b.sst_c) as sst_p90_c,
        count(*) as baseline_values
    from calendar as c
    inner join baseline as b
        on least(abs(b.day_of_year - c.day_of_year), 366 - abs(b.day_of_year - c.day_of_year)) <= {{ half }}
    group by b.point, c.day_of_year
),

-- The year three times in a row, so the moving mean of the first and last days reads across the new year.
wrapped as (
    select
        w.point,
        w.day_of_year + s.shift as day_of_year,
        w.sst_mean_c,
        w.sst_p90_c,
        w.baseline_values
    from windowed as w
    cross join (values (-366), (0), (366)) as s (shift)
),

smoothed as (
    select
        point,
        day_of_year,
        baseline_values,
        avg(sst_mean_c) over smoothing_window as sst_climatology_c,
        avg(sst_p90_c) over smoothing_window as sst_p90_c
    from wrapped
    window smoothing_window as (
        partition by point order by day_of_year rows between {{ smoothing }} preceding and {{ smoothing }} following
    )
)

select
    point,
    day_of_year,
    round(sst_climatology_c::numeric, 3)::numeric(6, 3) as sst_climatology_c,
    round(sst_p90_c::numeric, 3)::numeric(6, 3) as sst_p90_c,
    baseline_values
from smoothed
where day_of_year between 1 and 366
