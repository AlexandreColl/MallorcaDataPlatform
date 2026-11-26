-- Tourist dwellings of each municipality of Mallorca per reference month (INE experimental statistic: the listings
-- of the main holiday rental platforms), with their beds, the change against the previous reference month and their
-- weight against the population. The INE counts twice a year and the months have moved (August 2020, then February
-- and August, since November 2024 May and November), so the change is against the previous count, not a fixed lag.
-- The population is the register of 1 January of the same year, or the latest one before it while that register is
-- not published yet.
with counts as (
    select
        entity as municipality,
        local_date as reference_month,
        max(value) filter (where metric = 'tourist_dwellings') as tourist_dwellings,
        max(value) filter (where metric = 'tourist_beds') as tourist_beds,
        max(value) filter (where metric = 'beds_per_dwelling') as beds_per_dwelling
    from {{ ref('stg_ine_tourist_housing__observations') }}
    where not is_missing
    group by entity, local_date
),

with_previous as (
    select
        *,
        lag(reference_month) over (partition by municipality order by reference_month) as previous_month,
        lag(tourist_dwellings) over (partition by municipality order by reference_month) as previous_dwellings
    from counts
)

select
    c.municipality,
    m.name as municipality_name,
    c.reference_month,
    c.tourist_dwellings::int as tourist_dwellings,
    c.tourist_beds::int as tourist_beds,
    round(c.beds_per_dwelling::numeric, 2)::numeric(6, 2) as beds_per_dwelling,
    p.year as population_year,
    p.population,
    round((1000 * c.tourist_dwellings / nullif(p.population, 0))::numeric, 1)::numeric(8, 1)
        as dwellings_per_1000_inhabitants,
    round((100 * c.tourist_beds / nullif(p.population, 0))::numeric, 1)::numeric(8, 1) as beds_per_100_inhabitants,
    c.previous_month,
    (c.tourist_dwellings - c.previous_dwellings)::int as dwellings_change,
    round((c.tourist_dwellings / nullif(c.previous_dwellings, 0) - 1)::numeric, 4)::numeric(8, 4)
        as dwellings_change_pct
from with_previous as c
left join {{ ref('dim_municipalities') }} as m on c.municipality = m.municipality
left join lateral (
    select
        y.year,
        y.population
    from {{ ref('fct_population_yearly') }} as y
    where y.municipality = c.municipality and y.year <= extract(year from c.reference_month)
    order by y.year desc
    limit 1
) as p on true
