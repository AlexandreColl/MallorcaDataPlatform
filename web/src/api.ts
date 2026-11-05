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

export interface ClimateMonth {
  month: string;
  hydrological_year: number;
  rain_hydrological_year_mm: number | null;
  rain_hydrological_year_mean_mm: number | null;
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

export const api = {
  health: () => get<Health>("/health"),
  sources: () => get<Source[]>("/sources"),
  locations: () => get<Location[]>("/locations"),
  resources: (from: string) => get<ResourcesMonth[]>(`/resources/monthly?from=${from}`),
  climate: (from: string) => get<ClimateMonth[]>(`/climate/monthly?from=${from}`),
};
