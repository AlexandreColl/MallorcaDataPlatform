-- CTM island network (TIB buses, SFM trains, metro) per local day: stops with service, scheduled calls and the
-- busiest stop. Seasonal lines show up as a drop in stops with service when their timetable ends (31 October).
{{ transit_network_daily('stg_ctm__observations') }}
