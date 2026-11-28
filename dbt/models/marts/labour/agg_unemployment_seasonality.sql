-- How seasonal unemployment is, per year, in Mallorca as a whole (`area` = 'mallorca') and in each municipality (its
-- INE code): the mean of the winter months (November to February) against the mean of the summer months (June to
-- September) of the same calendar year. `winter_summer_ratio` 1.6 means 60 % more people registered as unemployed in
-- winter than in summer. A year counts only with its four summer months and at least three winter ones (the year in
-- progress has not got them yet), and a municipality only without suppressed totals in it.
with monthly as (
    select
        'mallorca' as area,
        'Mallorca' as area_name,
        month,
        season,
        unemployed,
        false as is_suppressed
    from {{ ref('fct_unemployment_island_monthly') }}
    union all
    select
        municipality as area,
        municipality_name as area_name,
        month,
        season,
        unemployed,
        is_suppressed
    from {{ ref('fct_unemployment_monthly') }}
),

yearly as (
    select
        area,
        area_name,
        extract(year from month)::int as year,
        count(*) filter (where season = 'summer' and unemployed is not null) as summer_months,
        count(*) filter (where season = 'winter' and unemployed is not null) as winter_months,
        bool_or(is_suppressed) as any_suppressed,
        avg(unemployed) filter (where season = 'summer') as summer_mean,
        avg(unemployed) filter (where season = 'winter') as winter_mean,
        min(unemployed) as lowest,
        max(unemployed) as highest
    from monthly
    group by area, area_name, extract(year from month)
)

select
    area,
    area_name,
    year,
    summer_months::int as summer_months,
    winter_months::int as winter_months,
    round(summer_mean::numeric, 0)::numeric(10, 0) as summer_mean,
    round(winter_mean::numeric, 0)::numeric(10, 0) as winter_mean,
    lowest::int as lowest_month,
    highest::int as highest_month,
    case
        when summer_months = 4 and winter_months >= 3 and not any_suppressed
            then round((winter_mean / nullif(summer_mean, 0))::numeric, 3)::numeric(8, 3)
    end as winter_summer_ratio
from yearly
