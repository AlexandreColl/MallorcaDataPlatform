-- The bathing waters of Mallorca as a whole per season (Náyade): how many were classified in each class of the
-- Bathing Water Directive (see fct_bathing_water_seasons, where the classes are computed), the share of excellent
-- ones among those classified, and the samples that came with advice against bathing and the restrictions.
with island as (
    select
        season,
        count(*) as bathing_waters,
        count(quality_class) as classified,
        count(*) filter (where quality_class = 4) as excellent,
        count(*) filter (where quality_class = 3) as good,
        count(*) filter (where quality_class = 2) as sufficient,
        count(*) filter (where quality_class = 1) as poor,
        count(*) filter (where quality_class_change < 0) as downgraded,
        count(*) filter (where quality_class_change > 0) as upgraded,
        sum(samples) as samples,
        sum(samples_not_fit) as samples_not_fit,
        sum(restrictions) as restrictions,
        sum(bans) as bans,
        sum(restricted_days) as restricted_days,
        max(worst_e_coli) as worst_e_coli,
        max(worst_enterococci) as worst_enterococci
    from {{ ref('fct_bathing_water_seasons') }}
    group by season
)

select
    season,
    bathing_waters::integer as bathing_waters,
    classified::integer as classified,
    excellent::integer as excellent,
    good::integer as good,
    sufficient::integer as sufficient,
    poor::integer as poor,
    round(excellent::numeric / nullif(classified, 0), 3)::numeric(6, 3) as excellent_share,
    downgraded::integer as downgraded,
    upgraded::integer as upgraded,
    samples::integer as samples,
    samples_not_fit::integer as samples_not_fit,
    round(samples_not_fit::numeric / nullif(samples, 0), 4)::numeric(6, 4) as samples_not_fit_share,
    restrictions::integer as restrictions,
    bans::integer as bans,
    restricted_days::integer as restricted_days,
    worst_e_coli::integer as worst_e_coli,
    worst_enterococci::integer as worst_enterococci
from island
