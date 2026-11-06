// Heights of the ground from the open Terrarium relief tiles (Mapzen terrain on AWS Open Data, no key): PNG tiles
// in the same Web Mercator grid as the basemap, whose colour encodes the height in metres.

import { type Bounds, mercatorY, pixelCenter } from "./interpolate";

/** About 120 m per pixel at the latitude of Mallorca: finer than the temperature image (160 m). */
export const ELEVATION_ZOOM = 10;

const TILE = 256;
const TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium";

/** Metres above the sea of a Terrarium pixel: red × 256 + green + blue / 256 − 32768. */
export function terrariumHeight(r: number, g: number, b: number): number {
  return r * 256 + g + b / 256 - 32768;
}

/** Position of a point in the pixels of the whole world at a zoom (Web Mercator, the origin at the north-west). */
export function worldPixel(lon: number, lat: number, zoom: number): [number, number] {
  const size = TILE * 2 ** zoom;
  return [((lon + 180) / 360) * size, ((1 - mercatorY(lat) / Math.PI) / 2) * size];
}

/** The tiles that cover the bounds: the first column and row and how many of each. */
export function tileRange(bounds: Bounds, zoom: number): { x: number; y: number; columns: number; rows: number } {
  const [west, north] = worldPixel(bounds.west, bounds.north, zoom).map((p) => Math.floor(p / TILE)) as [number, number];
  const [east, south] = worldPixel(bounds.east, bounds.south, zoom).map((p) => Math.floor(p / TILE)) as [number, number];
  return { x: west, y: north, columns: east - west + 1, rows: south - north + 1 };
}

export interface Elevation {
  /** Height of every pixel of the requested image, row by row from the north. */
  values: Float64Array;
  /** Height of any point inside the bounds. */
  at: (lon: number, lat: number) => number;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = "anonymous"; // the pixels are read back, so the tiles must come with CORS
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`no se pudo cargar ${url}`));
    image.src = url;
  });
}

/** Downloads the tiles over the bounds and reads the height at the centre of every pixel of a width × height image. */
export async function loadElevation(
  bounds: Bounds,
  width: number,
  height: number,
  zoom = ELEVATION_ZOOM,
): Promise<Elevation> {
  const range = tileRange(bounds, zoom);
  const canvas = document.createElement("canvas");
  [canvas.width, canvas.height] = [range.columns * TILE, range.rows * TILE];
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("sin canvas");
  const tiles: Promise<void>[] = [];
  for (let row = 0; row < range.rows; row++) {
    for (let column = 0; column < range.columns; column++) {
      const url = `${TILE_URL}/${zoom}/${range.x + column}/${range.y + row}.png`;
      tiles.push(loadImage(url).then((image) => context.drawImage(image, column * TILE, row * TILE)));
    }
  }
  await Promise.all(tiles);
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
  const at = (lon: number, lat: number) => {
    const [px, py] = worldPixel(lon, lat, zoom);
    const x = Math.min(canvas.width - 1, Math.max(0, Math.floor(px - range.x * TILE)));
    const y = Math.min(canvas.height - 1, Math.max(0, Math.floor(py - range.y * TILE)));
    const i = (y * canvas.width + x) * 4;
    return terrariumHeight(data[i] as number, data[i + 1] as number, data[i + 2] as number);
  };
  const values = new Float64Array(width * height);
  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) values[row * width + col] = at(...pixelCenter(bounds, width, height, col, row));
  }
  return { values, at };
}
