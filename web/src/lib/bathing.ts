// Bathing water quality (Náyade) on the climate and water page: the map of the beaches coloured by their class of
// the Bathing Water Directive, the card of each beach and the island's share of excellent waters per season.

import type { BathingWaterSeason, BathingWaterYear } from "../api";
import type { MapLayer } from "../components/PointMap";
import { messages } from "../i18n";
import { dayName, number } from "./format";

/** The classes of the directive, best first: 4 excellent, 3 good, 2 sufficient, 1 poor (the EEA's colours). */
export const QUALITY_CLASSES = [4, 3, 2, 1] as const;
export type QualityClass = (typeof QUALITY_CLASSES)[number];
export const QUALITY_COLORS: Record<QualityClass, string> = { 4: "#0284c7", 3: "#16a34a", 2: "#ca8a04", 1: "#dc2626" };
export const UNCLASSIFIED_COLOR = "#94a3b8";

/** The name of a class in the language of the page ("Excelente"), or "Sin clasificar" for null. */
export function qualityName(qualityClass: number | null): string {
  const m = messages().bathing;
  return qualityClass && qualityClass in m.classes ? m.classes[qualityClass as QualityClass] : m.unclassified;
}

/** How the class moved against the previous season, or null when either season has none. */
export function changeText(row: BathingWaterSeason): string | null {
  const m = messages().bathing;
  if (row.quality_class === null || row.previous_quality_class === null) return null;
  const previous = qualityName(row.previous_quality_class).toLowerCase();
  if (row.quality_class > row.previous_quality_class) return m.upgraded(previous);
  if (row.quality_class < row.previous_quality_class) return m.downgraded(previous);
  return m.unchanged;
}

/** The lines of a beach's card: name, municipality, class and its change, samples and worst results, restrictions. */
export function bathingCard(row: BathingWaterSeason): string[] {
  const m = messages().bathing;
  const lines = [
    row.name ?? row.bathing_water,
    row.municipality_name ?? row.municipality,
    `${m.classLine(String(row.season))}: ${qualityName(row.quality_class)}`,
  ];
  const change = changeText(row);
  if (change) lines.push(change);
  if (row.quality_class === null) lines.push(m.tooFewSamples(row.assessed_samples));
  lines.push(m.samplesLine(row.samples, row.last_sample_date ? dayName(row.last_sample_date) : "-"));
  if (row.worst_e_coli !== null || row.worst_enterococci !== null) {
    lines.push(m.worstLine(number(row.worst_e_coli ?? 0), number(row.worst_enterococci ?? 0)));
  }
  if (row.restrictions > 0) lines.push(m.restrictionsLine(row.restrictions, row.bans));
  return lines;
}

/** One map layer per class (best first) and one for the waters without a class, each beach with its card. */
export function bathingLayers(rows: BathingWaterSeason[]): MapLayer[] {
  const classes: (QualityClass | null)[] = [...QUALITY_CLASSES, null];
  return classes
    .map((qualityClass) => ({
      id: `bathing-${qualityClass ?? "none"}`,
      label: qualityName(qualityClass),
      color: qualityClass ? QUALITY_COLORS[qualityClass] : UNCLASSIFIED_COLOR,
      radius: 6,
      points: rows
        .filter((r) => r.quality_class === qualityClass)
        .map((r) => ({ lat: r.lat, lon: r.lon, popup: bathingCard(r) })),
    }))
    .filter((layer) => layer.points.length > 0);
}

/** The latest season with classified waters, as its share of excellent ones and the counts behind it. */
export function latestShare(years: BathingWaterYear[]): BathingWaterYear | null {
  return years.filter((y) => y.classified > 0 && y.excellent_share !== null).at(-1) ?? null;
}
