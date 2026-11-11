import { describe, expect, it } from "vitest";

import type { Source } from "../api";
import { slaText, sourceState } from "./sources";

const NOW = new Date("2026-11-05T12:00:00Z");

function source(fields: Partial<Source> = {}, sla: Partial<Source["sla"]> = {}, lifecycle: "active" | "history" = "active"): Source {
  return {
    source: "aemet", label: "AEMET", kind: "observation", last_status: "success",
    last_run_at: "2026-11-05T06:00:00Z", last_success_at: "2026-11-05T06:00:00Z", last_loaded_day: null,
    runs_7d: 7, failed_7d: 0, unavailable_7d: 0, failure_rate_7d: 0, latest_observation_ts: null, data_age_hours: null,
    observations: 1,
    governance: {
      domain: "weather", owner: "AEMET", license: "CC BY 4.0", terms_url: "https://www.aemet.es", access: "api_key",
      personal_data: false, classification: "public", lifecycle,
    },
    sla: { data_age_hours: 120, success_rate: 0.9, age_met: true, success_met: true, met: true, ...sla },
    ...fields,
  };
}

describe("sourceState", () => {
  it("is ok after a recent successful run within its SLA", () => {
    expect(sourceState(source(), NOW)).toBe("ok");
  });

  it("is failed when the last run failed", () => {
    expect(sourceState(source({ last_status: "failed" }), NOW)).toBe("failed");
  });

  it("is down, not failed, when its last run found the source down", () => {
    expect(sourceState(source({ last_status: "unavailable" }), NOW)).toBe("down");
  });

  it("is late without a successful run in 36 h", () => {
    expect(sourceState(source({ last_success_at: "2026-11-03T12:00:00Z" }), NOW)).toBe("late");
  });

  it("is out of its SLA when it loads but its data is too old", () => {
    expect(sourceState(source({}, { age_met: false, met: false }), NOW)).toBe("breach");
  });

  it("is ok when the SLA cannot be judged yet", () => {
    expect(sourceState(source({}, { age_met: null, success_met: null, met: null }), NOW)).toBe("ok");
  });

  it("is inactive when it has not run for a week", () => {
    expect(sourceState(source({ last_run_at: "2026-10-01T00:00:00Z", last_status: "failed" }), NOW)).toBe("inactive");
  });

  it("is inactive when the catalogue marks it as a closed history", () => {
    expect(sourceState(source({ data_age_hours: 5.4 * 365 * 24 }, {}, "history"), NOW)).toBe("inactive");
  });
});

describe("slaText", () => {
  it("gives the age in hours or days and the share of good runs", () => {
    expect(slaText(source({}, { data_age_hours: 48 }))).toBe("< 48 h · 90 % ok");
    expect(slaText(source({}, { data_age_hours: 2400, success_rate: 0.8 }))).toBe("< 100 días · 80 % ok");
  });

  it("leaves out the age when the SLA sets none", () => {
    expect(slaText(source({}, { data_age_hours: null }))).toBe("90 % ok");
  });
});
