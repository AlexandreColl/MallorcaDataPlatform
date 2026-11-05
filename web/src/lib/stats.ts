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
