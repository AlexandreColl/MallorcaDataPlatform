// Generated from the OpenAPI schema of the API by `make web-types` (api/typescript.py). Do not edit by hand.

/** The latest hour of one air quality station or model point (gold.air_quality_hourly). */
export interface AirQualityNow {
  source: string;
  entity: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  lat: number | null;
  lon: number | null;
  ts: string;
  pm2_5: number | null;
  pm10: number | null;
  no2: number | null;
  o3: number | null;
  /** European AQI band, 1 (good) to 6 (extremely poor), from the worst pollutant. */
  eaqi_band: number;
  eaqi_label: string | null;
}

/** How many values one detector flagged in one local day (silver.anomalies). */
export interface AnomaliesDay {
  local_date: string;
  detector: "robust_zscore" | "seasonal_residual" | "isolation_forest" | "vote";
  anomalies: number;
}

/** A value flagged by an anomaly detector (silver.anomalies). Flags never change the observation. */
export interface Anomaly {
  source: string;
  entity: string;
  metric: string;
  ts: string;
  detector: "robust_zscore" | "seasonal_residual" | "isolation_forest" | "vote";
  value: number | null;
  expected: number | null;
  score: number | null;
  threshold: number | null;
}

/** One groundwater body of Mallorca in the latest published month. */
export interface Aquifer {
  entity: string;
  code: string;
  aquifer: string;
  hydrogeological_unit: string;
  month: string;
  reserves_pct: number | null;
  change_12m_pts: number | null;
}

/** Climate of Mallorca in one month from the AEMET stations (gold.fct_climate_monthly). */
export interface ClimateMonth {
  month: string;
  hydrological_year: number;
  rain_stations: number;
  rain_mm: number | null;
  rain_same_month_mean_mm: number | null;
  /** Against the mean of the same month (0.2 = 20 % more). */
  rain_anomaly: number | null;
  rain_hydrological_year_mm: number | null;
  rain_hydrological_year_mean_mm: number | null;
  wet_days: number | null;
  temperature_stations: number;
  temperature_mean_c: number | null;
  temperature_anomaly_c: number | null;
  temperature_max_c: number | null;
  hot_days: number | null;
  same_month_years: number;
}

/**
 * A proposed value for a station hour without a valid one (gold.fct_observations_corrected).
 *
 * Corrections never change the observation: the original value and quality come with the corrected one.
 */
export interface Correction {
  source: string;
  entity: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  metric: string;
  ts: string;
  unit: string | null;
  /** `missing`, `suspect` or `absent` (no row) */
  original_quality: string;
  /** The suspect value; empty when it was missing or absent. */
  original_value: number | null;
  corrected_value: number;
  /** `interpolation` (gaps up to 3 h), `support` or `profile` (weekly cycle) */
  method: "interpolation" | "support" | "profile";
  /** Method `support`: the series used. */
  support_source: string | null;
  support_entity: string | null;
  /** Station minus support at that hour of the day, added to the support. */
  bias: number | null;
  /** From the correlation, the distance and the gap length. */
  confidence: number;
}

/**
 * How one detector did against one kind of injected fault, in the latest benchmark of a source.
 *
 * From ``make evaluate`` (gold.fct_anomaly_evaluations). ``fault = "all"`` holds the totals, the precision and the
 * false alarms; the rows of each fault kind only say how many of its faults were caught.
 */
export interface DetectorBenchmark {
  source: string;
  detector: "robust_zscore" | "seasonal_residual" | "isolation_forest" | "vote";
  fault: "spike" | "frozen" | "drift" | "shift" | "all";
  /** Faults injected. */
  events: number;
  /** Faults with at least one of their values flagged. */
  events_detected: number;
  /** Share of the faults caught. */
  event_recall: number | null;
  /** Share of the changed values flagged. */
  recall: number | null;
  /** Flags on injected values over all new flags (fault = all only). */
  precision: number | null;
  /** New flags on clean values (fault = all only). */
  false_alarms: number | null;
  window_start: string;
  window_end: string;
  evaluated_at: string;
}

