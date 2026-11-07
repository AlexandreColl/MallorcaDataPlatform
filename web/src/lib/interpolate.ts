// A temperature surface over the island from scattered stations: inverse distance weighting on a fine grid of
// pixels, drawn as an image over the map and clipped to the coastline.

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
  /** Height above the sea in metres, for the altitude correction of `grid`. */
  elevation?: number;
}

/** Standard lapse rate: the air cools about 6.5 °C for every kilometre up. */
export const LAPSE_RATE = 0.0065;

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

/** A box of longitudes and latitudes. */
export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** Mallorca with a margin of sea: the area of the temperature image. */
export const ISLAND_BOUNDS: Bounds = { west: 2.3, south: 39.24, east: 3.5, north: 39.98 };

/** Web Mercator y of a latitude, up to a constant scale: MapLibre stretches an image linearly in this projection. */
export function mercatorY(lat: number): number {
  return Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
}

export function latitudeOf(y: number): number {
  return ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;
}

/** Image height that keeps the pixels square on the map for a given width. */
export function imageHeight(bounds: Bounds, width: number): number {
  const lonSpan = ((bounds.east - bounds.west) * Math.PI) / 180;
  return Math.round((width * (mercatorY(bounds.north) - mercatorY(bounds.south))) / lonSpan);
}

/** Longitude and latitude of the centre of a pixel of a width × height image over the bounds (rows in Mercator). */
export function pixelCenter(bounds: Bounds, width: number, height: number, col: number, row: number): [number, number] {
  const [top, bottom] = [mercatorY(bounds.north), mercatorY(bounds.south)];
  return [
    bounds.west + ((bounds.east - bounds.west) * (col + 0.5)) / width,
    latitudeOf(top + ((bottom - top) * (row + 0.5)) / height),
  ];
}

/** The pixel of a width × height image over the bounds that contains a point, or null outside the image. */
export function pixelOf(bounds: Bounds, width: number, height: number, lon: number, lat: number): number | null {
  const [top, bottom] = [mercatorY(bounds.north), mercatorY(bounds.south)];
  const col = Math.floor(((lon - bounds.west) / (bounds.east - bounds.west)) * width);
  const row = Math.floor(((top - mercatorY(lat)) / (top - bottom)) * height);
  return col < 0 || col >= width || row < 0 || row >= height ? null : row * width + col;
}

/**
 * The interpolated value at the centre of every pixel of a width × height image over the bounds, row by row from
 * the north. Rows are evenly spaced in Web Mercator, not in latitude, so the image lines up with the map.
 *
 * With the height of every pixel (`elevation`, metres) the stations are first brought down to the sea with the
 * lapse rate, interpolated there and each pixel taken back up to its own height: a mountain station then cools the
 * mountains around it and not the plain at its foot.
 */
export function grid(
  samples: Sample[],
  bounds: Bounds,
  width: number,
  height: number,
  elevation?: Float64Array,
): Float64Array {
  const values = new Float64Array(width * height);
  if (samples.length === 0) return values.fill(Number.NaN);
  const above = (h: number | undefined) => Math.max(0, h ?? 0);
  // The same inverse-distance mean as `idw` (power 2), unrolled: this runs for every pixel of every day the player
  // shows, so nothing is allocated in the loop and the coordinates of each column and row are computed once.
  const n = samples.length;
  const [sLon, sLat, sValue] = [new Float64Array(n), new Float64Array(n), new Float64Array(n)];
  samples.forEach((s, j) => {
    [sLon[j], sLat[j]] = [s.lon, s.lat];
    sValue[j] = s.value + (elevation ? LAPSE_RATE * above(s.elevation) : 0); // brought down to the sea
  });
  const lons = Float64Array.from({ length: width }, (_, col) => pixelCenter(bounds, width, height, col, 0)[0]);
  for (let row = 0; row < height; row++) {
    const lat = pixelCenter(bounds, width, height, 0, row)[1];
    const k = Math.cos((lat * Math.PI) / 180);
    for (let col = 0; col < width; col++) {
      const lon = lons[col] as number;
      let num = 0;
      let den = 0;
      let exact = Number.NaN;
      for (let j = 0; j < n; j++) {
        const dx = ((sLon[j] as number) - lon) * k;
        const dy = (sLat[j] as number) - lat;
        const d2 = dx * dx + dy * dy;
        if (d2 < 1e-12) {
          exact = sValue[j] as number;
          break;
        }
        num += (sValue[j] as number) / d2;
        den += 1 / d2;
      }
      const i = row * width + col;
      const atSea = Number.isNaN(exact) ? num / den : exact;
      values[i] = atSea - (elevation ? LAPSE_RATE * above(elevation[i]) : 0);
    }
  }
  return values;
}

/** A diverging blue → yellow → red scale for temperatures between `min` and `max`. */
const STOPS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"];

/** The red, green and blue (0-255) of a temperature on the scale. */
export function temperatureRgb(value: number, min: number, max: number): [number, number, number] {
  const t = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 0.5;
  const pos = t * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(pos));
  const mix = pos - i;
  const a = STOP_RGB[i] as number[];
  const b = STOP_RGB[i + 1] as number[];
  const [r, g, bl] = a.map((c, k) => Math.round(c + ((b[k] as number) - c) * mix)) as [number, number, number];
  return [r, g, bl];
}

/**
 * The scale as 256 steps from `min` to `max`, red, green and blue in a row: an image colours each pixel from it
 * instead of mixing the stops again for every pixel.
 */
export function temperaturePalette(min: number, max: number): Uint8ClampedArray {
  const palette = new Uint8ClampedArray(256 * 3);
  for (let step = 0; step < 256; step++) palette.set(temperatureRgb(min + ((max - min) * step) / 255, min, max), step * 3);
  return palette;
}

export function temperatureColor(value: number, min: number, max: number): string {
  return `rgb(${temperatureRgb(value, min, max).join(", ")})`;
}

function hex(color: string): number[] {
  return [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
}

const STOP_RGB = STOPS.map(hex);

export const TEMPERATURE_STOPS = STOPS;
