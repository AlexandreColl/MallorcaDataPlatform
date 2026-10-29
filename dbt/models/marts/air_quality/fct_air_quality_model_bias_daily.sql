-- Daily air quality of each official station (EEA) next to the CAMS model of Open-Meteo at the nearest model point:
-- how far the model is from the measurements, per pollutant. A day counts only with at least 18 valid hours at the
-- station, so an outage of the feed never reads as a clean day.
with pairs as (
    select
        station,
        model_point,
        distance_km
    from {{ ref('int_station_model_pairs') }}
    where station_source = 'eea_air_quality'
),

hourly as (
    select
        source,
        entity,
        metric,
        local_date,
        value
    from {{ ref('fct_observations') }}
    where
        source in ('eea_air_quality', 'open_meteo')
        and metric in ('pm10', 'pm2_5', 'nitrogen_dioxide', 'ozone')
        and not is_missing
        and not is_suspect
),

daily as (
    select
        source,
        entity,
        metric,
        local_date,
        avg(value) as mean_ugm3,
        max(value) as max_ugm3,
        count(*) as hours
    from hourly
    group by source, entity, metric, local_date
)

select
    p.station,
    p.model_point,
    p.distance_km,
    obs.metric,
    obs.local_date,
    round(obs.mean_ugm3::numeric, 2)::double precision as station_mean_ugm3,
    round(model.mean_ugm3::numeric, 2)::double precision as model_mean_ugm3,
    round((model.mean_ugm3 - obs.mean_ugm3)::numeric, 2)::double precision as bias_ugm3,
    round(obs.max_ugm3::numeric, 2)::double precision as station_max_ugm3,
    obs.hours as station_hours
from pairs as p
inner join daily as obs
    on obs.source = 'eea_air_quality' and p.station = obs.entity
inner join daily as model
    on
        model.source = 'open_meteo'
        and p.model_point = model.entity
        and obs.metric = model.metric
        and obs.local_date = model.local_date
where obs.hours >= 18
