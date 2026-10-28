-- Mallorca's groundwater reserves per month: the island-wide share, its change, and its anomaly against the mean of
-- the same calendar month (reserves are seasonal: they peak in late winter and bottom out in early autumn, so a
-- month is only comparable with the same month of other years). Aquifer figures exist from the spreadsheet months on.
with island as (
    select
        local_date as month,
        value as reserves_pct
    from {{ ref('stg_water_reserves__observations') }}
    where entity = 'mallorca' and not is_missing
),

aquifers as (
    select
        o.local_date as month,
        count(*) as aquifers,
        count(*) filter (where o.value < 30) as aquifers_below_30_pct,
        min(o.value) as lowest_aquifer_pct,
        (array_agg(a.aquifer order by o.value, a.aquifer))[1] as lowest_aquifer
    from {{ ref('stg_water_reserves__observations') }} as o
    inner join {{ ref('dim_aquifers') }} as a on o.entity = a.entity
    where not o.is_missing
    group by o.local_date
),

with_climatology as (
    select
        *,
        avg(reserves_pct) over (partition by extract(month from month)) as same_month_mean_pct,
        count(*) over (partition by extract(month from month)) as same_month_years
    from island
)

select
    c.month,
    -- hydrological year: September to August, named after the year it ends in
    (extract(year from c.month) + case when extract(month from c.month) >= 9 then 1 else 0 end)::integer
        as hydrological_year,
    c.reserves_pct,
    c.reserves_pct - p.reserves_pct as change_1m_pts,
    c.reserves_pct - y.reserves_pct as change_12m_pts,
    round(c.same_month_mean_pct::numeric, 1)::numeric(5, 1) as same_month_mean_pct,
    round((c.reserves_pct - c.same_month_mean_pct)::numeric, 1)::numeric(5, 1) as anomaly_pts,
    c.same_month_years,
    a.aquifers,
    a.aquifers_below_30_pct,
    a.lowest_aquifer,
    a.lowest_aquifer_pct
from with_climatology as c
left join island as p on c.month - interval '1 month' = p.month
left join island as y on c.month - interval '1 year' = y.month
left join aquifers as a on c.month = a.month
