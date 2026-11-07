// Types and calls of the REST API (api/schemas.py). The front end reads only the API, never the warehouse.

export interface Health {
  status: string;
  database: string;
  version: string;
}

export interface Source {
  source: string;
  label: string | null;
  kind: string | null;
  last_status: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_loaded_day: string | null;
  runs_7d: number;
  failure_rate_7d: number | null;
  latest_observation_ts: string | null;
  data_age_hours: number | null;
  observations: number;
}

export interface Location {
  source: string;
  label: string | null;
  kind: string | null;
  entity: string;
  /** The name the source publishes (a stop, a station); null when the identifier already reads as one. */
  name: string | null;
  lat: number;
  lon: number;
  first_seen: string | null;
  last_seen: string | null;
  n_metrics: number;
}

export interface ResourcesMonth {
  month: string;
  international_tourists: number | null;
  tourists_anomaly: number | null;
  airport_passengers: number | null;
  hotel_bed_occupancy_pct: number | null;
  electricity_demand_gwh: number | null;
  electricity_demand_anomaly: number | null;
  reserves_pct: number | null;
  reserves_anomaly_pts: number | null;
  rain_mm: number | null;
  rain_anomaly: number | null;
  temperature_mean_c: number | null;
  temperature_anomaly_c: number | null;
}

export interface TourismMonth {
  month: string;
  international_tourists: number | null;
  international_spending_eur: number | null;
  spending_per_tourist_eur: number | null;
  hotel_bed_occupancy_pct: number | null;
  airport_passengers: number | null;
  international_tourists_yoy: number | null;
  airport_passengers_yoy: number | null;
}

export interface ClimateMonth {
  month: string;
  hydrological_year: number;
  rain_mm: number | null;
  rain_hydrological_year_mm: number | null;
  rain_hydrological_year_mean_mm: number | null;
  temperature_mean_c: number | null;
  temperature_anomaly_c: number | null;
  hot_days: number | null;
}

export interface WaterReservesMonth {
  month: string;
  hydrological_year: number;
  reserves_pct: number;
  same_month_mean_pct: number | null;
  anomaly_pts: number | null;
  aquifers_below_30_pct: number | null;
  lowest_aquifer: string | null;
}

export interface Aquifer {
  entity: string;
  aquifer: string;
  month: string;
  reserves_pct: number | null;
  change_12m_pts: number | null;
}

export interface MobilityDay {
  network: "emt_palma" | "ctm";
  local_date: string;
  is_weekend: boolean;
  stops: number;
  stops_with_service: number;
  scheduled_stop_calls: number | null;
  busiest_stop: string | null;
  busiest_stop_name: string | null;
  busiest_stop_departures: number | null;
}

export interface StopService {
  network: "emt_palma" | "ctm";
  stop: string;
  /** The name the source publishes (a stop, a station); null when the identifier already reads as one. */
  name: string | null;
  lat: number;
  lon: number;
  local_date: string;
  departures: number | null;
  lines: number | null;
}

export interface WeatherSourceDay {
  source: string;
  source_label: string | null;
  source_kind: string | null;
  local_date: string;
  entities: number;
  temperature_mean: number | null;
  temperature_max: number | null;
  precipitation_mean: number | null;
  wind_gust_max: number | null;
}

export interface StationDay {
  source: string;
  entity: string;
  /** The name the source publishes (a stop, a station); null when the identifier already reads as one. */
  name: string | null;
  lat: number;
  lon: number;
  local_date: string;
  temperature_mean: number;
  temperature_max: number | null;
  temperature_min: number | null;
  precipitation_sum: number | null;
}

export interface WeatherWarning {
  warning_id: string;
  zone: string;
  zone_name: string | null;
  zone_kind: string | null;
  phenomenon: string;
  level: number;
  start_ts: string;
  end_ts: string;
}

export interface WarningZone {
  zone: string;
  name: string;
  kind: "land" | "coast";
  polygon: [number, number][];
}

export interface PopulationYear {
  municipality: string;
  municipality_name: string | null;
  year: number;
  population: number | null;
  population_men: number | null;
  population_women: number | null;
  density_per_km2: number | null;
  population_change: number | null;
  population_change_pct: number | null;
}

export interface HumanPressureDay {
  local_date: string;
  is_weekend: boolean | null;
  people_present: number;
  residents: number | null;
  register_year: number | null;
  people_over_residents: number | null;
  pressure_ratio: number | null;
}

export interface Municipality {
  municipality: string;
  name: string;
  lat: number;
  lon: number;
  area_km2: number;
  /** Rings of [lon, lat] vertices, the largest first (Palma also has the Cabrera archipelago). */
  polygon: [number, number][][];
}

