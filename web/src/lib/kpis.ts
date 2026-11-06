// The key figures of the dashboards: the latest month of each series and how far it is from its usual value.

import type { ClimateMonth, ResourcesMonth, TourismMonth, WaterReservesMonth } from "../api";
import { compact, monthName, number, signed } from "./format";

/** Whether a deviation is good news, bad news or just a fact (more tourists is neither). */
export type Tone = "good" | "bad" | "neutral";

export interface Kpi {
  id: string;
  label: string;
  value: string;
  unit: string;
  month: string;
  deviation: string | null;
  tone: Tone;
  history: { month: string; value: number }[];
}

export interface Spec<Row> {
  id: string;
  label: string;
  unit: string;
  value: (row: Row) => number | null;
  format: (value: number) => string;
  /** The deviation of the row from its usual value, already as text, and whether it is good or bad. */
  deviation: (row: Row) => { text: string; tone: Tone } | null;
}

const HISTORY_MONTHS = 36;

function tone(value: number, goodWhenUp: boolean | null): Tone {
  if (goodWhenUp === null || value === 0) return "neutral";
  return value > 0 === goodWhenUp ? "good" : "bad";
}

/** A relative anomaly (0.25 = 25 % above the mean of the same month) as text. */
function relative(anomaly: number | null, goodWhenUp: boolean | null) {
  if (anomaly === null) return null;
  return { text: `${signed(anomaly * 100, 0)} % sobre lo normal`, tone: tone(anomaly, goodWhenUp) };
}

export const RESOURCE_SPECS: Spec<ResourcesMonth>[] = [
  {
    id: "reserves",
    label: "Reservas de agua",
    unit: "%",
    value: (r) => r.reserves_pct,
    format: (v) => number(v, 0),
    deviation: (r) =>
      r.reserves_anomaly_pts === null
        ? null
        : { text: `${signed(r.reserves_anomaly_pts)} puntos sobre lo normal`, tone: tone(r.reserves_anomaly_pts, true) },
  },
  {
    id: "tourists",
    label: "Turistas internacionales",
    unit: "",
    value: (r) => r.international_tourists,
    format: compact,
    deviation: (r) => relative(r.tourists_anomaly, null),
  },
  {
    id: "electricity",
    label: "Demanda eléctrica",
    unit: "GWh",
    value: (r) => r.electricity_demand_gwh,
    format: (v) => number(v, 0),
    deviation: (r) => relative(r.electricity_demand_anomaly, null),
  },
  {
    id: "temperature",
    label: "Temperatura media",
    unit: "°C",
    value: (r) => r.temperature_mean_c,
    format: (v) => number(v, 1),
    deviation: (r) =>
      r.temperature_anomaly_c === null
        ? null
        : { text: `${signed(r.temperature_anomaly_c)} °C sobre lo normal`, tone: tone(r.temperature_anomaly_c, false) },
  },
];

/** A change against the same month a year earlier (0.05 = 5 % more). */
function yearOnYear(change: number | null) {
  if (change === null) return null;
  return { text: `${signed(change * 100, 1)} % que hace un año`, tone: "neutral" as Tone };
}

export const TOURISM_SPECS: Spec<TourismMonth>[] = [
  {
    id: "tourists",
    label: "Turistas internacionales",
    unit: "",
    value: (r) => r.international_tourists,
    format: compact,
    deviation: (r) => yearOnYear(r.international_tourists_yoy),
  },
  {
    id: "airport",
    label: "Pasajeros del aeropuerto",
    unit: "",
    value: (r) => r.airport_passengers,
    format: compact,
    deviation: (r) => yearOnYear(r.airport_passengers_yoy),
  },
  {
    id: "occupancy",
    label: "Ocupación hotelera",
    unit: "%",
    value: (r) => r.hotel_bed_occupancy_pct,
    format: (v) => number(v, 1),
    deviation: () => null,
  },
];

export const WATER_SPECS: Spec<WaterReservesMonth>[] = [
  {
    id: "reserves",
    label: "Reservas de agua",
    unit: "%",
    value: (r) => r.reserves_pct,
    format: (v) => number(v, 0),
    deviation: (r) =>
      r.anomaly_pts === null
        ? null
        : { text: `${signed(r.anomaly_pts)} puntos sobre lo normal`, tone: tone(r.anomaly_pts, true) },
  },
  {
    id: "aquifers",
    label: "Acuíferos bajo el 30 %",
    unit: `de 18`,
    value: (r) => r.aquifers_below_30_pct,
    format: (v) => number(v, 0),
    deviation: (r) => (r.lowest_aquifer ? { text: `El más bajo: ${r.lowest_aquifer}`, tone: "neutral" } : null),
  },
];

export const HOT_DAYS_SPEC: Spec<ClimateMonth> = {
  id: "hot-days",
  label: "Días de calor",
  unit: "días",
  value: (r) => r.hot_days,
  format: (v) => number(v, 0),
  deviation: (r) =>
    r.temperature_anomaly_c === null
      ? null
      : { text: `${signed(r.temperature_anomaly_c)} °C sobre lo normal`, tone: tone(r.temperature_anomaly_c, false) },
};

export const RAIN_SPEC: Spec<ClimateMonth> = {
  id: "rain",
  label: "Lluvia del año hidrológico",
  unit: "mm",
  value: (r) => r.rain_hydrological_year_mm,
  format: (v) => number(v, 0),
  deviation: (r) =>
    r.rain_hydrological_year_mm === null || !r.rain_hydrological_year_mean_mm
      ? null
      : relative(r.rain_hydrological_year_mm / r.rain_hydrological_year_mean_mm - 1, true),
};

/**
 * The KPI of a series: its latest month with a value (each source publishes with its own delay, so the latest
 * month differs between KPIs) and the last 36 months for the sparkline.
 */
export function buildKpi<Row extends { month: string }>(spec: Spec<Row>, rows: Row[]): Kpi | null {
  const withValue = rows
    .filter((row) => spec.value(row) !== null)
    .sort((a, b) => a.month.localeCompare(b.month));
  const latest = withValue.at(-1);
  if (!latest) return null;
  const deviation = spec.deviation(latest);
  return {
    id: spec.id,
    label: spec.label,
    value: spec.format(spec.value(latest) as number),
    unit: spec.unit,
    month: monthName(latest.month),
    deviation: deviation?.text ?? null,
    tone: deviation?.tone ?? "neutral",
    history: withValue.slice(-HISTORY_MONTHS).map((row) => ({ month: row.month, value: spec.value(row) as number })),
  };
}
