import { describe, expect, it } from "vitest";

import { blur, contourLevels, contours } from "./contours";

describe("contourLevels", () => {
  it("takes every whole degree, or every two over a wide range", () => {
    expect(contourLevels(14.2, 17.8)).toEqual([15, 16, 17]);
    expect(contourLevels(0.5, 20)).toEqual([2, 4, 6, 8, 10, 12, 14, 16, 18, 20]);
    expect(contourLevels(5, 5)).toEqual([]);
  });
});

describe("contours", () => {
  // Rises by 1 from west to east: 10, 11, 12 on each of three rows.
  const ramp = [10, 11, 12, 10, 11, 12, 10, 11, 12];

  it("draws a north-south line where a west-east ramp crosses the level", () => {
    const [line] = contours(ramp, 3, 3, [11.5]);
    expect(line?.segments).toEqual([
      [[1.5, 0], [1.5, 1]],
      [[1.5, 1], [1.5, 2]],
    ]);
  });

  it("draws nothing outside the mask or for a level out of range", () => {
    expect(contours(ramp, 3, 3, [11.5], [1, 1, 0, 1, 1, 0, 1, 1, 0])[0]?.segments).toEqual([]);
    expect(contours(ramp, 3, 3, [20])[0]?.segments).toEqual([]);
  });

  it("splits a saddle into two segments", () => {
    const [saddle] = contours([0, 1, 1, 0], 2, 2, [0.5]);
    expect(saddle?.segments).toHaveLength(2);
  });
});

describe("blur", () => {
  it("keeps a flat grid flat and spreads a spike over its neighbours", () => {
    expect([...blur([5, 5, 5, 5], 2, 2, 1)]).toEqual([5, 5, 5, 5]);
    const spread = blur([0, 0, 0, 0, 9, 0, 0, 0, 0], 3, 3, 1);
    expect(spread[4]).toBeLessThan(9);
    expect(spread[0]).toBeGreaterThan(0);
    expect([...spread].reduce((a, b) => a + b, 0)).toBeGreaterThan(0);
  });

  it("ignores missing values", () => {
    expect([...blur([1, Number.NaN, 3, Number.NaN], 2, 2, 1)].every((v) => v === 2)).toBe(true);
  });
});
