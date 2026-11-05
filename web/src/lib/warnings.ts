// AEMET warnings: their levels and phenomena in words, and the level of each zone over a period.

import type { WeatherWarning } from "../api";

/** Meteoalerta levels with AEMET's own colours (0 is "no risk", shown green). */
export const LEVELS = [
  { label: "Sin aviso", color: "#4ade80" },
  { label: "Amarillo", color: "#facc15" },
  { label: "Naranja", color: "#f97316" },
  { label: "Rojo", color: "#dc2626" },
];

export const PHENOMENA: Record<string, string> = {
  rain: "Lluvias",
  storms: "Tormentas",
  wind: "Viento",
  coastal: "Fenómenos costeros",
  max_temperature: "Temperaturas máximas",
  min_temperature: "Temperaturas mínimas",
  snow: "Nevadas",
  fog: "Nieblas",
  rissaga: "Rissagas",
  dust: "Polvo en suspensión",
};

/** The warnings that overlap ``[from, to)``. */
export function overlapping(warnings: WeatherWarning[], from: Date, to: Date): WeatherWarning[] {
  return warnings.filter((w) => Date.parse(w.start_ts) < to.getTime() && Date.parse(w.end_ts) > from.getTime());
}

/** The highest level of each zone among the warnings (zones without any are left out: they are at 0). */
export function zoneLevels(warnings: WeatherWarning[]): Map<string, number> {
  const levels = new Map<string, number>();
  for (const w of warnings) levels.set(w.zone, Math.max(levels.get(w.zone) ?? 0, w.level));
  return levels;
}

/** "Amarillo por lluvias": a warning in words. */
export function describe(w: WeatherWarning): string {
  return `${LEVELS[w.level]?.label ?? "Aviso"} por ${(PHENOMENA[w.phenomenon] ?? w.phenomenon).toLowerCase()}`;
}
