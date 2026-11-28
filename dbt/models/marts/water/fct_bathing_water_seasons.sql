-- One row per bathing water of Mallorca and season (Náyade): its samples, worst results and restrictions, and the
-- classification of the Bathing Water Directive (2006/7/EC, annex II, coastal waters) computed on the samples of
-- that season and the three before it, the same four-season set the official classification uses.
--
-- The directive works on the logarithms of the results: the 95th percentile is 10^(mean + 1.65 sd) and the 90th
-- 10^(mean + 1.282 sd), for E. coli and intestinal enterococci alike. A water is
--   4 excellent:  95th percentile of E. coli <= 250 and of enterococci <= 100 (cfu/100 ml)
--   3 good:       95th percentile <= 500 and <= 200
--   2 sufficient: 90th percentile <= 500 and <= 185
--   1 poor:       otherwise
-- and is not classified with fewer than 16 samples in the set (the directive's minimum) or with a single season: a
-- water with several sampling points reaches 16 samples in one season, which is not an assessment of four. Náyade
-- keeps only the last four seasons, so the first ones loaded are assessed on fewer (`assessed_seasons`), and the
-- samples of every sampling point of a water count, while the official assessment may leave out samples of
-- short-term pollution: this is a reproduction of the method, not the official classification.
with samples as (
    select
        split_part(entity, '_', 1) as municipality,
        split_part(entity, '_', 2) as bathing_water,
        entity as sampling_point,
        local_date as sample_date,
        extract(year from local_date)::integer as season,
        max(value) filter (where metric = 'e_coli') as e_coli,
        max(value) filter (where metric = 'enterococci') as enterococci,
        max(value) filter (where metric = 'bathing_advice') as bathing_advice,
        max(value) filter (where metric = 'incident_level') as incident_level,
        max(value) filter (where metric = 'incident_days') as incident_days,
        avg(lat) as lat,
        avg(lon) as lon
    from {{ ref('stg_nayade__observations') }}
    where not is_missing
    group by entity, local_date
),

points as (
    select
        s.municipality,
        s.bathing_water,
        s.sampling_point,
        avg(s.lat) as lat,
        avg(s.lon) as lon,
        -- the name of a point is that of its water plus " (PM3)" when the water has several
        min(regexp_replace(e.name, ' \(PM[0-9]+\)$', '')) as name
    from samples as s
    left join {{ ref('stg_silver__entities') }} as e on e.source = 'nayade' and s.sampling_point = e.entity
    group by s.municipality, s.bathing_water, s.sampling_point
),

waters as (
    select
        municipality,
        bathing_water,
        min(name) as name,
        count(*) as sampling_points,
        round(avg(lat)::numeric, 6)::double precision as lat,
        round(avg(lon)::numeric, 6)::double precision as lon
    from points
    group by municipality, bathing_water
),

seasons as (
    select
        bathing_water,
        season,
        count(*) filter (where e_coli is not null or enterococci is not null) as samples,
        max(e_coli) as worst_e_coli,
        max(enterococci) as worst_enterococci,
        count(*) filter (where bathing_advice >= 1) as samples_not_fit,
        count(*) filter (where incident_level is not null) as restrictions,
        count(*) filter (where incident_level = 2) as bans,
        coalesce(sum(incident_days), 0) as restricted_days,
        max(sample_date) filter (where e_coli is not null or enterococci is not null) as last_sample_date
    from samples
    group by bathing_water, season
),

assessment as (
    select
        s.bathing_water,
        s.season,
        count(x.e_coli) as assessed_samples,
        count(distinct x.season) as assessed_seasons,
        avg(log(greatest(x.e_coli, 1))) as log_mean_e_coli,
        stddev_samp(log(greatest(x.e_coli, 1))) as log_sd_e_coli,
        avg(log(greatest(x.enterococci, 1))) as log_mean_enterococci,
        stddev_samp(log(greatest(x.enterococci, 1))) as log_sd_enterococci
    from seasons as s
    inner join samples as x
        on
            s.bathing_water = x.bathing_water
            and x.season between s.season - 3 and s.season
            and x.e_coli is not null
            and x.enterococci is not null
    group by s.bathing_water, s.season
),

percentiles as (
    select
        bathing_water,
        season,
        assessed_samples,
        assessed_seasons,
        power(10, log_mean_e_coli + 1.65 * log_sd_e_coli) as p95_e_coli,
        power(10, log_mean_enterococci + 1.65 * log_sd_enterococci) as p95_enterococci,
        power(10, log_mean_e_coli + 1.282 * log_sd_e_coli) as p90_e_coli,
        power(10, log_mean_enterococci + 1.282 * log_sd_enterococci) as p90_enterococci
    from assessment
),

classified as (
    select
        *,
        case
            when assessed_samples < 16 or assessed_seasons < 2 then null
            when p95_e_coli <= 250 and p95_enterococci <= 100 then 4
            when p95_e_coli <= 500 and p95_enterococci <= 200 then 3
            when p90_e_coli <= 500 and p90_enterococci <= 185 then 2
            else 1
        end as quality_class
    from percentiles
),

joined as (
    select
        w.municipality,
        w.bathing_water,
        w.name,
        w.sampling_points,
        w.lat,
        w.lon,
        s.season,
        s.samples,
        s.worst_e_coli,
        s.worst_enterococci,
        s.samples_not_fit,
        s.restrictions,
        s.bans,
        s.restricted_days,
        s.last_sample_date,
        c.assessed_samples,
        c.assessed_seasons,
        c.p95_e_coli,
        c.p95_enterococci,
        c.p90_e_coli,
        c.p90_enterococci,
        c.quality_class,
        lag(c.quality_class) over (partition by s.bathing_water order by s.season) as previous_quality_class
    from seasons as s
    inner join waters as w on s.bathing_water = w.bathing_water
    left join classified as c on s.bathing_water = c.bathing_water and s.season = c.season
)

select
    j.bathing_water,
    j.name,
    j.municipality,
    d.name as municipality_name,
    j.sampling_points::integer as sampling_points,
    j.lat,
    j.lon,
    j.season,
    j.samples::integer as samples,
    j.last_sample_date,
    j.worst_e_coli::integer as worst_e_coli,
    j.worst_enterococci::integer as worst_enterococci,
    j.samples_not_fit::integer as samples_not_fit,
    j.restrictions::integer as restrictions,
    j.bans::integer as bans,
    j.restricted_days::integer as restricted_days,
    coalesce(j.assessed_samples, 0)::integer as assessed_samples,
    coalesce(j.assessed_seasons, 0)::integer as assessed_seasons,
    round(j.p95_e_coli::numeric, 1)::numeric(10, 1) as p95_e_coli,
    round(j.p95_enterococci::numeric, 1)::numeric(10, 1) as p95_enterococci,
    round(j.p90_e_coli::numeric, 1)::numeric(10, 1) as p90_e_coli,
    round(j.p90_enterococci::numeric, 1)::numeric(10, 1) as p90_enterococci,
    j.quality_class::integer as quality_class,
    case j.quality_class
        when 4 then 'excellent'
        when 3 then 'good'
        when 2 then 'sufficient'
        when 1 then 'poor'
    end as quality,
    j.previous_quality_class::integer as previous_quality_class,
    (j.quality_class - j.previous_quality_class)::integer as quality_class_change
from joined as j
left join {{ ref('dim_municipalities') }} as d on j.municipality = d.municipality
