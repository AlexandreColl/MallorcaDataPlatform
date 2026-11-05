import { describe, expect, it } from "vitest";

import { deseasonalize, movingAverage, pearson, strength } from "./stats";

describe("movingAverage", () => {
  it("cancels a yearly cycle and keeps the trend", () => {
    const cycle = [0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1];
    const values = [...cycle, ...cycle.map((v) => v + 12)]; // the same year, 12 higher
    const trend = movingAverage(values);

    expect(trend.slice(0, 11).every((v) => v === null)).toBe(true);
    expect(trend[11]).toBeCloseTo(3);
    expect(trend[23]).toBeCloseTo(15);
  });

  it("is null where a month in the window is missing", () => {
    const values = Array.from({ length: 14 }, (_, i) => (i === 12 ? null : i));
    expect(movingAverage(values).slice(11)).toEqual([5.5, null, null]);
  });
});

describe("pearson", () => {
  it("is 1 and -1 for perfectly related series and skips missing pairs", () => {
    const xs = [1, 2, 3, 4, 5, 6, 7, null];
    expect(pearson(xs, [2, 4, 6, 8, 10, 12, 14, 99])).toEqual({ r: 1, n: 7 });
    expect(pearson(xs, [7, 6, 5, 4, 3, 2, 1, 0])?.r).toBeCloseTo(-1);
  });

  it("is null with too few pairs or a flat series", () => {
    expect(pearson([1, 2, 3], [3, 2, 1])).toBeNull();
    expect(pearson([1, 2, 3, 4, 5, 6], [5, 5, 5, 5, 5, 5])).toBeNull();
  });
});

describe("strength", () => {
  it("reads the size and the direction of r", () => {
    expect(strength(-0.72)).toBe("Relación fuerte inversa");
    expect(strength(0.45)).toBe("Relación moderada directa");
    expect(strength(0.1)).toBe("Relación débil");
  });
});

describe("deseasonalize", () => {
  it("takes the mean of each calendar month out", () => {
    const months = ["2024-07-01", "2024-08-01", "2025-07-01", "2025-08-01"];
    expect(deseasonalize(months, [10, 20, 14, null])).toEqual([-2, 0, 2, null]);
  });

  it("removes a correlation that comes only from the season", () => {
    const months = Array.from({ length: 36 }, (_, i) => new Date(Date.UTC(2023, i, 1)).toISOString().slice(0, 10));
    const season = months.map((m) => Math.sin((Number(m.slice(5, 7)) / 12) * 2 * Math.PI));
    const noise = months.map((_, i) => ((i * 7919) % 13) / 13 - 0.5);
    const tourists = season.map((s, i) => 10 * s + (noise[i] as number));
    const water = season.map((s, i) => -10 * s + (noise[(i + 5) % 36] as number));

    expect(pearson(tourists, water)?.r).toBeLessThan(-0.9);
    expect(Math.abs(pearson(deseasonalize(months, tourists), deseasonalize(months, water))?.r ?? 1)).toBeLessThan(0.5);
  });
});