/** One earthquake located by the IGN, in its latest revision (gold.fct_earthquakes). */
export interface Earthquake {
  event_id: string;
  ts: string;
  lat: number;
  lon: number;
  magnitude: number | null;
  depth_km: number | null;
  distance_to_palma_km: number | null;
}

/** Who owns a source and under which terms it is used (the catalogue of sources, docs/data-governance.md). */
export interface Governance {
  /** Subject area: weather, air, sea, mobility... */
  domain: string;
  /** Publisher owning the data. */
  owner: string;
  /** Licence or reuse terms as the publisher states them. */
  license: string;
  terms_url: string;
  access: "open" | "api_key";
  /** Whether the source holds data about identifiable people. */
  personal_data: boolean;
  classification: "public" | "internal" | "restricted";
  /** `history`: a closed series, no SLA on its age. */
  lifecycle: "active" | "history";
}

/** Liveness of the API and of its warehouse connection. */
export interface Health {
  status: string;
  /** `ok` or `unavailable` */
  database: string;
  version: string;
}

/** People actually present in Mallorca on one day (gold.fct_human_pressure_daily, Ibestat IPH). */
export interface HumanPressureDay {
  local_date: string;
  is_weekend: boolean | null;
  /** Human Pressure Indicator: residents plus visitors. */
  people_present: number;
  /** Population in the INE register of that year. */
  residents: number | null;
  /** Year of the register (or the latest before). */
  register_year: number | null;
  /** People present minus residents. */
  people_over_residents: number | null;
  /** People present over residents. */
  pressure_ratio: number | null;
}

/** A place a source measures at (gold.dim_locations with its source from gold.dim_sources). */
export interface Location {
  source: string;
  label: string | null;
  /** `observation`, `model`, `schedule`... */
  kind: string | null;
  entity: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  lat: number;
  lon: number;
  first_seen: string | null;
  last_seen: string | null;
  n_metrics: number;
}

/** One marine heatwave at a coastal point: 5 or more days above the 90th percentile (gold.fct_marine_heatwaves). */
export interface MarineHeatwave {
  heatwave_id: string;
  point: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  start_date: string;
  end_date: string;
  days: number;
  peak_day: string | null;
  peak_sst_c: number | null;
  /** Highest anomaly against the climatology (°C). */
  max_intensity_c: number | null;
  mean_intensity_c: number | null;
  /** Sum of the daily anomalies (°C x days). */
  cumulative_intensity_c_days: number | null;
  /** Hobday et al. (2018). */
  category: "moderate" | "strong" | "severe" | "extreme";
  has_preliminary_days: boolean;
}

/** Scheduled public transport of one network in one day (gold.fct_bus_network_daily, fct_island_transit_daily). */
export interface MobilityDay {
  /** `emt_palma` (Palma buses) or `ctm` (the island) */
  network: "emt_palma" | "ctm";
  local_date: string;
  is_weekend: boolean;
  stops: number;
  stops_with_service: number;
  /** Vehicles calling at a stop, summed over every stop. */
  scheduled_stop_calls: number | null;
  avg_lines_per_served_stop: number | null;
  busiest_stop: string | null;
  busiest_stop_name: string | null;
  busiest_stop_departures: number | null;
}

/**
 * Error of the weather model against one station (gold.agg_model_bias_by_station): model minus station.
 *
 * The ``_adjusted`` temperature errors compare the model at the height of the station (6.5 °C per km), so a
 * mountain station measures the model and not the altitude.
 */
export interface ModelBias {
  station_source: string;
  station: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  station_name: string | null;
  model_point: string;
  distance_km: number | null;
  /** Height of the station minus that of the model cell, in metres. */
  elevation_diff_m: number | null;
  days_compared: number;
  temperature_bias_c: number | null;
  temperature_mae_c: number | null;
  temperature_rmse_c: number | null;
  temperature_bias_adjusted_c: number | null;
  temperature_mae_adjusted_c: number | null;
  temperature_rmse_adjusted_c: number | null;
  precipitation_bias_total_mm: number | null;
  rain_day_agreement: number | null;
  wind_speed_bias_kmh: number | null;
  first_day: string | null;
  last_day: string | null;
}

