// Contour lines of a grid of values (isotherms) by marching squares: every square of four neighbouring pixel
// centres that a level crosses gets a segment between the points where its sides cross it.

/** A segment of a contour line, in pixel coordinates (x to the east, y to the south, centres on whole numbers). */
export type Segment = [[number, number], [number, number]];

export interface Contour {
  level: number;
  segments: Segment[];
}

/** Whole levels between the minimum and the maximum: every 1 unit, or every 2 when there would be more than 12. */
export function contourLevels(min: number, max: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
  const step = max - min > 12 ? 2 : 1;
  const levels: number[] = [];
  for (let level = Math.ceil(min / step) * step; level <= max; level += step) levels.push(level);
  return levels;
}

/**
 * The segments of each level over a width × height grid (row by row). With a mask, only the squares whose four
 * corners are in it (e.g. on land) are drawn.
 */
export function contours(
  values: ArrayLike<number>,
  width: number,
  height: number,
  levels: number[],
  mask?: ArrayLike<number>,
): Contour[] {
  return levels.map((level) => {
    const segments: Segment[] = [];
    for (let y = 0; y < height - 1; y++) {
      for (let x = 0; x < width - 1; x++) {
        const corners = [y * width + x, y * width + x + 1, (y + 1) * width + x + 1, (y + 1) * width + x];
        if (mask && corners.some((i) => !mask[i])) continue;
        const [a, b, c, d] = corners.map((i) => values[i] as number) as [number, number, number, number];
        if ([a, b, c, d].some((v) => !Number.isFinite(v))) continue;
        // Where the level crosses each side, in the order top, right, bottom, left (null: not crossed).
        const cross = (v0: number, v1: number, p0: [number, number], p1: [number, number]): [number, number] | null => {
          if (v0 >= level === v1 >= level) return null;
          const t = (level - v0) / (v1 - v0);
          return [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
        };
        const points = [
          cross(a, b, [x, y], [x + 1, y]),
          cross(b, c, [x + 1, y], [x + 1, y + 1]),
          cross(d, c, [x, y + 1], [x + 1, y + 1]),
          cross(a, d, [x, y], [x, y + 1]),
        ];
        const hits = points.filter((p): p is [number, number] => p !== null);
        if (hits.length === 2) segments.push([hits[0] as [number, number], hits[1] as [number, number]]);
        else if (hits.length === 4) {
          // A saddle: the mean of the square decides which corners are joined.
          const [top, right, bottom, left] = points as [number, number][];
          const centreHigh = (a + b + c + d) / 4 >= level;
          if (centreHigh === a >= level) segments.push([top as [number, number], right as [number, number]], [bottom as [number, number], left as [number, number]]);
          else segments.push([top as [number, number], left as [number, number]], [bottom as [number, number], right as [number, number]]);
        }
      }
    }
    return { level, segments };
  });
}

/**
 * A box blur of `radius` pixels over a width × height grid, done twice (close to a Gaussian). Missing values
 * (not a number) are left out of the means. Contour lines drawn on it skip the small bumps of the relief.
 */
export function blur(values: ArrayLike<number>, width: number, height: number, radius: number): Float64Array {
  let current = Float64Array.from(values);
  const pass = (source: Float64Array, horizontal: boolean) => {
    const out = new Float64Array(source.length);
    const [outer, inner] = horizontal ? [height, width] : [width, height];
    for (let o = 0; o < outer; o++) {
      for (let i = 0; i < inner; i++) {
        let [sum, count] = [0, 0];
        for (let k = Math.max(0, i - radius); k <= Math.min(inner - 1, i + radius); k++) {
          const v = source[horizontal ? o * width + k : k * width + o] as number;
          if (Number.isFinite(v)) [sum, count] = [sum + v, count + 1];
        }
        out[horizontal ? o * width + i : i * width + o] = count ? sum / count : Number.NaN;
      }
    }
    return out;
  };
  for (let round = 0; round < 2; round++) current = pass(pass(current, true), false);
  return current;
}
