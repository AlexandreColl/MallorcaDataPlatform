-- Population of each municipality of Mallorca on 1 January (INE municipal register), with its density and the change
-- against the previous register. There was no register in 1997, so the change of 1998 is against 1996.
with yearly as (
    select
        entity as municipality,
        extract(year from local_date)::int as year,
        max(value) filter (where metric = 'population') as population,
        max(value) filter (where metric = 'population_men') as population_men,
        max(value) filter (where metric = 'population_women') as population_women
    from {{ ref('stg_ine_population__observations') }}
    where not is_missing
    group by entity, extract(year from local_date)
),

with_previous as (
    select
        *,
        lag(population) over (partition by municipality order by year) as previous_population,
        lag(year) over (partition by municipality order by year) as previous_year
    from yearly
)

select
    p.municipality,
    m.name as municipality_name,
    p.year,
    p.population::int as population,
    p.population_men::int as population_men,
    p.population_women::int as population_women,
    m.area_km2,
    round((p.population / nullif(m.area_km2, 0))::numeric, 1)::numeric(10, 1) as density_per_km2,
    p.previous_year,
    (p.population - p.previous_population)::int as population_change,
    round((p.population / nullif(p.previous_population, 0) - 1)::numeric, 4)::numeric(8, 4) as population_change_pct
from with_previous as p
left join {{ ref('dim_municipalities') }} as m on p.municipality = m.municipality
