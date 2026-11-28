-- Registered unemployment of each municipality of Mallorca per month (SEPE): the people registered as unemployed on
-- the last working day of the month, by sex and age and by sector, per 1,000 inhabitants of the register, against the
-- same month a year earlier and against the mean of the same calendar month (the summer jobs make it seasonal).
-- Since 2022 SEPE publishes every count from 1 to 4 as "<5": those cells are null here, and `is_suppressed` marks a
-- total that is one of them. The population is the register of 1 January of the same year, or the latest one before
-- it while that register is not published yet.
with monthly as (
    select
        entity as municipality,
        local_date as month,
        bool_or(metric = 'unemployed' and value is null) as is_suppressed,
        max(value) filter (where metric = 'unemployed') as unemployed,
        max(value) filter (where metric = 'unemployed_men_under_25') as men_under_25,
        max(value) filter (where metric = 'unemployed_men_25_44') as men_25_44,
        max(value) filter (where metric = 'unemployed_men_45_plus') as men_45_plus,
        max(value) filter (where metric = 'unemployed_women_under_25') as women_under_25,
        max(value) filter (where metric = 'unemployed_women_25_44') as women_25_44,
        max(value) filter (where metric = 'unemployed_women_45_plus') as women_45_plus,
        max(value) filter (where metric = 'unemployed_agriculture') as agriculture,
        max(value) filter (where metric = 'unemployed_industry') as industry,
        max(value) filter (where metric = 'unemployed_construction') as construction,
        max(value) filter (where metric = 'unemployed_services') as services,
        max(value) filter (where metric = 'unemployed_no_previous_job') as no_previous_job
    from {{ ref('stg_sepe_unemployment__observations') }}
    group by entity, local_date
),

with_context as (
    select
        m.*,
        avg(m.unemployed) over (partition by m.municipality, extract(month from m.month)) as same_month_mean,
        y.unemployed as unemployed_year_before
    from monthly as m
    left join monthly as y on m.municipality = y.municipality and m.month - interval '1 year' = y.month
)

select
    c.municipality,
    d.name as municipality_name,
    c.month,
    {{ unemployment_season('c.month') }} as season,
    c.is_suppressed,
    c.unemployed::int as unemployed,
    (c.men_under_25 + c.men_25_44 + c.men_45_plus)::int as unemployed_men,
    (c.women_under_25 + c.women_25_44 + c.women_45_plus)::int as unemployed_women,
    (c.men_under_25 + c.women_under_25)::int as unemployed_under_25,
    (c.men_45_plus + c.women_45_plus)::int as unemployed_45_plus,
    c.men_under_25::int as unemployed_men_under_25,
    c.men_25_44::int as unemployed_men_25_44,
    c.men_45_plus::int as unemployed_men_45_plus,
    c.women_under_25::int as unemployed_women_under_25,
    c.women_25_44::int as unemployed_women_25_44,
    c.women_45_plus::int as unemployed_women_45_plus,
    c.agriculture::int as unemployed_agriculture,
    c.industry::int as unemployed_industry,
    c.construction::int as unemployed_construction,
    c.services::int as unemployed_services,
    c.no_previous_job::int as unemployed_no_previous_job,
    p.year as population_year,
    p.population,
    round((1000 * c.unemployed / nullif(p.population, 0))::numeric, 1)::numeric(8, 1)
        as unemployed_per_1000_inhabitants,
    round((c.unemployed / nullif(c.unemployed_year_before, 0) - 1)::numeric, 4)::numeric(8, 4) as unemployed_yoy,
    round(c.same_month_mean::numeric, 1)::numeric(10, 1) as same_month_mean,
    round((c.unemployed / nullif(c.same_month_mean, 0) - 1)::numeric, 3)::numeric(8, 3) as unemployed_anomaly
from with_context as c
left join {{ ref('dim_municipalities') }} as d on c.municipality = d.municipality
left join lateral (
    select
        y.year,
        y.population
    from {{ ref('fct_population_yearly') }} as y
    where y.municipality = c.municipality and y.year <= extract(year from c.month)
    order by y.year desc
    limit 1
) as p on true