/** A municipality of Mallorca with its boundary (gold.dim_municipalities, IGN). */
export interface Municipality {
  municipality: string;
  name: string;
  lat: number;
  lon: number;
  area_km2: number;
  /** Rings of [lon, lat] vertices; the largest first. */
  polygon: [number, number][][];
}

/** One value of a series in the common schema (gold.fct_observations). */
export interface Observation {
  source: string;
  entity: string;
  metric: string;
  ts: string;
  value: number | null;
  unit: string | null;
  /** `ok`, `suspect` or `missing` */
  quality: string;
  lat: number | null;
  lon: number | null;
}

/** Population of a municipality of Mallorca on 1 January (gold.fct_population_yearly, INE municipal register). */
export interface PopulationYear {
  /** INE municipality code. */
  municipality: string;
  municipality_name: string | null;
  year: number;
  population: number | null;
  population_men: number | null;
  population_women: number | null;
  /** Inhabitants per km2. */
  density_per_km2: number | null;
  /** Change against the previous register (1996 for 1998). */
  population_change: number | null;
  /** Relative change (0.01 = +1 %). */
  population_change_pct: number | null;
}

/** The latest check of one quality rule on one source (gold.data_quality_summary). */
export interface QualityRule {
  source: string;
  rule: string;
  target: string;
  checked: number;
  failed: number;
  passed: boolean;
  failed_ratio: number | null;
  checked_at: string | null;
}

/** Tourism, water, climate and electricity in one month, with anomalies (gold.fct_resources_monthly). */
export interface ResourcesMonth {
  month: string;
  hydrological_year: number;
  international_tourists: number | null;
  tourists_anomaly: number | null;
  international_spending_eur: number | null;
  airport_passengers: number | null;
  hotel_bed_occupancy_pct: number | null;
  electricity_demand_gwh: number | null;
  electricity_demand_anomaly: number | null;
  reserves_pct: number | null;
  reserves_change_1m_pts: number | null;
  reserves_anomaly_pts: number | null;
  rain_mm: number | null;
  rain_hydrological_year_mm: number | null;
  rain_anomaly: number | null;
  temperature_mean_c: number | null;
  temperature_anomaly_c: number | null;
  hot_days: number | null;
}

/** The path of a line as a GeoJSON MultiLineString of [lon, lat] points: one polyline per direction. */
export interface RouteGeometry {
  type: "MultiLineString";
  coordinates: [number, number][][];
}

/** Sea conditions at one coastal point in one hour (gold.fct_sea_conditions_hourly). */
export interface SeaHour {
  point: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  lat: number | null;
  lon: number | null;
  ts: string;
  wave_height_m: number | null;
  wave_period_s: number | null;
  swell_height_m: number | null;
  sea_temperature_c: number | null;
}

/** Satellite sea surface temperature at one coastal point on one day (gold.fct_sea_temperature_daily, OISST). */
export interface SeaTemperatureDay {
  point: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  /** Centre of the 0.25 degree cell. */
  lat: number | null;
  lon: number | null;
  /** UTC day the analysis describes. */
  day: string;
  sst_c: number | null;
  /** True until the final value replaces it, about 16 days later. */
  is_preliminary: boolean;
  /** 1991-2020 mean of the same day of the year, smoothed. */
  sst_climatology_c: number | null;
  /** 90th percentile of the same day of the year: the heatwave threshold. */
  sst_p90_c: number | null;
  sst_anomaly_c: number | null;
  /** Part of a marine heatwave (Hobday et al., 2016). */
  is_marine_heatwave: boolean;
  heatwave_id: string | null;
}

/** The sea around Mallorca in one month, from the satellite (gold.fct_sea_temperature_monthly, OISST). */
export interface SeaTemperatureMonth {
  month: string;
  points: number;
  days_reported: number;
  sst_mean_c: number | null;
  /** 1991-2020 climatology of the same days. */
  sst_climatology_c: number | null;
  sst_anomaly_c: number | null;
  /** Marine heatwave days, mean of the coastal points. */
  heatwave_days: number | null;
  /** Days with a marine heatwave at any coastal point. */
  days_with_heatwave: number;
  has_preliminary_days: boolean;
}

