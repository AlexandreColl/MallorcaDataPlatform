// AEMET warnings: their levels and phenomena in words, and the level of each zone over a period.

import type { WeatherWarning } from "../api";
import { messages } from "../i18n";

/** Meteoalerta levels with AEMET's own colours (0 is "no risk", shown green). */
export const LEVEL_COLORS = ["#4ade80", "#facc15", "#f97316", "#dc2626"];

/** The levels with their names in the language of the page. */
export function levels(): { label: string; color: string }[] {
  const names = messages().warnings.levels;
  return LEVEL_COLORS.map((color, i) => ({ label: names[i] ?? String(i), color }));
}

/** A phenomenon in words ("Lluvias"); one AEMET adds later is shown by its code. */
export function phenomenon(code: string): string {
  const names: Record<string, string> = messages().warnings.phenomena;
  return names[code] ?? code;
}

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
  const m = messages().warnings;
  return m.describe(m.levels[w.level] ?? m.warning, phenomenon(w.phenomenon));
}
