import { describe, expect, it } from "vitest";

import { grid, idw, imageHeight, inside, ISLAND_BOUNDS, temperatureColor, temperatureRgb } from "./interpolate";

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

describe("grid", () => {
  const bounds = { west: 2, south: 39, east: 3, north: 40 };

  it("has one value per pixel, the station's own value everywhere with a single station", () => {
    const values = grid([{ lon: 2.9, lat: 39.6, value: 18 }], bounds, 20, 10);
    expect(values).toHaveLength(200);
    expect([...values].every((v) => Math.abs(v - 18) < 1e-9)).toBe(true);
  });

  it("runs from north to south and west to east", () => {
    const north = grid([{ lon: 2.5, lat: 40, value: 10 }, { lon: 2.5, lat: 39, value: 20 }], bounds, 4, 4);
    expect(north[0]).toBeLessThan(north[12] as number); // first row (north) cooler than the last
    const west = grid([{ lon: 2, lat: 39.5, value: 10 }, { lon: 3, lat: 39.5, value: 20 }], bounds, 4, 4);
    expect(west[0]).toBeLessThan(west[3] as number);
  });

  it("makes square pixels: the island image is about 0.8 times as tall as it is wide", () => {
    expect(imageHeight(ISLAND_BOUNDS, 600) / 600).toBeCloseTo(0.8, 1);
  });

  it("is empty (not a number) without stations", () => {
    expect(Number.isNaN(grid([], bounds, 2, 2)[0])).toBe(true);
  });
});

describe("temperatureColor", () => {
  it("goes from blue at the minimum to red at the maximum", () => {
    expect(temperatureColor(10, 10, 20)).toBe("rgb(44, 123, 182)");
    expect(temperatureColor(20, 10, 20)).toBe("rgb(215, 25, 28)");
    expect(temperatureColor(15, 10, 20)).toBe("rgb(255, 255, 191)");
    expect(temperatureRgb(20, 10, 20)).toEqual([215, 25, 28]);
  });
});
