// The state of a source as one word, from its health in gold.source_health.

import type { Source } from "../api";

export type SourceState = "ok" | "failed" | "late" | "inactive";

/** The DAG runs every day: a source without a successful run in 36 h is late (the alert in Grafana uses the same). */
const LATE_AFTER_HOURS = 36;
/** A source that has not run in a week is no longer scheduled. */
const INACTIVE_AFTER_DAYS = 7;
/** A source whose newest value is over a year old is a closed history (GOIB air quality ends in 2021). */
const HISTORY_AFTER_DAYS = 365;

const HOUR = 3_600_000;

export function sourceState(source: Source, now: Date = new Date()): SourceState {
  const hoursSince = (iso: string | null) => (iso ? (now.getTime() - Date.parse(iso)) / HOUR : Infinity);
  if (hoursSince(source.last_run_at) > INACTIVE_AFTER_DAYS * 24) return "inactive";
  if ((source.data_age_hours ?? 0) > HISTORY_AFTER_DAYS * 24) return "inactive";
  if (source.last_status === "failed") return "failed";
  if (hoursSince(source.last_success_at) > LATE_AFTER_HOURS) return "late";
  return "ok";
}

export const STATE_LABELS: Record<SourceState, string> = {
  ok: "Al día",
  failed: "Falló",
  late: "Atrasada",
  inactive: "Histórico",
};
