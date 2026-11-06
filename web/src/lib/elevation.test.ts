import { describe, expect, it } from "vitest";

import { terrariumHeight, tileRange, worldPixel } from "./elevation";
import { ISLAND_BOUNDS } from "./interpolate";

describe("terrariumHeight", () => {
  it("decodes the sea level and a height", () => {
    expect(terrariumHeight(128, 0, 0)).toBe(0);
    expect(terrariumHeight(131, 233, 128)).toBeCloseTo(1001.5);
  });
});

describe("worldPixel", () => {
  it("puts longitude and latitude 0 in the middle of the world", () => {
    expect(worldPixel(0, 0, 0)).toEqual([128, 128]);
    expect(worldPixel(-180, 0, 1)[0]).toBe(0);
  });
});

describe("tileRange", () => {
  it("covers Mallorca with a few tiles at zoom 10", () => {
    const range = tileRange(ISLAND_BOUNDS, 10);
    expect(range).toMatchObject({ x: 518, columns: 4 });
    expect(range.columns * range.rows).toBeLessThanOrEqual(16);
  });
});
