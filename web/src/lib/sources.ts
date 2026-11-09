// The state of a source as one word, from its health and its SLA in gold.source_health.

import type { Source } from "../api";

export type SourceState = "ok" | "failed" | "late" | "breach" | "inactive";

/** The DAG runs every day: a source without a successful run in 36 h is late (the alert in Grafana uses the same). */
const LATE_AFTER_HOURS = 36;
/** A source that has not run in a week is no longer scheduled. */
const INACTIVE_AFTER_DAYS = 7;

const HOUR = 3_600_000;

/**
 * Inactive (a closed history in the catalogue, or not run in a week), failed (its last run), late (no successful
 * run in 36 h), breach (loads fine but misses the SLA agreed in its catalogue entry) or ok.
 */
export function sourceState(source: Source, now: Date = new Date()): SourceState {
  const hoursSince = (iso: string | null) => (iso ? (now.getTime() - Date.parse(iso)) / HOUR : Infinity);
  if (source.governance.lifecycle === "history") return "inactive";
  if (hoursSince(source.last_run_at) > INACTIVE_AFTER_DAYS * 24) return "inactive";
  if (source.last_status === "failed") return "failed";
  if (hoursSince(source.last_success_at) > LATE_AFTER_HOURS) return "late";
  if (source.sla.met === false) return "breach";
  return "ok";
}

export const STATE_LABELS: Record<SourceState, string> = {
  ok: "Al día",
  failed: "Falló",
  late: "Atrasada",
  breach: "Fuera de SLA",
  inactive: "Histórico",
};

/** The SLA of a source, short: the maximum age of its newest value and the minimum share of successful runs. */
export function slaText(source: Source): string {
  const parts: string[] = [];
  const hours = source.sla.data_age_hours;
  if (hours !== null) parts.push(hours < 72 ? `< ${hours} h` : `< ${Math.round(hours / 24)} días`);
  parts.push(`${Math.round(source.sla.success_rate * 100)} % ok`);
  return parts.join(" · ");
}

export const ACCESS_LABELS: Record<Source["governance"]["access"], string> = {
  open: "Abierto",
  api_key: "Clave gratuita",
};
