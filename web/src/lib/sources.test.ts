import { describe, expect, it } from "vitest";

import type { Source } from "../api";
import { sourceState } from "./sources";

const NOW = new Date("2026-11-05T12:00:00Z");

function source(fields: Partial<Source>): Source {
  return {
    source: "aemet", label: "AEMET", kind: "observation", last_status: "success",
    last_run_at: "2026-11-05T06:00:00Z", last_success_at: "2026-11-05T06:00:00Z", last_loaded_day: null,
    runs_7d: 7, failure_rate_7d: 0, latest_observation_ts: null, data_age_hours: null, observations: 1, ...fields,
  };
}

describe("sourceState", () => {
  it("is ok after a recent successful run", () => {
    expect(sourceState(source({}), NOW)).toBe("ok");
  });

  it("is failed when the last run failed", () => {
    expect(sourceState(source({ last_status: "failed" }), NOW)).toBe("failed");
  });

  it("is late without a successful run in 36 h", () => {
    expect(sourceState(source({ last_success_at: "2026-11-03T12:00:00Z" }), NOW)).toBe("late");
  });

  it("is inactive when it has not run for a week", () => {
    expect(sourceState(source({ last_run_at: "2026-10-01T00:00:00Z", last_status: "failed" }), NOW)).toBe("inactive");
  });

  it("is inactive when its newest value is years old (a closed history)", () => {
    expect(sourceState(source({ data_age_hours: 5.4 * 365 * 24 }), NOW)).toBe("inactive");
  });

  it("stays current with a yearly value from almost two years ago (the municipal register)", () => {
    expect(sourceState(source({ data_age_hours: 22 * 30 * 24 }), NOW)).toBe("ok");
  });
});
