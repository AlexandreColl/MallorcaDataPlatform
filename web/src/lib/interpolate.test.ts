import { describe, expect, it } from "vitest";

import { idw, inside, surface, temperatureColor } from "./interpolate";

describe("inside", () => {
  it("knows Palma and Inca are on the island and Cabrera and Menorca are not", () => {
    expect(inside(2.65, 39.58)).toBe(true); // Palma
    expect(inside(2.91, 39.72)).toBe(true); // Inca
    expect(inside(2.93, 39.15)).toBe(false); // Cabrera
    expect(inside(4.1, 39.95)).toBe(false); // Menorca
  });
});

describe("idw", () => {
  const samples = [
    { lon: 2.6, lat: 39.6, value: 10 },
    { lon: 3.2, lat: 39.6, value: 20 },
  ];

  it("is the station's own value on top of it and the mean halfway", () => {
    expect(idw(samples, 2.6, 39.6)).toBe(10);
    expect(idw(samples, 2.9, 39.6)).toBeCloseTo(15);
  });

  it("leans to the nearest station", () => {
    expect(idw(samples, 2.7, 39.6)).toBeLessThan(13);
  });
});

describe("surface", () => {
  it("covers the island with cells and none in the sea", () => {
    const cells = surface([{ lon: 2.9, lat: 39.6, value: 18 }], 0.05);
    expect(cells.length).toBeGreaterThan(100);
    expect(cells.every((c) => Math.abs(c.value - 18) < 1e-9)).toBe(true);
  });
});

describe("temperatureColor", () => {
  it("goes from blue at the minimum to red at the maximum", () => {
    expect(temperatureColor(10, 10, 20)).toBe("rgb(44, 123, 182)");
    expect(temperatureColor(20, 10, 20)).toBe("rgb(215, 25, 28)");
    expect(temperatureColor(15, 10, 20)).toBe("rgb(255, 255, 191)");
  });
});
