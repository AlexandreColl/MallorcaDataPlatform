// A temperature surface over the island from scattered stations: inverse distance weighting on a grid of cells,
// keeping only the cells inside the coastline.

/** Simplified coastline of Mallorca (lon, lat), clockwise from the western tip; the logo is drawn from it too. */
export const ISLAND: [number, number][] = [
  [2.34, 39.56], [2.36, 39.59], [2.45, 39.66], [2.58, 39.74], [2.69, 39.8], [2.8, 39.86], [2.93, 39.9],
  [3.05, 39.92], [3.11, 39.94], [3.18, 39.955], [3.13, 39.915], [3.08, 39.89], [3.12, 39.87], [3.2, 39.89],
  [3.17, 39.84], [3.12, 39.82], [3.13, 39.76], [3.22, 39.74], [3.33, 39.75], [3.42, 39.74], [3.48, 39.71],
  [3.46, 39.66], [3.39, 39.57], [3.3, 39.46], [3.22, 39.39], [3.12, 39.32], [3.05, 39.265], [2.97, 39.32],
  [2.88, 39.36], [2.78, 39.42], [2.74, 39.5], [2.68, 39.56], [2.6, 39.54], [2.55, 39.48], [2.5, 39.52],
  [2.43, 39.53], [2.38, 39.54],
];

/** Ray casting: true when (lon, lat) is inside the polygon. */
export function inside(lon: number, lat: number, polygon: [number, number][] = ISLAND): boolean {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i] as [number, number];
    const [xj, yj] = polygon[j] as [number, number];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export interface Sample {
  lon: number;
  lat: number;
  value: number;
}

/** Inverse distance weighting: nearby stations weigh more (power 2); on top of a station, its own value. */
export function idw(samples: Sample[], lon: number, lat: number, power = 2): number {
  const k = Math.cos((lat * Math.PI) / 180); // a degree of longitude is shorter than one of latitude
  let num = 0;
  let den = 0;
  for (const s of samples) {
    const d2 = ((s.lon - lon) * k) ** 2 + (s.lat - lat) ** 2;
    if (d2 < 1e-12) return s.value;
    const w = 1 / d2 ** (power / 2);
    num += w * s.value;
    den += w;
  }
  return num / den;
}

export interface Cell {
  polygon: [number, number][];
  value: number;
}

/** Square cells of `step` degrees over the island, each with the interpolated value at its centre. */
export function surface(samples: Sample[], step = 0.02): Cell[] {
  if (samples.length === 0) return [];
  const lons = ISLAND.map(([x]) => x);
  const lats = ISLAND.map(([, y]) => y);
  const cells: Cell[] = [];
  for (let lon = Math.min(...lons); lon < Math.max(...lons); lon += step) {
    for (let lat = Math.min(...lats); lat < Math.max(...lats); lat += step) {
      const [cx, cy] = [lon + step / 2, lat + step / 2];
      if (!inside(cx, cy)) continue;
      cells.push({
        polygon: [[lon, lat], [lon + step, lat], [lon + step, lat + step], [lon, lat + step], [lon, lat]],
        value: idw(samples, cx, cy),
      });
    }
  }
  return cells;
}

/** A diverging blue → yellow → red scale for temperatures between `min` and `max`. */
const STOPS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"];

export function temperatureColor(value: number, min: number, max: number): string {
  const t = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 0.5;
  const pos = t * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(pos));
  const mix = pos - i;
  const a = hex(STOPS[i] as string);
  const b = hex(STOPS[i + 1] as string);
  return `rgb(${a.map((c, k) => Math.round(c + ((b[k] as number) - c) * mix)).join(", ")})`;
}

function hex(color: string): number[] {
  return [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
}

export const TEMPERATURE_STOPS = STOPS;
