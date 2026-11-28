-- Registered unemployment of Mallorca as a whole per month (SEPE): the sum of its municipalities, per 1,000
-- inhabitants of the register, against the same month a year earlier and against the mean of the same calendar month.
-- A municipality whose total is published as "<5" (Escorca, some months) adds nothing: `suppressed_municipalities`
-- counts them, so the island figure is short by at most 4 people for each one. The bands of sex and age and the
-- sectors add up only their published cells, so they can be a little below the total.
with island as (
    select
        month,
        count(*) as municipalities,
        count(*) filter (where is_suppressed) as suppressed_municipalities,
        sum(unemployed) as unemployed,
        sum(unemployed_men_under_25) + sum(unemployed_men_25_44) + sum(unemployed_men_45_plus) as unemployed_men,
        sum(unemployed_women_under_25) + sum(unemployed_women_25_44) + sum(unemployed_women_45_plus)
            as unemployed_women,
        sum(unemployed_men_under_25) + sum(unemployed_women_under_25) as unemployed_under_25,
        sum(unemployed_men_45_plus) + sum(unemployed_women_45_plus) as unemployed_45_plus,
        sum(unemployed_agriculture) as unemployed_agriculture,
        sum(unemployed_industry) as unemployed_industry,
        sum(unemployed_construction) as unemployed_construction,
        sum(unemployed_services) as unemployed_services,
        sum(unemployed_no_previous_job) as unemployed_no_previous_job,
        sum(population) as population
    from {{ ref('fct_unemployment_monthly') }}
    group by month
),

with_context as (
    select
        i.*,
        avg(i.unemployed) over (partition by extract(month from i.month)) as same_month_mean,
        y.unemployed as unemployed_year_before
    from island as i
    left join island as y on i.month - interval '1 year' = y.month
)

select
    month,
    {{ unemployment_season('month') }} as season,
    municipalities::int as municipalities,
    suppressed_municipalities::int as suppressed_municipalities,
    unemployed::int as unemployed,
    unemployed_men::int as unemployed_men,
    unemployed_women::int as unemployed_women,
    unemployed_under_25::int as unemployed_under_25,
    unemployed_45_plus::int as unemployed_45_plus,
    unemployed_agriculture::int as unemployed_agriculture,
    unemployed_industry::int as unemployed_industry,
    unemployed_construction::int as unemployed_construction,
    unemployed_services::int as unemployed_services,
    unemployed_no_previous_job::int as unemployed_no_previous_job,
    round((unemployed_services / nullif(unemployed, 0))::numeric, 3)::numeric(6, 3) as services_share,
    population::int as population,
    round((1000 * unemployed / nullif(population, 0))::numeric, 1)::numeric(8, 1) as unemployed_per_1000_inhabitants,
    round((unemployed / nullif(unemployed_year_before, 0) - 1)::numeric, 4)::numeric(8, 4) as unemployed_yoy,
    round(same_month_mean::numeric, 0)::numeric(10, 0) as same_month_mean,
    round((unemployed / nullif(same_month_mean, 0) - 1)::numeric, 3)::numeric(8, 3) as unemployed_anomaly
from with_context
