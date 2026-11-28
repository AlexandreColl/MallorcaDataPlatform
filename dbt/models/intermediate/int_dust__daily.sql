-- Saharan dust over the island per local day: the mean of the daily mean of every model point, the point with the
-- most and whether the day is a dust day (the island mean at or above `dust_episode_ugm3`). Dust arrives in plumes
-- hundreds of kilometres wide, so the mean of the points is the island's and one point alone does not make a day.
with points as (
    select
        point,
        local_date,
        dust_mean_ugm3,
        dust_max_ugm3
    from {{ ref('fct_pollen_dust_daily') }}
    where dust_mean_ugm3 is not null
),

peaks as (
    select distinct on (local_date)
        local_date,
        point as peak_point
    from points
    order by local_date asc, dust_mean_ugm3 desc, point asc
)

select
    p.local_date,
    round(avg(p.dust_mean_ugm3)::numeric, 1)::double precision as dust_mean_ugm3,
    max(p.dust_mean_ugm3) as peak_point_dust_ugm3,
    max(pk.peak_point) as peak_point,
    max(p.dust_max_ugm3) as dust_max_ugm3,
    count(*) filter (where p.dust_mean_ugm3 >= {{ var('dust_episode_ugm3') }}) as points_over_threshold,
    avg(p.dust_mean_ugm3) >= {{ var('dust_episode_ugm3') }} as is_dust_day
from points as p
inner join peaks as pk on p.local_date = pk.local_date
group by p.local_date
