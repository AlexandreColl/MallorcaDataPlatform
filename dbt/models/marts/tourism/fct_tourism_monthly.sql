-- Balearic tourism per month (Dataestur): international arrivals and spending, hotel occupancy and Palma airport
-- passengers, with the change against the same month a year earlier. Hotel occupancy is published a month after
-- the others, so the latest month can have arrivals but no hotel figures yet.
with monthly as (
    select
        local_date as month,
        max(value) filter (where metric = 'international_tourists') as international_tourists,
        max(value) filter (where metric = 'international_tourist_spending') as international_spending_eur,
        max(value) filter (where metric = 'international_tourist_nights') as international_tourist_nights,
        max(value) filter (where metric = 'hotel_guests') as hotel_guests,
        max(value) filter (where metric = 'hotel_nights') as hotel_nights,
        max(value) filter (where metric = 'hotel_bed_occupancy') as hotel_bed_occupancy_pct,
        max(value) filter (where metric = 'hotels_open') as hotels_open,
        max(value) filter (where metric = 'hotel_staff') as hotel_staff,
        max(value) filter (where metric = 'airport_passengers') as airport_passengers
    from {{ ref('stg_dataestur__observations') }}
    where not is_missing
    group by local_date
)

select
    m.month,
    m.international_tourists,
    m.international_spending_eur,
    m.international_tourist_nights,
    round((m.international_spending_eur / nullif(m.international_tourists, 0))::numeric, 2)::numeric(10, 2)
        as spending_per_tourist_eur,
    m.hotel_guests,
    m.hotel_nights,
    round((m.hotel_nights / nullif(m.hotel_guests, 0))::numeric, 2)::numeric(6, 2) as hotel_average_stay_nights,
    m.hotel_bed_occupancy_pct,
    m.hotels_open,
    m.hotel_staff,
    m.airport_passengers,
    round((m.international_tourists / nullif(y.international_tourists, 0) - 1)::numeric, 4)::numeric(8, 4)
        as international_tourists_yoy,
    round((m.airport_passengers / nullif(y.airport_passengers, 0) - 1)::numeric, 4)::numeric(8, 4)
        as airport_passengers_yoy
from monthly as m
left join monthly as y on m.month - interval '1 year' = y.month
