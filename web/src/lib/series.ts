import type { Series, SeriesDay } from "../api";
import { locale, messages, TAGS } from "../i18n";
import { dayShort, monthShort, placeName } from "./format";

/** How the units are written: symbols, and words in the language of the page. Any other is shown as stored. */
const SYMBOLS: Record<string, string> = { degC: "°C", pct: "%", "ug/m3": "µg/m³", eaqi: "", deg: "°" };

/** The name of a metric in the language of the page; any other metric is shown by its identifier. */
export function metricLabel(metric: string): string {
  const names: Record<string, string> = messages().series.metrics;
  return names[metric] ?? metric.replace(/_/g, " ");
}

export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  const words: Record<string, string> = messages().series.units;
  return SYMBOLS[unit] ?? words[unit] ?? unit;
}

/** Sorts names as the language of the page does. */
export function byName(a: string, b: string): number {
  return a.localeCompare(b, TAGS[locale()]);
}

/** The metrics of a source, by their name. */
export function metricsOf(series: Series[]): string[] {
  return [...new Set(series.map((s) => s.metric))].sort((a, b) => byName(metricLabel(a), metricLabel(b)));
}

/** The series of one metric, by the name of their entity. */
export function entitiesOf(series: Series[], metric: string): Series[] {
  return series
    .filter((s) => s.metric === metric)
    .sort((a, b) => byName(placeName(a.entity, a.name), placeName(b.entity, b.name)));
}

/** The series to open first: the one with most days (ties by name), so the chart is not empty. */
export function longest(series: Series[]): Series | undefined {
  return [...series].sort((a, b) => b.days - a.days)[0];
}

export const RANGES = ["month", "year", "five", "all"] as const;
export type Range = (typeof RANGES)[number];

export function rangeLabel(range: Range): string {
  return messages().series.ranges[range];
}

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

/** Days an export of the API may cover (API_EXPORT_MAX_DAYS). */
export const EXPORT_MAX_DAYS = 366;

/**
 * The link that downloads the values of `series` from `from` to its last day as a file, and whether it had to be
 * cut to the last `EXPORT_MAX_DAYS` days. The API counts the end as excluded: the day after the last one.
 */
export function exportLink(series: Series, from: string, format: "csv" | "parquet"): { href: string; clipped: boolean } {
  const end = new Date(`${series.last_day}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  const earliest = new Date(end);
  earliest.setUTCDate(earliest.getUTCDate() - EXPORT_MAX_DAYS);
  const start = new Date(`${from}T00:00:00Z`);
  const clipped = start < earliest;
  const params = new URLSearchParams({
    source: series.source, entity: series.entity, metric: series.metric,
    start: (clipped ? earliest : start).toISOString(), end: end.toISOString(), format,
  });
  return { href: `/api/v1/observations/export?${params}`, clipped };
}
