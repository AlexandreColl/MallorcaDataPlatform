import { describe, expect, it } from "vitest";

import {
  binColor,
  busiestDay,
  change,
  DAYS_OF_YEAR,
  islandTotals,
  municipalityOf,
  pressureByYear,
  serviceByMunicipality,
} from "./population";

const square = (x: number, y: number, size = 1): [number, number][] => [
  [x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y],
]; // prettier-ignore

const PLACES = [
  { municipality: "A", lat: 0.5, lon: 0.5, polygon: [square(0, 0)] },
  // Two rings, like Palma and the Cabrera archipelago.
  { municipality: "B", lat: 0.5, lon: 1.5, polygon: [square(1, 0), square(5, 5, 0.5)] },
];

describe("municipalityOf", () => {
  it("finds the boundary that contains the stop, in any of its rings", () => {
    expect(municipalityOf({ lat: 0.2, lon: 0.2 }, PLACES)).toBe("A");
    expect(municipalityOf({ lat: 5.2, lon: 5.2 }, PLACES)).toBe("B");
  });

  it("falls back to the nearest centre for a stop just outside every boundary", () => {
    expect(municipalityOf({ lat: -0.01, lon: 1.6 }, PLACES)).toBe("B");
  });
});

describe("serviceByMunicipality", () => {
  it("counts the stops and adds up their departures", () => {
    const stops = [
      { lat: 0.2, lon: 0.2, departures: 10 },
      { lat: 0.8, lon: 0.3, departures: null },
      { lat: 0.4, lon: 1.4, departures: 5 },
    ];

    expect(Object.fromEntries(serviceByMunicipality(stops, PLACES))).toEqual({
      A: { stops: 2, departures: 10 },
      B: { stops: 1, departures: 5 },
    });
  });
});

describe("islandTotals", () => {
  it("adds up the municipalities and leaves out a year that is not complete", () => {
    const rows = [
      { municipality: "A", year: 2024, population: 100 },
      { municipality: "B", year: 2024, population: 50 },
      { municipality: "A", year: 2025, population: 110 },
      { municipality: "B", year: 2025, population: null },
    ];

    expect(islandTotals(rows)).toEqual([{ year: 2024, population: 150 }]);
  });
});

describe("change and binColor", () => {
  it("compare and colour values, and handle the missing ones", () => {
    expect(change(110, 100)).toBeCloseTo(0.1);
    expect(change(110, null)).toBeNull();
    expect(change(110, 0)).toBeNull();
    expect(binColor(5, [10, 100], ["a", "b", "c"])).toBe("a");
    expect(binColor(50, [10, 100], ["a", "b", "c"])).toBe("b");
    expect(binColor(500, [10, 100], ["a", "b", "c"])).toBe("c");
    expect(binColor(null, [10], ["a", "b"])).toBe("#9ca3af");
  });
});

describe("pressureByYear", () => {
  const days = [
    { local_date: "2025-08-11", people_present: 1_490_000 },
    { local_date: "2026-08-11", people_present: 1_517_631 },
    { local_date: "2024-02-29", people_present: 900_000 },
  ];

  it("lays each year over the days of a year, newest first", () => {
    const years = pressureByYear(days);
    expect(years.map((y) => y.year)).toEqual([2026, 2025, 2024]);
    const august11 = DAYS_OF_YEAR.indexOf("08-11");
    expect(years[0]?.values[august11]).toBe(1_517_631);
    expect(years[1]?.values[august11]).toBe(1_490_000);
    expect(years[2]?.values[DAYS_OF_YEAR.indexOf("02-29")]).toBe(900_000);
    expect(years[0]?.values.filter((v) => v !== null)).toHaveLength(1);
  });

  it("has 366 days and finds the busiest one", () => {
    expect(DAYS_OF_YEAR).toHaveLength(366);
    expect(busiestDay(days)?.local_date).toBe("2026-08-11");
    expect(busiestDay([])).toBeNull();
  });
});
