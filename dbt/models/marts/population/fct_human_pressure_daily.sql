-- People actually present in Mallorca each day (Ibestat Human Pressure Indicator) against the people registered
-- there (INE municipal register on 1 January of that year, or the latest register before it). The difference is the
-- visitors present that day net of the residents who are away; the ratio is the island's load over its residents.
with pressure as (
    select
        local_date,
        value as people_present
    from {{ ref('stg_ibestat_iph__observations') }}
    where entity = 'mallorca' and not is_missing
),

residents as (
    select
        extract(year from local_date)::int as year,
        sum(value) as residents
    from {{ ref('stg_ine_population__observations') }}
    where metric = 'population' and not is_missing
    group by extract(year from local_date)
)

select
    p.local_date,
    d.iso_day_of_week,
    d.is_weekend,
    p.people_present::int as people_present,
    r.year as register_year,
    r.residents::int as residents,
    (p.people_present - r.residents)::int as people_over_residents,
    round((p.people_present / nullif(r.residents, 0))::numeric, 3)::numeric(6, 3) as pressure_ratio
from pressure as p
left join {{ ref('dim_date') }} as d on p.local_date = d.date_day
left join lateral (
    -- the register of that year or, when it is not out yet, the latest before it
    select year, residents
    from residents
    where year <= extract(year from p.local_date)
    order by year desc
    limit 1
) as r on true
