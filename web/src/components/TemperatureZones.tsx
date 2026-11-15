import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type Municipality, type StationDay } from "../api";
import { blur, contourLevels, contours } from "../lib/contours";
import { type Elevation, loadElevation } from "../lib/elevation";
import { number, placeName } from "../lib/format";
import {
  type Bounds,
  grid,
  imageHeight,
  ISLAND_BOUNDS,
  mercatorY,
  pixelCenter,
  pixelOf,
  TEMPERATURE_STOPS,
  temperatureColor,
  temperaturePalette,
} from "../lib/interpolate";
import { DaySlider } from "./DaySlider";
import { type MapImage, type MapLayer, type MapLines, PointMap } from "./PointMap";

const TEMPERATURE_FIELDS = {
  temperature_mean: "Media",
  temperature_max: "Máxima",
  temperature_min: "Mínima",
} as const;

type TemperatureField = keyof typeof TEMPERATURE_FIELDS;

/** Pixels across the temperature image: about 160 m each, fine enough that MapLibre's smoothing hides them. */
const IMAGE_WIDTH = 640;
const IMAGE_HEIGHT = imageHeight(ISLAND_BOUNDS, IMAGE_WIDTH);

/**
 * The interpolated temperatures as a PNG over the bounds, transparent outside the coastline, and which pixels are
 * on land: the pixels are painted first and then kept only where the municipalities are filled in.
 */
