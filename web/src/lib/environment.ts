// The figures of the weather and environment page: key figures, air quality points, local times and subtitles.

import type { AirQualityNow, SeaHour, StationDay, WeatherSourceDay } from "../api";
import type { MapLayer } from "../components/PointMap";
import { dayName, dayShort, number, placeName } from "./format";
import type { Kpi } from "./kpis";

/** Bands of the European Air Quality Index, with the EEA's own colours. */
export const EAQI = [
  { label: "Buena", color: "#50f0e6" },
  { label: "Razonable", color: "#50ccaa" },
  { label: "Regular", color: "#f0e641" },
  { label: "Mala", color: "#ff5050" },
  { label: "Muy mala", color: "#960032" },
  { label: "Extremadamente mala", color: "#7d2181" },
];

const EPISODE_TYPES: Record<string, string> = { rain: "lluvia", wind: "viento", sea: "mar" };

export function episodeType(type: string): string {
  return type.split(" + ").map((t) => EPISODE_TYPES[t] ?? t).join(" + ");
}

export function environmentKpis(weather: WeatherSourceDay[], air: AirQualityNow[], sea: SeaHour[], quakes: number): Kpi[] {
  const kpis: Kpi[] = [];
  const model = weather.filter((d) => d.source === "open_meteo" && d.temperature_mean !== null);
  const today = model.at(-1);
  if (today) {
    kpis.push({
      id: "temperature", label: "Temperatura media", value: number(today.temperature_mean as number, 1), unit: "°C",
      month: `${dayName(today.local_date)} · modelo`,
      deviation: today.temperature_max === null ? null : `Máxima ${number(today.temperature_max, 1)} °C`,
      tone: "neutral", history: model.map((d) => ({ month: d.local_date, value: d.temperature_mean as number })),
    });
  }
  const stations = air.filter((a) => a.source === "eea_air_quality");
  if (stations.length > 0) {
    const worst = Math.max(...stations.map((a) => a.eaqi_band));
    const good = stations.filter((a) => a.eaqi_band <= 2).length;
    kpis.push({
      id: "air", label: "Calidad del aire", value: EAQI[worst - 1]?.label ?? "—", unit: "",
      month: "La peor estación, en la última hora", deviation: `${good} de ${stations.length} estaciones buenas o razonables`,
      tone: worst <= 2 ? "good" : worst >= 4 ? "bad" : "neutral", history: [],
    });
  }
  const recent = sea.filter((s) => s.wave_height_m !== null && Date.parse(s.ts) > Date.now() - 86_400_000);
  if (recent.length > 0) {
    const top = recent.reduce((a, b) => ((b.wave_height_m ?? 0) > (a.wave_height_m ?? 0) ? b : a));
    kpis.push({
      id: "waves", label: "Ola más alta", value: number(top.wave_height_m as number, 1), unit: "m",
      month: "Últimas 24 horas", deviation: `En ${placeName(top.point)}`, tone: "neutral", history: [],
    });
  }
  kpis.push({
    id: "quakes", label: "Sismos", value: number(quakes), unit: "", month: "Último año, IGN",
    deviation: null, tone: "neutral", history: [],
  });
  return kpis;
}

export function airLayers(air: AirQualityNow[]): MapLayer[] {
  const point = (a: AirQualityNow) => ({
    lat: a.lat as number, lon: a.lon as number, color: EAQI[a.eaqi_band - 1]?.color,
    popup: [placeName(a.entity, a.name), EAQI[a.eaqi_band - 1]?.label ?? "", `NO₂ ${a.no2 ?? "—"} · O₃ ${a.o3 ?? "—"} · PM10 ${a.pm10 ?? "—"} µg/m³`],
  });
  const located = air.filter((a) => a.lat !== null && a.lon !== null);
  return [
    { id: "stations", label: "Estaciones", color: "#15803d", radius: 8, points: located.filter((a) => a.source === "eea_air_quality").map(point) },
    { id: "model", label: "Modelo CAMS", color: "#d97706", radius: 5, points: located.filter((a) => a.source !== "eea_air_quality").map(point) },
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
  const when = shown ? ` el ${dayName(shown)}${day === null ? " (último día publicado)" : ""}` : "";
  return `Las ${stations?.length ?? 33} estaciones oficiales de AEMET${when}, interpoladas entre ellas y corregidas por la altitud.`;
}
