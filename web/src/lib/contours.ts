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
  // One pass over the squares, trying only the levels between the lowest and the highest corner of each: this runs
  // for every day the player shows, so the loop allocates nothing but the segments it finds.
  const found: Segment[][] = levels.map(() => []);
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      const [ia, ib] = [y * width + x, y * width + x + 1];
      const [ic, id] = [ib + width, ia + width];
      if (mask && !(mask[ia] && mask[ib] && mask[ic] && mask[id])) continue;
      const a = values[ia] as number;
      const b = values[ib] as number;
      const c = values[ic] as number;
      const d = values[id] as number;
      if (!(Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(c) && Number.isFinite(d))) continue;
      const low = Math.min(a, b, c, d);
      const high = Math.max(a, b, c, d);
      for (let l = 0; l < levels.length; l++) {
        const level = levels[l] as number;
        if (level <= low || level > high) continue; // every corner on the same side
        // Where the level crosses each side: top, right, bottom, left (null: not crossed).
        const top = a >= level === b >= level ? null : crossing(x, y, x + 1, y, (level - a) / (b - a));
        const right = b >= level === c >= level ? null : crossing(x + 1, y, x + 1, y + 1, (level - b) / (c - b));
        const bottom = d >= level === c >= level ? null : crossing(x, y + 1, x + 1, y + 1, (level - d) / (c - d));
        const left = a >= level === d >= level ? null : crossing(x, y, x, y + 1, (level - a) / (d - a));
        const segments = found[l] as Segment[];
        if (top && right && bottom && left) {
          // A saddle: the mean of the square decides which corners are joined.
          const centreHigh = (a + b + c + d) / 4 >= level;
          if (centreHigh === a >= level) segments.push([top, right], [bottom, left]);
          else segments.push([top, left], [bottom, right]);
        } else {
          const hits = [top, right, bottom, left].filter((p): p is [number, number] => p !== null);
          if (hits.length === 2) segments.push([hits[0] as [number, number], hits[1] as [number, number]]);
        }
      }
    }
  }
  return levels.map((level, l) => ({ level, segments: found[l] as Segment[] }));
}

/** The point a fraction `t` of the way from (x0, y0) to (x1, y1). */
function crossing(x0: number, y0: number, x1: number, y1: number, t: number): [number, number] {
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t];
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
    // Plain counters, no arrays: this runs over every pixel four times for every day the player shows.
    const [step, stride] = horizontal ? [1, width] : [width, 1];
    for (let o = 0; o < outer; o++) {
      const base = o * stride;
      for (let i = 0; i < inner; i++) {
        let sum = 0;
        let count = 0;
        const last = Math.min(inner - 1, i + radius);
        for (let k = Math.max(0, i - radius); k <= last; k++) {
          const v = source[base + k * step] as number;
          if (Number.isFinite(v)) {
            sum += v;
            count++;
          }
        }
        out[base + i * step] = count ? sum / count : Number.NaN;
      }
    }
    return out;
  };
  for (let round = 0; round < 2; round++) current = pass(pass(current, true), false);
  return current;
}
