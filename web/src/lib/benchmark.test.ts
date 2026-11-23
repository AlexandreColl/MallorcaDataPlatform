import { describe, expect, it } from "vitest";

import type { DetectorBenchmark } from "../api";
import { benchmarkRows, benchmarkWindow } from "./benchmark";

function row(source: string, detector: DetectorBenchmark["detector"], fault: DetectorBenchmark["fault"], events: number,
  detected: number, extra: Partial<DetectorBenchmark> = {}): DetectorBenchmark {
  return {
    source, detector, fault, events, events_detected: detected, event_recall: null, recall: null, precision: null,
    false_alarms: null, window_start: "2026-10-23", window_end: "2026-11-22", evaluated_at: "2026-11-22T10:00:00Z",
    ...extra,
  };
}

describe("benchmarkRows", () => {
  it("gives one row per source and detector, with the share caught of each fault and the precision", () => {
    const rows = benchmarkRows([
      row("socib", "vote", "spike", 72, 69),
      row("socib", "vote", "shift", 24, 7),
      row("socib", "vote", "all", 144, 104, { precision: 0.74, false_alarms: 71 }),
    ]);

    expect(rows).toEqual([{
      source: "socib", detector: "vote", precision: 0.74, falseAlarms: 71,
      caught: { spike: 69 / 72, drift: null, frozen: null, shift: 7 / 24 },
    }]);
  });

  it("puts the model first, then the stations, and the detectors in their order", () => {
    const rows = benchmarkRows([
      row("eea_air_quality", "vote", "all", 1, 1),
      row("socib", "robust_zscore", "all", 1, 1),
      row("open_meteo", "vote", "all", 1, 1),
      row("open_meteo", "robust_zscore", "all", 1, 1),
      row("new_source", "vote", "all", 1, 1),
    ]);

    expect(rows.map((r) => `${r.source}:${r.detector}`)).toEqual([
      "open_meteo:robust_zscore", "open_meteo:vote", "socib:robust_zscore", "eea_air_quality:vote", "new_source:vote",
    ]);
  });

  it("leaves a fault that was not injected empty instead of 0 %", () => {
    expect(benchmarkRows([row("socib", "vote", "frozen", 0, 0)])[0]?.caught.frozen).toBeNull();
  });
});

describe("benchmarkWindow", () => {
  it("is the window of the newest run, or nothing before the first one", () => {
    const older = row("socib", "vote", "all", 1, 1, { window_end: "2026-10-01", evaluated_at: "2026-10-01T00:00:00Z" });

    expect(benchmarkWindow([older, row("open_meteo", "vote", "all", 1, 1)])).toEqual({ from: "2026-10-23", to: "2026-11-22" });
    expect(benchmarkWindow([])).toBeNull();
  });
});
