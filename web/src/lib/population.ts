import { inside } from "./interpolate";

/** The fields of a stop and a municipality that the joins below need (see api.ts). */
interface Stop {
  lat: number;
  lon: number;
  departures: number | null;
}

interface Place {
  municipality: string;
  lat: number;
  lon: number;
  polygon: [number, number][][];
}

interface PopulationRow {
  municipality: string;
  year: number;
  population: number | null;
}

export interface Service {
  stops: number;
  departures: number;
}

/**
 * The municipality of every stop: the boundary that contains it or, for the few stops on the coast that the
 * simplified boundaries (about 150 m) leave outside, the municipality with the nearest centre.
 */
export function municipalityOf(stop: { lat: number; lon: number }, places: Place[]): string | null {
  const hit = places.find((p) => p.polygon.some((ring) => inside(stop.lon, stop.lat, ring)));
  if (hit) return hit.municipality;
  let best: Place | null = null;
  let bestDistance = Infinity;
  for (const p of places) {
    // Equirectangular distance in degrees, longitude scaled by cos(39.6°): enough to rank nearby centres.
    const d = Math.hypot((p.lon - stop.lon) * 0.77, p.lat - stop.lat);
    if (d < bestDistance) [best, bestDistance] = [p, d];
  }
  return best?.municipality ?? null;
}

/** Stops and scheduled departures of the latest day per municipality. */
export function serviceByMunicipality(stops: Stop[], places: Place[]): Map<string, Service> {
  const service = new Map<string, Service>();
  for (const stop of stops) {
    const code = municipalityOf(stop, places);
    if (code === null) continue;
    const own = service.get(code) ?? { stops: 0, departures: 0 };
    own.stops += 1;
    own.departures += stop.departures ?? 0;
    service.set(code, own);
  }
  return service;
}

/** Mallorca's population per year: the sum of its municipalities (years with every municipality only). */
export function islandTotals(rows: PopulationRow[]): { year: number; population: number }[] {
  const byYear = new Map<number, { population: number; municipalities: number }>();
  for (const r of rows) {
    if (r.population === null) continue;
    const own = byYear.get(r.year) ?? { population: 0, municipalities: 0 };
    own.population += r.population;
    own.municipalities += 1;
    byYear.set(r.year, own);
  }
  const complete = Math.max(0, ...[...byYear.values()].map((v) => v.municipalities));
  return [...byYear.entries()]
    .filter(([, v]) => v.municipalities === complete)
    .map(([year, v]) => ({ year, population: v.population }))
    .sort((a, b) => a.year - b.year);
}

/** Relative change between two values (0.1 = +10 %), or null without a base. */
export function change(now: number | null | undefined, before: number | null | undefined): number | null {
  return now == null || before == null || before === 0 ? null : now / before - 1;
}

/** A colour of a sequential scale from its upper bounds (the last colour for anything above them). */
export function binColor(value: number | null, bounds: number[], colors: string[]): string {
  if (value === null) return "#9ca3af";
  const index = bounds.findIndex((b) => value < b);
  return colors[index === -1 ? colors.length - 1 : index] ?? "#9ca3af";
}

/** The days of a year as "MM-DD", 29 February included, for charts that lay several years over each other. */
export const DAYS_OF_YEAR: string[] = Array.from({ length: 366 }, (_, i) => {
  const day = new Date(Date.UTC(2024, 0, 1 + i)); // 2024 is a leap year
  return day.toISOString().slice(5, 10);
});

interface PressureRow {
  local_date: string;
  people_present: number;
}

/**
 * The people present on each day of the year, one row per year (newest first) with a value per `DAYS_OF_YEAR`
 * (null for the days a year does not have or has not published).
 */
export function pressureByYear(days: PressureRow[]): { year: number; values: (number | null)[] }[] {
  const byYear = new Map<number, Map<string, number>>();
  for (const d of days) {
    const year = Number(d.local_date.slice(0, 4));
    if (!byYear.has(year)) byYear.set(year, new Map());
    byYear.get(year)?.set(d.local_date.slice(5, 10), d.people_present);
  }
  return [...byYear.keys()]
    .sort((a, b) => b - a)
    .map((year) => ({ year, values: DAYS_OF_YEAR.map((day) => byYear.get(year)?.get(day) ?? null) }));
}

/** The day of the most people present among `days`, or null without days. */
export function busiestDay<T extends PressureRow>(days: T[]): T | null {
  return days.reduce<T | null>((best, d) => (best === null || d.people_present > best.people_present ? d : best), null);
}