/** One daily series of a source: its entity, metric and coverage (gold.agg_daily_metrics). */
export interface Series {
  source: string;
  entity: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  metric: string;
  unit: string | null;
  first_day: string;
  last_day: string;
  /** Local days with at least one sample. */
  days: number;
}

/** One local day of a series: its statistics, completeness and flagged values (gold.agg_daily_metrics). */
export interface SeriesDay {
  local_date: string;
  /** Samples of the day, missing included. */
  samples: number;
  /** Samples with a value. */
  valid: number;
  /** Samples a quality rule labelled suspect. */
  suspect: number;
  /** Of the samples labelled ok. */
  min_value: number | null;
  avg_value: number | null;
  max_value: number | null;
  /** Share of samples with a value (0-1). */
  completeness: number | null;
  /** Instants of the day flagged by an anomaly detector (silver.anomalies). */
  anomalies: number;
}

/** The SLA agreed for a source and whether it is met now. Null means unknown (no target or nothing to judge). */
export interface Sla {
  /** Maximum age of the newest value, in hours. */
  data_age_hours: number | null;
  /** Minimum share of successful runs in 7 days (0-1). */
  success_rate: number;
  age_met: boolean | null;
  success_met: boolean | null;
  /** False if either part is breached, true if a known part is met. */
  met: boolean | null;
}

/** One data source, its health, its governance and its SLA (gold.source_health). */
export interface Source {
  source: string;
  label: string | null;
  kind: string | null;
  /** running, success, failed (our side) or unavailable (the source was down). */
  last_status: "running" | "success" | "failed" | "unavailable" | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_loaded_day: string | null;
  runs_7d: number;
  /** Runs in 7 days that failed on our side. */
  failed_7d: number;
  /** Runs in 7 days whose source was down. */
  unavailable_7d: number;
  /** Share of the runs in 7 days that did not load (0-1). */
  failure_rate_7d: number | null;
  latest_observation_ts: string | null;
  data_age_hours: number | null;
  observations: number;
  governance: Governance;
  sla: Sla;
}

/** The weather of one station or model point on the latest day of its source (gold.fct_weather_daily). */
export interface StationDay {
  source: string;
  entity: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  lat: number;
  lon: number;
  local_date: string;
  temperature_mean: number;
  temperature_max: number | null;
  temperature_min: number | null;
  precipitation_sum: number | null;
  wind_gust_max: number | null;
}

/** The scheduled service of one stop on the latest day of its network. */
export interface StopService {
  network: "emt_palma" | "ctm";
  stop: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  name: string | null;
  lat: number;
  lon: number;
  local_date: string;
  departures: number | null;
  lines: number | null;
}

/** Balearic tourism in one month (gold.fct_tourism_monthly, Dataestur). */
export interface TourismMonth {
  month: string;
  international_tourists: number | null;
  international_spending_eur: number | null;
  international_tourist_nights: number | null;
  spending_per_tourist_eur: number | null;
  hotel_guests: number | null;
  hotel_nights: number | null;
  hotel_average_stay_nights: number | null;
  hotel_bed_occupancy_pct: number | null;
  hotels_open: number | null;
  hotel_staff: number | null;
  airport_passengers: number | null;
  international_tourists_yoy: number | null;
  airport_passengers_yoy: number | null;
}

/** Tourist dwellings of a municipality of Mallorca in one reference month (gold.fct_tourist_dwellings, INE). */
export interface TouristDwellings {
  /** INE municipality code. */
  municipality: string;
  municipality_name: string | null;
  /** Month the listings were counted in. */
  reference_month: string;
  tourist_dwellings: number | null;
  tourist_beds: number | null;
  beds_per_dwelling: number | null;
  /** Register the ratios use (the latest up to the month). */
  population_year: number | null;
  dwellings_per_1000_inhabitants: number | null;
  beds_per_100_inhabitants: number | null;
  /** Reference month of the previous count. */
  previous_month: string | null;
  /** Change against the previous count. */
  dwellings_change: number | null;
  /** Relative change (0.01 = +1 %). */
  dwellings_change_pct: number | null;
}

