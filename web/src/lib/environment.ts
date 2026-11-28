// The figures of the weather and environment page: key figures, air quality points, local times and subtitles.

import type { AirQualityNow, PollenDustDay, SeaHour, StationDay, WeatherSourceDay } from "../api";
import type { MapLayer } from "../components/PointMap";
import { messages } from "../i18n";
import { dayName, dayShort, number, placeName } from "./format";
import type { Kpi } from "./kpis";

/** The EEA's colours of the bands of the European Air Quality Index, from good to extremely poor. */
const EAQI_COLORS = ["#50f0e6", "#50ccaa", "#f0e641", "#ff5050", "#960032", "#7d2181"];

/** The bands of the European Air Quality Index with their names in the language of the page. */
export function eaqiBands(): { label: string; color: string }[] {
  const names = messages().environment.eaqi;
  return EAQI_COLORS.map((color, i) => ({ label: names[i] ?? String(i + 1), color }));
}

/** The band of an index value (1 to 6). */
export function eaqiBand(band: number): { label: string; color: string } | undefined {
  return eaqiBands()[band - 1];
}

/** Where the moderate level starts, in grains/m³ of daily mean (Red Española de Aerobiología; dbt vars.pollen_levels). */
export const POLLEN_MODERATE = { olive: 51, grass: 26 } as const;
/** A dust day: the island mean of CAMS dust reaches half the EU daily PM10 limit (dbt vars.dust_episode_ugm3). */
export const DUST_EPISODE_UGM3 = 25;

export interface IslandDay {
  date: string;
  olive: number | null;
  grass: number | null;
  dust: number | null;
}

/** The mean of a list without its nulls, or null when nothing is left. */
function meanOf(values: (number | null)[]): number | null {
  const known = values.filter((v): v is number => v !== null);
  return known.length === 0 ? null : known.reduce((a, b) => a + b, 0) / known.length;
}

/** The island per day: the mean of the daily means of its model points, for pollen and dust, oldest day first. */
export function islandDays(days: PollenDustDay[]): IslandDay[] {
  const byDate = new Map<string, PollenDustDay[]>();
  for (const d of days) byDate.set(d.local_date, [...(byDate.get(d.local_date) ?? []), d]);
  return [...byDate.keys()].sort().map((date) => {
    const points = byDate.get(date) ?? [];
    return {
      date,
      olive: meanOf(points.map((p) => p.olive_pollen_mean)),
      grass: meanOf(points.map((p) => p.grass_pollen_mean)),
      dust: meanOf(points.map((p) => p.dust_mean_ugm3)),
    };
  });
}

export function episodeType(type: string): string {
  const names: Record<string, string> = messages().environment.episodeTypes;
  return type.split(" + ").map((t) => names[t] ?? t).join(" + ");
}

export function environmentKpis(weather: WeatherSourceDay[], air: AirQualityNow[], sea: SeaHour[], quakes: number): Kpi[] {
  const m = messages().environment;
  const kpis: Kpi[] = [];
  const model = weather.filter((d) => d.source === "open_meteo" && d.temperature_mean !== null);
  const today = model.at(-1);
  if (today) {
    kpis.push({
      id: "temperature", label: m.meanTemperature, value: number(today.temperature_mean as number, 1), unit: "°C",
      month: m.modelDay(dayName(today.local_date)),
      deviation: today.temperature_max === null ? null : m.maximum(number(today.temperature_max, 1)),
      tone: "neutral", history: model.map((d) => ({ month: d.local_date, value: d.temperature_mean as number })),
    });
  }
  const stations = air.filter((a) => a.source === "eea_air_quality");
  if (stations.length > 0) {
    const worst = Math.max(...stations.map((a) => a.eaqi_band));
    const good = stations.filter((a) => a.eaqi_band <= 2).length;
    kpis.push({
      id: "air", label: m.air, value: eaqiBand(worst)?.label ?? "—", unit: "",
      month: m.worstStation, deviation: m.goodStations(good, stations.length),
      tone: worst <= 2 ? "good" : worst >= 4 ? "bad" : "neutral", history: [],
    });
  }
  const recent = sea.filter((s) => s.wave_height_m !== null && Date.parse(s.ts) > Date.now() - 86_400_000);
  if (recent.length > 0) {
    const top = recent.reduce((a, b) => ((b.wave_height_m ?? 0) > (a.wave_height_m ?? 0) ? b : a));
    kpis.push({
      id: "waves", label: m.highestWave, value: number(top.wave_height_m as number, 1), unit: "m",
      month: m.last24h, deviation: m.at(placeName(top.point)), tone: "neutral", history: [],
    });
  }
  kpis.push({
    id: "quakes", label: m.quakes, value: number(quakes), unit: "", month: m.lastYearIgn,
    deviation: null, tone: "neutral", history: [],
  });
  return kpis;
}

export function airLayers(air: AirQualityNow[]): MapLayer[] {
  const point = (a: AirQualityNow) => ({
    lat: a.lat as number, lon: a.lon as number, color: eaqiBand(a.eaqi_band)?.color,
    popup: [placeName(a.entity, a.name), eaqiBand(a.eaqi_band)?.label ?? "", `NO₂ ${a.no2 ?? "—"} · O₃ ${a.o3 ?? "—"} · PM10 ${a.pm10 ?? "—"} µg/m³`],
  });
  const located = air.filter((a) => a.lat !== null && a.lon !== null);
  const m = messages().environment;
  return [
    { id: "stations", label: m.stations, color: "#15803d", radius: 8, points: located.filter((a) => a.source === "eea_air_quality").map(point) },
    { id: "model", label: m.camsModel, color: "#d97706", radius: 5, points: located.filter((a) => a.source !== "eea_air_quality").map(point) },
  ];
}

/** An instant in Mallorca's local time: "5 nov 14:00". */
export function localTime(iso: string): string {
  const local = new Date(iso).toLocaleString("sv-SE", { timeZone: "Europe/Madrid" }); // "2026-11-05 14:00:00"
  return `${dayShort(local)} ${local.slice(11, 16)}`;
}

/** "Las 33 estaciones oficiales de AEMET el 3 de noviembre de 2026 (último día publicado), ...". */
export function temperatureSubtitle(stations: StationDay[] | null, day: string | null): string {
  const shown = stations?.[0]?.local_date;
  return messages().environment.temperatureSubtitle(stations?.length ?? 33, shown ? dayName(shown) : null, day === null);
}
