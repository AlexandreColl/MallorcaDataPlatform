import { describe, expect, it } from "vitest";

import type { Series, SeriesDay } from "../api";
import { axisDate, entitiesOf, longest, metricLabel, metricsOf, rangeStart, summarize, unitLabel } from "./series";

const series = (entity: string, metric: string, days: number, name: string | null = null): Series => ({
  source: "aemet", entity, name, metric, unit: "degC", first_day: "2020-01-01", last_day: "2026-11-03", days,
});

const day = (local_date: string, min: number | null, avg: number | null, max: number | null, extra: Partial<SeriesDay> = {}) => ({
  local_date, samples: 24, valid: 24, suspect: 0, min_value: min, avg_value: avg, max_value: max, completeness: 1,
  anomalies: 0, ...extra,
});

describe("labels", () => {
  it("names the metrics and units in Spanish and keeps unknown ones as they are", () => {
    expect(metricLabel("temperature_2m_mean")).toBe("Temperatura media");
    expect(metricLabel("new_metric")).toBe("new metric");
    expect(unitLabel("ug/m3")).toBe("µg/m³");
    expect(unitLabel("MWh")).toBe("MWh");
    expect(unitLabel(null)).toBe("");
  });
});

describe("catalog", () => {
  const catalog = [
    series("B228", "temperature_2m_mean", 2000, "Palma, Puerto"),
    series("B013X", "temperature_2m_mean", 3000, "Escorca, Lluc"),
    series("B228", "precipitation_sum", 2500, "Palma, Puerto"),
  ];

  it("lists the metrics by name and the entities of a metric by name", () => {
    expect(metricsOf(catalog)).toEqual(["precipitation_sum", "temperature_2m_mean"]);
    expect(entitiesOf(catalog, "temperature_2m_mean").map((s) => s.entity)).toEqual(["B013X", "B228"]);
  });

  it("opens the longest series first", () => {
    expect(longest(catalog)?.entity).toBe("B013X");
    expect(longest([])).toBeUndefined();
  });
});

describe("rangeStart", () => {
  const s = series("B228", "temperature_2m_mean", 2000);

  it("ends the range on the series' last day and never starts before its first", () => {
    expect(rangeStart(s, "month")).toBe("2026-10-05");
    expect(rangeStart(s, "year")).toBe("2025-11-04");
    expect(rangeStart(s, "five")).toBe("2021-11-05");
    expect(rangeStart({ ...s, first_day: "2026-06-01" }, "five")).toBe("2026-06-01");
    expect(rangeStart(s, "all")).toBe("2020-01-01");
  });
});

describe("summarize", () => {
  it("takes the lowest minimum, the mean of the means and the highest maximum, and adds up the flags", () => {
    const summary = summarize([
      day("2026-11-01", 10, 14, 18),
      day("2026-11-02", 12, 16, 21, { valid: 12, suspect: 2, anomalies: 3 }),
      day("2026-11-03", null, null, null, { valid: 0 }),
    ]);

    expect(summary).toEqual({ days: 3, completeness: 0.5, suspect: 2, anomalies: 3, min: 10, mean: 15, max: 21 });
  });

  it("has no figures without days", () => {
    expect(summarize([])).toEqual({ days: 0, completeness: null, suspect: 0, anomalies: 0, min: null, mean: null, max: null });
  });
});

describe("axisDate", () => {
  const ms = Date.parse("2024-03-15T00:00:00Z");

  it("labels days for a few months, months for a few years and years beyond", () => {
    expect(axisDate(ms, 30)).toBe("15 mar");
    expect(axisDate(ms, 365)).toBe("mar 24");
    expect(axisDate(ms, 5 * 365)).toBe("2024");
  });
});
