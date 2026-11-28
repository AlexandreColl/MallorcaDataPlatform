import { describe, expect, it } from "vitest";

import type { MunicipalUnemployment, ResourcesMonth, UnemploymentSeasonality } from "../api";
import { latestByMunicipality, latestSeasonality, unemploymentCorrelations, unemploymentLine } from "./unemployment";

const SEASON = [0.3, 0.35, 0.5, 0.8, 1.2, 1.6, 1.9, 2.0, 1.6, 1.0, 0.4, 0.3]; // millions of passengers, Jan-Dec

function month(year: number, m: number, airport: number, unemployed: number | null): ResourcesMonth {
  return {
    month: `${year}-${String(m).padStart(2, "0")}-01`,
    airport_passengers: airport,
    international_tourists: airport / 2,
    cruise_passengers: null,
    unemployed,
  } as ResourcesMonth;
}

describe("unemploymentCorrelations", () => {
  it("is strongly negative through the season and says what is left without it", () => {
    // Three years: unemployment mirrors the season, and a busier year (the second) has a little less of it.
    const rows = [0, 1, 2].flatMap((y) =>
      SEASON.map((s, i) => month(2023 + y, i + 1, s * 1e6 * (y === 1 ? 1.1 : 1), 30000 - 6000 * s - (y === 1 ? 800 : 0))),
    );

    const r = unemploymentCorrelations(rows);

    expect(r.airport.raw?.r).toBeLessThan(-0.95);
    expect(r.airport.raw?.n).toBe(36);
    expect(r.airport.deseasonalized?.r).toBeLessThan(-0.8); // more passengers than usual, fewer unemployed than usual
    expect(r.cruises.raw).toBeNull(); // no cruise figures at all
  });
});

describe("latestSeasonality", () => {
  it("names the latest year with a ratio", () => {
    const rows = [
      { area: "mallorca", year: 2025, winter_summer_ratio: 1.142 },
      { area: "mallorca", year: 2026, winter_summer_ratio: null },
    ] as UnemploymentSeasonality[];

    expect(latestSeasonality(rows)).toBe("2025: 1,14");
    expect(latestSeasonality([])).toBeNull();
  });
});

describe("unemploymentLine", () => {
  const row = (fields: Partial<MunicipalUnemployment>) =>
    ({ municipality: "07042", month: "2026-10-01", is_suppressed: false, ...fields }) as MunicipalUnemployment;

  it("shows the unemployed and the ratio of the latest month", () => {
    const rows = [
      row({ month: "2026-09-01", unemployed: 200 }),
      row({ unemployed: 243, unemployed_per_1000_inhabitants: 13.6 }),
    ];
    const latest = latestByMunicipality(rows).get("07042");

    expect(unemploymentLine(latest)).toBe("243 en paro registrado en octubre de 2026 · 13,6 por 1.000 hab.");
  });

  it("never shows a suppressed total as 5", () => {
    const escorca = row({ municipality: "07019", is_suppressed: true, unemployed: null });

    expect(unemploymentLine(escorca)).toBe("Menos de 5 en paro registrado en octubre de 2026");
    expect(unemploymentLine(undefined)).toBe("Sin dato de paro registrado");
  });
});