/** One line of a transit network with its path and its departures on the latest day of the network. */
export interface TransitRoute {
  network: "emt_palma" | "ctm";
  /** Entity of the line's `scheduled_trips` series. */
  route: string;
  short_name: string;
  name: string;
  /** bus, train, metro or tram. */
  kind: string;
  /** The colour the operator gives the line. */
  color: string | null;
  local_date: string | null;
  /** Departures of the line that day. */
  trips: number | null;
  geometry: RouteGeometry;
}

/** An AEMET warning zone of Mallorca with its polygon (gold.dim_warning_zones). */
export interface WarningZone {
  zone: string;
  name: string;
  /** `land` or `coast` */
  kind: "land" | "coast";
  /** [lon, lat] vertices. */
  polygon: [number, number][];
}

/** Groundwater reserves of Mallorca in one month (gold.fct_water_reserves_monthly). */
export interface WaterReservesMonth {
  month: string;
  /** September to August, named after the year it ends in. */
  hydrological_year: number;
  /** Share of a full aquifer, island-wide. */
  reserves_pct: number;
  change_1m_pts: number | null;
  change_12m_pts: number | null;
  same_month_mean_pct: number | null;
  /** Reserves minus the mean of the same calendar month. */
  anomaly_pts: number | null;
  aquifers: number | null;
  aquifers_below_30_pct: number | null;
  lowest_aquifer: string | null;
  lowest_aquifer_pct: number | null;
}

/** Error of the wave model against one SOCIB buoy (gold.agg_wave_model_bias_by_buoy): model minus buoy. */
export interface WaveModelBias {
  buoy: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  buoy_name: string | null;
  model_point: string;
  /** The name the source publishes (silver.entities); null when the identifier already reads as a name. */
  model_point_name: string | null;
  distance_km: number | null;
  hours_compared: number;
  wave_height_buoy_mean_m: number | null;
  wave_height_model_mean_m: number | null;
  /** Mean of model minus buoy, in metres. */
  wave_height_bias_m: number | null;
  wave_height_mae_m: number | null;
  wave_height_rmse_m: number | null;
  /** Pearson r of the hourly significant wave heights. */
  wave_height_correlation: number | null;
  /** Mean model height over mean buoy height. */
  model_ratio: number | null;
  first_ts: string | null;
  last_ts: string | null;
}

/** Consecutive days of heavy rain, strong wind or high waves on the island (gold.fct_weather_episodes). */
export interface WeatherEpisode {
  episode_id: string;
  start_date: string;
  end_date: string;
  days: number;
  episode_type: string;
  peak_rain_mm: number | null;
  peak_rain_station: string | null;
  peak_rain_day: string | null;
  max_stations_over_rain_threshold: number | null;
  peak_gust_kmh: number | null;
  peak_wave_m: number | null;
}

/** Island-wide weather of one source in one day: the mean of its stations or points (gold.fct_weather_daily). */
export interface WeatherSourceDay {
  source: string;
  source_label: string | null;
  /** `observation` or `model` */
  source_kind: string | null;
  local_date: string;
  entities: number;
  temperature_mean: number | null;
  temperature_max: number | null;
  temperature_min: number | null;
  precipitation_mean: number | null;
  wind_gust_max: number | null;
}

/** An AEMET warning: one zone and phenomenon at one level for a period (gold.fct_weather_warnings). */
export interface WeatherWarning {
  warning_id: string;
  zone: string;
  zone_name: string | null;
  /** `land` or `coast` */
  zone_kind: string | null;
  /** `rain`, `storms`, `wind`, `coastal`, `max_temperature`... */
  phenomenon: string;
  /** 1 yellow, 2 orange, 3 red. */
  level: number;
  start_ts: string;
  end_ts: string;
}
