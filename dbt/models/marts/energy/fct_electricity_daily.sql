-- Balearic electric system per local day: demand, generation by technology, renewable share and CO2.
with daily as (
    select
        local_date,
        sum(value) filter (where metric = 'electricity_demand') as demand_mwh,
        count(*) filter (where metric = 'electricity_demand') as demand_hours,
        max(value) filter (where metric = 'electricity_demand') as peak_hour_demand_mwh,
        max(value) filter (where metric = 'generation_total') as generation_total_mwh,
        max(value) filter (where metric = 'generation_combined_cycle') as combined_cycle_mwh,
        max(value) filter (where metric = 'generation_gas_turbine') as gas_turbine_mwh,
        max(value) filter (where metric = 'generation_diesel_engines') as diesel_engines_mwh,
        max(value) filter (where metric = 'generation_cogeneration') as cogeneration_mwh,
        max(value) filter (where metric = 'generation_non_renewable_waste') as non_renewable_waste_mwh,
        max(value) filter (where metric = 'generation_renewable_waste') as renewable_waste_mwh,
        max(value) filter (where metric = 'generation_solar_pv') as solar_pv_mwh,
        max(value) filter (where metric = 'generation_other_renewables') as other_renewables_mwh,
        max(value) filter (where metric = 'co2_emissions') as co2_emissions_t,
        max(value) filter (where metric = 'co2_intensity') as co2_intensity_t_per_mwh
    from {{ ref('stg_redata__observations') }}
    where not is_missing
    group by local_date
)

select
    *,
    round((
        (coalesce(solar_pv_mwh, 0) + coalesce(renewable_waste_mwh, 0) + coalesce(other_renewables_mwh, 0))
        / nullif(generation_total_mwh, 0)
    )::numeric, 4)::numeric(5, 4) as renewable_share,
    -- generation below demand means the islands imported the rest through the Mallorca-mainland link
    round((demand_mwh - generation_total_mwh)::numeric, 1)::numeric(10, 1) as net_import_mwh
from daily
