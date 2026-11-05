import { describe, expect, it } from "vitest";

import type { ClimateMonth, ResourcesMonth } from "../api";
import { buildKpi, RAIN_SPEC, RESOURCE_SPECS } from "./kpis";

function month(m: string, fields: Partial<ResourcesMonth>): ResourcesMonth {
  return {
    month: m, international_tourists: null, tourists_anomaly: null, airport_passengers: null,
    hotel_bed_occupancy_pct: null, electricity_demand_gwh: null, electricity_demand_anomaly: null,
    reserves_pct: null, reserves_anomaly_pts: null, rain_mm: null, rain_anomaly: null, temperature_mean_c: null,
    temperature_anomaly_c: null, ...fields,
  };
}

const spec = (id: string) => RESOURCE_SPECS.find((s) => s.id === id)!;

describe("buildKpi", () => {
  it("takes the latest month with a value, not the latest month", () => {
    const rows = [
      month("2026-08-01", { international_tourists: 2_596_458, tourists_anomaly: 0.249 }),
      month("2026-09-01", { electricity_demand_gwh: 640.7 }), // tourism is published months later
    ];

    const kpi = buildKpi(spec("tourists"), rows)!;

    expect(kpi.month).toBe("agosto de 2026");
    expect(kpi.value).toBe("2,6 M");
    expect(kpi.deviation).toBe("+25 % sobre lo normal");
    expect(kpi.tone).toBe("neutral"); // more tourists is neither good nor bad news
  });

  it("marks low water reserves and a warm month as bad news", () => {
    const rows = [month("2026-08-01", { reserves_pct: 38, reserves_anomaly_pts: -11.5, temperature_mean_c: 28.54, temperature_anomaly_c: 2.07 })];

    expect(buildKpi(spec("reserves"), rows)).toMatchObject({ value: "38", tone: "bad", deviation: "−11,5 puntos sobre lo normal" });
    expect(buildKpi(spec("temperature"), rows)).toMatchObject({ value: "28,5", tone: "bad" });
  });

  it("compares the rain of the hydrological year with its mean at the same point", () => {
    const rows: ClimateMonth[] = [
      {
        month: "2026-10-01", hydrological_year: 2027, rain_mm: 40, rain_hydrological_year_mm: 120,
        rain_hydrological_year_mean_mm: 100, temperature_mean_c: 20, temperature_anomaly_c: 0.5, hot_days: 0,
      },
    ];

    expect(buildKpi(RAIN_SPEC, rows)).toMatchObject({ value: "120", tone: "good", deviation: "+20 % sobre lo normal" });
  });

  it("keeps the months in order and at most 36 of them", () => {
    const rows = Array.from({ length: 40 }, (_, i) => {
      const date = new Date(Date.UTC(2023, i, 1)).toISOString().slice(0, 10);
      return month(date, { reserves_pct: i });
    }).reverse();

    const kpi = buildKpi(spec("reserves"), rows)!;

    expect(kpi.history).toHaveLength(36);
    expect(kpi.history.at(-1)).toEqual({ month: "2026-04-01", value: 39 });
  });

  it("is null for a series without any value", () => {
    expect(buildKpi(spec("electricity"), [month("2026-08-01", {})])).toBeNull();
  });
});