function temperatureImage(
  values: Float64Array,
  coast: [number, number][][],
  bounds: Bounds,
  min: number,
  max: number,
): { url: string; land: Uint8Array } {
  const [width, height] = [IMAGE_WIDTH, IMAGE_HEIGHT];
  const pixels = new ImageData(width, height);
  const palette = temperaturePalette(min, max);
  const scale = max > min ? 255 / (max - min) : 0;
  for (let i = 0; i < values.length; i++) {
    const step = scale ? Math.round(Math.min(255, Math.max(0, ((values[i] as number) - min) * scale))) : 128;
    pixels.data[i * 4] = palette[step * 3] as number;
    pixels.data[i * 4 + 1] = palette[step * 3 + 1] as number;
    pixels.data[i * 4 + 2] = palette[step * 3 + 2] as number;
    pixels.data[i * 4 + 3] = 255;
  }
  const painted = document.createElement("canvas");
  [painted.width, painted.height] = [width, height];
  painted.getContext("2d")?.putImageData(pixels, 0, 0);

  const canvas = document.createElement("canvas");
  [canvas.width, canvas.height] = [width, height];
  const context = canvas.getContext("2d", { willReadFrequently: true });
  const land = new Uint8Array(width * height);
  if (!context) return { url: "", land };
  const [top, bottom] = [mercatorY(bounds.north), mercatorY(bounds.south)];
  context.beginPath();
  for (const ring of coast) {
    ring.forEach(([lon, lat], i) => {
      const x = ((lon - bounds.west) / (bounds.east - bounds.west)) * width;
      const y = ((top - mercatorY(lat)) / (top - bottom)) * height;
      if (i === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.closePath();
  }
  context.fill();
  // Pixels at least half covered by the coastline count as land (for the isotherms and the value under the cursor).
  const alpha = context.getImageData(0, 0, width, height).data;
  for (let i = 0; i < land.length; i++) land[i] = (alpha[i * 4 + 3] as number) >= 128 ? 1 : 0;
  // Keeps the painted temperatures only where the coastline was just filled.
  context.globalCompositeOperation = "source-in";
  context.drawImage(painted, 0, 0);
  return { url: canvas.toDataURL("image/png"), land };
}

/** Isotherms in longitude and latitude: the pixel coordinates of the contours are pixel centres. */
function isotherms(values: Float64Array, land: Uint8Array, min: number, max: number): [number, number][][] {
  const toLonLat = ([x, y]: [number, number]): [number, number] => {
    const [lon0, lat0] = pixelCenter(ISLAND_BOUNDS, IMAGE_WIDTH, IMAGE_HEIGHT, Math.floor(x), Math.floor(y));
    const [lon1, lat1] = pixelCenter(ISLAND_BOUNDS, IMAGE_WIDTH, IMAGE_HEIGHT, Math.floor(x) + 1, Math.floor(y) + 1);
    return [lon0 + (lon1 - lon0) * (x % 1), lat0 + (lat1 - lat0) * (y % 1)];
  };
  // On a blurred copy (about 500 m): the lines follow the shape of the relief, not every gully.
  const smooth = blur(values, IMAGE_WIDTH, IMAGE_HEIGHT, 3);
  return contours(smooth, IMAGE_WIDTH, IMAGE_HEIGHT, contourLevels(min, max), land).flatMap((c) =>
    c.segments.map(([a, b]) => [toLonLat(a), toLonLat(b)]),
  );
}

/**
 * The relief under the temperature image, from the open Terrarium tiles: null while it loads, "failed" when they
 * cannot be read (the map then interpolates without the altitude correction).
 */
function useElevation(): Elevation | null | "failed" {
  const [elevation, setElevation] = useState<Elevation | null | "failed">(null);
  useEffect(() => {
    let alive = true;
    loadElevation(ISLAND_BOUNDS, IMAGE_WIDTH, IMAGE_HEIGHT)
      .then((e) => alive && setElevation(e))
      .catch(() => alive && setElevation("failed"));
    return () => {
      alive = false;
    };
  }, []);
  return elevation;
}

/** Fetches the stations of every day at once (the answers are remembered, so each step of the player is instant). */
function preloadDays(days: string[]) {
  for (const day of days) api.stations("aemet", day).catch(() => undefined);
}

/**
 * The temperature of the AEMET stations spread over the island. Every station is brought down to the sea with the
 * lapse rate (6.5 °C per km), the inverse-distance mean is taken there and every pixel goes back up to the height
 * of its ground: the colours show the warm south and the cold summits of the Tramuntana, not just rings around
 * the stations. Isotherms every degree, and the value under the cursor. `days` are the days AEMET has published,
 * newest first: the select shows any of them.
 */
export function TemperatureZones({ stations, places, days, onDay }: {
  stations: StationDay[];
  places: Municipality[];
  days: string[];
  onDay: (day: string) => void;
}) {
  const [field, setField] = useState<TemperatureField>("temperature_max");
  const elevation = useElevation();
  const relief = elevation !== null && elevation !== "failed" ? elevation : null;
  const surface = useMemo(() => {
    if (elevation === null) return null; // waits for the relief rather than drawing the map twice
    const samples = stations
      .filter((s) => s[field] !== null)
      .map((s) => ({
        lon: s.lon, lat: s.lat, value: s[field] as number, name: placeName(s.entity, s.name),
        elevation: relief ? Math.max(0, relief.at(s.lon, s.lat)) : undefined,
      }));
    const measured = samples.map((s) => s.value);
    const [min, max] = [Math.floor(Math.min(...measured)), Math.ceil(Math.max(...measured))];
    const coast = places.flatMap((p) => p.polygon);
    const values = grid(samples, ISLAND_BOUNDS, IMAGE_WIDTH, IMAGE_HEIGHT, relief?.values);
    const painted = samples.length > 0 ? temperatureImage(values, coast, ISLAND_BOUNDS, min, max) : null;
    const image: MapImage | undefined = painted ? { url: painted.url, ...ISLAND_BOUNDS } : undefined;
    const lines: MapLines | undefined = painted
      ? { lines: isotherms(values, painted.land, min, max), color: "#0a120d" }
      : undefined;
    const layers: MapLayer[] = [
      {
        id: "stations", label: "Estaciones", color: "#0a120d", radius: 4.5,
        points: samples.map((s) => ({
          lat: s.lat, lon: s.lon, color: temperatureColor(s.value, min, max),
          popup: [
            s.name,
            `${TEMPERATURE_FIELDS[field]}: ${number(s.value, 1)} °C`,
            ...(s.elevation === undefined ? [] : [`${number(s.elevation)} m de altitud`]),
          ],
        })),
      },
    ];
    return { samples, values, land: painted?.land, image, lines, layers, min, max };
  }, [stations, places, field, elevation, relief]);

  const describe = useCallback(
    (lon: number, lat: number) => {
      if (!surface?.land) return null;
      const i = pixelOf(ISLAND_BOUNDS, IMAGE_WIDTH, IMAGE_HEIGHT, lon, lat);
      if (i === null || !surface.land[i]) return null;
      const height = relief ? ` · ${number(Math.max(0, relief.values[i] as number))} m` : "";
      return `${number(surface.values[i] as number, 1)} °C${height}`;
    },
    [surface, relief],
  );

  if (surface === null) return <div className="block skeleton" style={{ height: 520 }} aria-busy="true" />;
  const shown = stations[0]?.local_date.slice(0, 10);
  const controls = (
    <div className="controls">
      <div className="segmented" role="group" aria-label="Temperatura">
        {(Object.keys(TEMPERATURE_FIELDS) as TemperatureField[]).map((f) => (
          <button key={f} type="button" aria-pressed={f === field} onClick={() => setField(f)}>
            {TEMPERATURE_FIELDS[f]}
          </button>
        ))}
      </div>
      {days.length > 1 && <DaySlider days={days} value={shown ?? days[0] as string} onChange={onDay} onPlay={preloadDays} />}
    </div>
  );
  if (surface.samples.length === 0) {
    return (
      <>
        {controls}
        <p className="empty">Sin temperaturas para ese día.</p>
      </>
    );
  }
  return (
    <>
      {controls}
      <PointMap layers={surface.layers} image={surface.image} lines={surface.lines} describe={describe} height={480} />
      <div className="gradient-scale">
        <span>{number(surface.min)} °C</span>
        <span className="gradient-bar" style={{ background: `linear-gradient(90deg, ${TEMPERATURE_STOPS.join(", ")})` }} />
        <span>{number(surface.max)} °C</span>
      </div>
      <p className="map-note">
        Isotermas cada {surface.max - surface.min > 12 ? 2 : 1} °C.{" "}
        {elevation === "failed"
          ? "Sin corrección por altitud: no se pudo cargar el relieve."
          : "Corregido por la altitud del terreno (relieve de Mapzen Terrain Tiles); pasa el cursor para ver la temperatura y la altura."}
      </p>
    </>
  );
}
