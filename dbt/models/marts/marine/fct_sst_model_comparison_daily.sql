-- Satellite vs model per coastal point and day: the OISST sea surface temperature and the daily mean of the hourly
-- one Open-Meteo Marine gives at the same point (the points share their names), with the difference (model minus
-- satellite: positive = the model is warmer). Both are UTC days, since OISST analyses a UTC day; a model day needs
-- 20 of its 24 hours. SOCIB's buoys do not load their water temperature yet, so they are not compared.
with model as (
    select
        entity as point,
        (ts at time zone 'UTC')::date as day,
        avg(value) as sst_model_c,
        count(*) as model_hours
    from {{ ref('stg_open_meteo_marine__observations') }}
    where metric = 'sea_surface_temperature' and not is_missing and not is_suspect
    group by entity, (ts at time zone 'UTC')::date
    having count(*) >= 20
)

select
    s.point,
    s.day,
    s.sst_c as sst_satellite_c,
    s.is_preliminary,
    round(m.sst_model_c::numeric, 2)::numeric(5, 2) as sst_model_c,
    round((m.sst_model_c - s.sst_c)::numeric, 2)::numeric(5, 2) as sst_bias_c,
    m.model_hours
from {{ ref('fct_sea_temperature_daily') }} as s
inner join model as m on s.point = m.point and s.day = m.day
where s.sst_c is not null
