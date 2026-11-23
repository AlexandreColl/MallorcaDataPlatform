// The fault-injection benchmark of the anomaly detectors (`make evaluate`, /anomalies/benchmark) as one row per
// source and detector: the share of each kind of fault it caught, and the precision of its flags.

import type { DetectorBenchmark } from "../api";

export const FAULTS = ["spike", "drift", "frozen", "shift"] as const;
export type Fault = (typeof FAULTS)[number];

/** The model first, the easy case, then the real stations; a source added later goes after them. */
const SOURCES = ["open_meteo", "socib", "eea_air_quality"];
const DETECTORS = ["robust_zscore", "seasonal_residual", "isolation_forest", "vote"];

export interface BenchmarkRow {
  source: string;
  detector: DetectorBenchmark["detector"];
  /** Share of the injected faults of each kind with some value flagged; null when none was injected. */
  caught: Record<Fault, number | null>;
  precision: number | null;
  falseAlarms: number | null;
}

function rank(list: string[], value: string): number {
  const i = list.indexOf(value);
  return i < 0 ? list.length : i;
}

export function benchmarkRows(rows: DetectorBenchmark[]): BenchmarkRow[] {
  const byKey = new Map<string, BenchmarkRow>();
  for (const r of rows) {
    const key = `${r.source}|${r.detector}`;
    let row = byKey.get(key);
    if (!row) {
      row = {
        source: r.source, detector: r.detector, precision: null, falseAlarms: null,
        caught: { spike: null, drift: null, frozen: null, shift: null },
      };
      byKey.set(key, row);
    }
    if (r.fault === "all") {
      row.precision = r.precision;
      row.falseAlarms = r.false_alarms;
    } else {
      row.caught[r.fault] = r.events > 0 ? r.events_detected / r.events : null;
    }
  }
  return [...byKey.values()].sort(
    (a, b) =>
      rank(SOURCES, a.source) - rank(SOURCES, b.source) ||
      a.source.localeCompare(b.source) ||
      rank(DETECTORS, a.detector) - rank(DETECTORS, b.detector),
  );
}

/** The days the benchmark covered, from the newest run among the sources. */
export function benchmarkWindow(rows: DetectorBenchmark[]): { from: string; to: string } | null {
  if (rows.length === 0) return null;
  const newest = rows.reduce((a, b) => (b.evaluated_at > a.evaluated_at ? b : a));
  return { from: newest.window_start, to: newest.window_end };
}