export interface WeatherEpisode {
  episode_id: string;
  start_date: string;
  end_date: string;
  days: number;
  episode_type: string;
  peak_rain_mm: number | null;
  peak_rain_station: string | null;
  peak_gust_kmh: number | null;
  peak_wave_m: number | null;
}

export interface ModelBias {
  station_source: string;
  station: string;
  station_name: string | null;
  model_point: string;
  days_compared: number;
  temperature_bias_c: number | null;
  temperature_mae_c: number | null;
  rain_day_agreement: number | null;
}

export interface AirQualityNow {
  source: string;
  entity: string;
  /** The name the source publishes (a stop, a station); null when the identifier already reads as one. */
  name: string | null;
  lat: number | null;
  lon: number | null;
  ts: string;
  pm2_5: number | null;
  pm10: number | null;
  no2: number | null;
  o3: number | null;
  eaqi_band: number;
  eaqi_label: string | null;
}

export interface SeaHour {
  point: string;
  ts: string;
  wave_height_m: number | null;
  sea_temperature_c: number | null;
}

export interface Earthquake {
  event_id: string;
  ts: string;
  lat: number;
  lon: number;
  magnitude: number | null;
  depth_km: number | null;
  distance_to_palma_km: number | null;
}

export interface QualityRule {
  source: string;
  rule: string;
  target: string;
  checked: number;
  failed: number;
  passed: boolean;
  failed_ratio: number | null;
}

export interface AnomaliesDay {
  local_date: string;
  detector: string;
  anomalies: number;
}

export interface Correction {
  source: string;
  entity: string;
  name: string | null;
  metric: string;
  ts: string;
  unit: string | null;
  original_quality: string;
  original_value: number | null;
  corrected_value: number;
  method: string;
  confidence: number;
}

interface Page<T> {
  items: T[];
}

const BASE = "/api/v1";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

const answers = new Map<string, Promise<unknown>>();

/**
 * The answer to `path`, asked for once per page load: a past day does not change, so playing the days again or
 * going back to one is instant. A failed request is forgotten, so the next attempt asks again.
 */
function remembered<T>(path: string, load: (path: string) => Promise<T>): Promise<T> {
  let answer = answers.get(path) as Promise<T> | undefined;
  if (!answer) {
    answer = load(path);
    answers.set(path, answer);
    answer.catch(() => answers.delete(path));
  }
  return answer;
}

/** An ISO day `days` before today, for the `from` and `start` parameters. */
export function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export const api = {
  health: () => get<Health>("/health"),
  sources: () => get<Source[]>("/sources"),
  locations: () => get<Location[]>("/locations"),
  resources: (from: string) => get<ResourcesMonth[]>(`/resources/monthly?from=${from}`),
  tourism: (from: string) => get<TourismMonth[]>(`/tourism/monthly?from=${from}`),
  climate: (from: string) => get<ClimateMonth[]>(`/climate/monthly?from=${from}`),
  water: (from: string) => get<WaterReservesMonth[]>(`/water/reserves?from=${from}`),
  aquifers: () => get<Aquifer[]>("/water/aquifers"),
  mobilityDaily: (from: string) => get<MobilityDay[]>(`/mobility/daily?from=${from}`),
  stops: () => get<StopService[]>("/mobility/stops"),
  weatherDaily: (from: string) => get<WeatherSourceDay[]>(`/weather/daily?from=${from}`),
  stations: (source: "aemet" | "socib" | "open_meteo", day?: string | null) =>
    remembered(`/weather/stations?source=${source}${day ? `&date=${day}` : ""}`, get<StationDay[]>),
  warnings: () => get<WeatherWarning[]>("/warnings"),
  warningZones: () => get<WarningZone[]>("/warnings/zones"),
  population: (from: number) => get<PopulationYear[]>(`/population?from=${from}`),
  humanPressure: (from: string) => get<HumanPressureDay[]>(`/population/pressure?from=${from}`),
  municipalities: () => get<Municipality[]>("/municipalities"),
  episodes: (from: string) => get<WeatherEpisode[]>(`/weather/episodes?from=${from}`),
  modelBias: () => get<ModelBias[]>("/weather/model-bias"),
  airQuality: () => get<AirQualityNow[]>("/air-quality/latest"),
  sea: (start: string) => get<SeaHour[]>(`/sea/hourly?start=${start}T00:00:00Z`),
  earthquakes: () => get<Earthquake[]>("/earthquakes"),
  qualityRules: () => get<QualityRule[]>("/quality/rules"),
  anomaliesDaily: (start: string) => get<AnomaliesDay[]>(`/anomalies/daily?start=${start}T00:00:00Z`),
  corrections: (start: string) =>
    get<Page<Correction>>(`/corrections?start=${start}T00:00:00Z&limit=8`).then((page) => page.items),
};
