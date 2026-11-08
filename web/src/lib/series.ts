import type { Series, SeriesDay } from "../api";
import { dayShort, monthShort, placeName } from "./format";

/** Spanish names of the metrics; any other metric is shown by its identifier. */
const METRICS: Record<string, string> = {
  temperature_2m: "Temperatura",
  temperature_2m_mean: "Temperatura media",
  temperature_2m_max: "Temperatura máxima",
  temperature_2m_min: "Temperatura mínima",
  relative_humidity_2m: "Humedad relativa",
  relative_humidity_2m_mean: "Humedad relativa media",
  precipitation: "Precipitación",
  precipitation_sum: "Precipitación diaria",
  wind_speed_10m: "Viento",
  wind_speed_10m_mean: "Viento medio",
  wind_gusts_10m: "Rachas de viento",
  wind_gusts_10m_max: "Racha máxima",
  surface_pressure: "Presión en superficie",
  pressure_msl: "Presión al nivel del mar",
  pressure_station_max: "Presión máxima",
  pressure_station_min: "Presión mínima",
  sunshine_duration: "Horas de sol",
  nitrogen_dioxide: "NO₂",
  ozone: "O₃",
  pm10: "PM10",
  pm2_5: "PM2,5",
  sulphur_dioxide: "SO₂",
  carbon_monoxide: "CO",
  european_aqi: "Índice europeo de calidad del aire",
  wave_height: "Altura de ola",
  wave_period: "Periodo de ola",
  wave_direction: "Dirección de ola",
  swell_wave_height: "Mar de fondo",
  sea_surface_temperature: "Temperatura del mar",
  sea_level_height_msl: "Nivel del mar",
  ocean_current_velocity: "Corriente",
  scheduled_departures: "Pasos programados",
  scheduled_trips: "Salidas programadas",
  lines_served: "Líneas",
  electricity_demand: "Demanda eléctrica",
  generation_total: "Generación total",
  co2_emissions: "Emisiones de CO₂",
  co2_intensity: "Intensidad de CO₂",
  water_reserves: "Reservas de agua",
  human_pressure: "Población real presente",
  population: "Población",
  population_men: "Población (hombres)",
  population_women: "Población (mujeres)",
  airport_passengers: "Pasajeros del aeropuerto",
  international_tourists: "Turistas internacionales",
  international_tourist_nights: "Pernoctaciones de turistas internacionales",
  international_tourist_spending: "Gasto de turistas internacionales",
  hotel_guests: "Viajeros en hoteles",
  hotel_nights: "Pernoctaciones hoteleras",
  hotel_bed_occupancy: "Ocupación hotelera por plazas",
  hotel_staff: "Personal de hoteles",
  hotels_open: "Hoteles abiertos",
};

/** How the units are written; any other unit is shown as it is stored. */
const UNITS: Record<string, string> = {
  degC: "°C",
  pct: "%",
  "ug/m3": "µg/m³",
  eaqi: "",
  deg: "°",
  people: "personas",
  trips: "salidas",
  buses: "autobuses",
  vehicles: "vehículos",
  lines: "líneas",
  nights: "noches",
  passengers: "pasajeros",
  establishments: "hoteles",
};

export function metricLabel(metric: string): string {
  return METRICS[metric] ?? metric.replace(/_/g, " ");
}

export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  return UNITS[unit] ?? unit;
}

/** The metrics of a source, by their Spanish name. */
export function metricsOf(series: Series[]): string[] {
  return [...new Set(series.map((s) => s.metric))].sort((a, b) => metricLabel(a).localeCompare(metricLabel(b), "es"));
}

/** The series of one metric, by the name of their entity. */
export function entitiesOf(series: Series[], metric: string): Series[] {
  return series
    .filter((s) => s.metric === metric)
    .sort((a, b) => placeName(a.entity, a.name).localeCompare(placeName(b.entity, b.name), "es"));
}

/** The series to open first: the one with most days (ties by name), so the chart is not empty. */
export function longest(series: Series[]): Series | undefined {
  return [...series].sort((a, b) => b.days - a.days)[0];
}

export const RANGES = { month: "30 días", year: "1 año", five: "5 años", all: "Todo" } as const;
export type Range = keyof typeof RANGES;

/** First day of a range that ends on the series' last day ("all" starts on its first day). */
export function rangeStart(series: Series, range: Range): string {
  if (range === "all") return series.first_day;
  const days = { month: 30, year: 365, five: 5 * 365 }[range];
  const last = new Date(`${series.last_day}T00:00:00Z`);
  last.setUTCDate(last.getUTCDate() - (days - 1));
  const start = last.toISOString().slice(0, 10);
  return start < series.first_day ? series.first_day : start;
}

/** A date axis label for a range of `spanDays`: the day for a few months, then the month, then the year. */
export function axisDate(ms: number, spanDays: number): string {
  const iso = new Date(ms).toISOString();
  if (spanDays > 3 * 365) return iso.slice(0, 4);
  if (spanDays > 120) return monthShort(iso.slice(0, 7));
  return dayShort(iso);
}

/** Days from the first to the last day shown, both included. */
export function spanOf(days: SeriesDay[]): number {
  const first = days[0]?.local_date;
  const last = days.at(-1)?.local_date;
  if (!first || !last) return 0;
  return (Date.parse(last) - Date.parse(first)) / 86_400_000 + 1;
}

export interface SeriesSummary {
  days: number;
  completeness: number | null;
  suspect: number;
  anomalies: number;
  min: number | null;
  mean: number | null;
  max: number | null;
}

/** Figures of the days shown: the lowest minimum, the mean of the daily means and the highest maximum. */
export function summarize(days: SeriesDay[]): SeriesSummary {
  const means = days.flatMap((d) => (d.avg_value === null ? [] : [d.avg_value]));
  const mins = days.flatMap((d) => (d.min_value === null ? [] : [d.min_value]));
  const maxes = days.flatMap((d) => (d.max_value === null ? [] : [d.max_value]));
  const samples = days.reduce((n, d) => n + d.samples, 0);
  return {
    days: days.length,
    completeness: samples ? days.reduce((n, d) => n + d.valid, 0) / samples : null,
    suspect: days.reduce((n, d) => n + d.suspect, 0),
    anomalies: days.reduce((n, d) => n + d.anomalies, 0),
    min: mins.length ? Math.min(...mins) : null,
    mean: means.length ? means.reduce((a, b) => a + b, 0) / means.length : null,
    max: maxes.length ? Math.max(...maxes) : null,
  };
}
