// Small statistics for the dashboards: trends that remove the yearly cycle and how two series move together.

type Value = number | null | undefined;

/**
 * Trailing 12-month mean: each month is the mean of itself and the 11 before it, so the yearly cycle cancels out and
 * only the trend is left. Null until 12 values are available, or when any of them is missing.
 */
export function movingAverage(values: Value[], window = 12): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    const slice = values.slice(i - window + 1, i + 1);
    if (slice.some((v) => v === null || v === undefined)) return null;
    return (slice as number[]).reduce((sum, v) => sum + v, 0) / window;
  });
}

/**
 * Each value minus the mean of its calendar month over every year: what is left once the yearly cycle is taken out.
 * Two series that both peak in summer correlate through the season alone; their deseasonalised values do not.
 */
export function deseasonalize(months: string[], values: Value[]): (number | null)[] {
  const byMonth = new Map<string, number[]>();
  months.forEach((m, i) => {
    const v = values[i];
    if (v === null || v === undefined) return;
    const key = m.slice(5, 7);
    byMonth.set(key, [...(byMonth.get(key) ?? []), v]);
  });
  const mean = (key: string) => {
    const vs = byMonth.get(key) ?? [];
    return vs.reduce((s, v) => s + v, 0) / vs.length;
  };
  return values.map((v, i) => (v === null || v === undefined ? null : v - mean((months[i] as string).slice(5, 7))));
}

export interface Correlation {
  /** Pearson's r, from -1 (one goes up when the other goes down) to 1 (they go up together). */
  r: number;
  /** Months with a value in both series. */
  n: number;
}

/** Pearson correlation of the pairs where both series have a value; null with fewer than 6 pairs or no variation. */
export function pearson(xs: Value[], ys: Value[]): Correlation | null {
  const pairs: [number, number][] = [];
  xs.forEach((x, i) => {
    const y = ys[i];
    if (x !== null && x !== undefined && y !== null && y !== undefined) pairs.push([x, y]);
  });
  const n = pairs.length;
  if (n < 6) return null;
  const meanX = pairs.reduce((s, [x]) => s + x, 0) / n;
  const meanY = pairs.reduce((s, [, y]) => s + y, 0) / n;
  let cov = 0;
  let varX = 0;
  let varY = 0;
  for (const [x, y] of pairs) {
    cov += (x - meanX) * (y - meanY);
    varX += (x - meanX) ** 2;
    varY += (y - meanY) ** 2;
  }
  if (varX === 0 || varY === 0) return null;
  return { r: cov / Math.sqrt(varX * varY), n };
}

/** The usual reading of |r|: weak below 0.3, moderate below 0.6, strong from there. */
export function strength(r: number): string {
  const size = Math.abs(r) < 0.3 ? "débil" : Math.abs(r) < 0.6 ? "moderada" : "fuerte";
  if (size === "débil") return "Relación débil";
  return `Relación ${size} ${r > 0 ? "directa" : "inversa"}`;
}

export interface GrowthTrend {
  /** Mean annual growth (0.012 = +1,2 % a year). */
  rate: number;
  /** The trend's value in a year. */
  at: (year: number) => number;
  /** First and last year of the fit. */
  from: number;
  to: number;
  /** Sum of the squared residuals of the logarithms: how far the years are from the trend. */
  sse: number;
  /**
   * Prediction interval of a year's value (95 % by default): where a new year would fall if the trend held. It
   * widens with the distance to the years of the fit.
   */
  interval: (year: number, z?: number) => [number, number];
}

/**
 * Exponential trend of a yearly series, fitted by least squares on the logarithm: the mean annual growth, steady
 * from the first year to the last. Years may be missing (there was no municipal register in 1997). Null with fewer
 * than two positive values.
 */
export function growthTrend(points: { year: number; value: number }[]): GrowthTrend | null {
  const valid = points.filter((p) => p.value > 0);
  const n = valid.length;
  if (n < 2) return null;
  const meanX = valid.reduce((s, p) => s + p.year, 0) / n;
  const meanY = valid.reduce((s, p) => s + Math.log(p.value), 0) / n;
  let cov = 0;
  let varX = 0;
  for (const p of valid) {
    cov += (p.year - meanX) * (Math.log(p.value) - meanY);
    varX += (p.year - meanX) ** 2;
  }
  if (varX === 0) return null;
  const slope = cov / varX;
  const fitted = (year: number) => meanY + slope * (year - meanX);
  const sse = valid.reduce((s, p) => s + (Math.log(p.value) - fitted(p.year)) ** 2, 0);
  const sigma = n > 2 ? Math.sqrt(sse / (n - 2)) : 0;
  const years = valid.map((p) => p.year);
  return {
    rate: Math.exp(slope) - 1,
    at: (year) => Math.exp(fitted(year)),
    from: Math.min(...years),
    to: Math.max(...years),
    sse,
    interval: (year, z = 1.96) => {
      const spread = z * sigma * Math.sqrt(1 + 1 / n + (year - meanX) ** 2 / varX);
      return [Math.exp(fitted(year) - spread), Math.exp(fitted(year) + spread)];
    },
  };
}

/**
 * The trend in one or two stretches: the series is split at the year that fits best (each stretch at least
 * `minYears` long) and kept whole unless the split halves the error. Mallorca grew fast until the 2008 crisis, then
 * stalled and grew again: one line for 30 years would hide it.
 */
export function segmentedTrend(points: { year: number; value: number }[], minYears = 6): GrowthTrend[] {
  const sorted = [...points].filter((p) => p.value > 0).sort((a, b) => a.year - b.year);
  const whole = growthTrend(sorted);
  if (!whole) return [];
  let best: [GrowthTrend, GrowthTrend] | null = null;
  for (let k = minYears; k <= sorted.length - minYears; k++) {
    const [before, after] = [growthTrend(sorted.slice(0, k)), growthTrend(sorted.slice(k))];
    if (before && after && (!best || before.sse + after.sse < best[0].sse + best[1].sse)) best = [before, after];
  }
  return best && best[0].sse + best[1].sse < whole.sse / 2 ? best : [whole];
}
