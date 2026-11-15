-- Buoy vs model, one row per buoy and hour: the significant wave height a SOCIB buoy measured and the one Open-Meteo
-- Marine gave at the nearest point, with the difference (model minus buoy: positive = the model overestimates).
-- Only hours with a valid value on both sides are compared.
with buoy as (
    select
        entity,
        ts,
        local_date,
        value
    from {{ ref('stg_socib__observations') }}
    where metric = 'wave_height' and not is_missing and not is_suspect
),

model as (
    select
        entity,
        ts,
        value
    from {{ ref('stg_open_meteo_marine__observations') }}
    where metric = 'wave_height' and not is_missing and not is_suspect
)

select
    p.buoy,
    p.model_point,
    p.distance_km,
    b.ts,
    b.local_date,
    b.value as wave_height_buoy_m,
    m.value as wave_height_model_m,
    m.value - b.value as wave_height_bias_m
from {{ ref('int_buoy_wave_model_pairs') }} as p
inner join buoy as b on p.buoy = b.entity
inner join model as m on p.model_point = m.entity and b.ts = m.ts
