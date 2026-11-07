import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, ImageSource, StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useMemo, useRef, useState } from "react";

import { number } from "../lib/format";
import { useTheme } from "../theme";

// maplibre looks for its worker next to its own module, which bundling renames: give it the bundled URL instead.
maplibregl.setWorkerUrl(workerUrl);

export interface MapPoint {
  lat: number;
  lon: number;
  /** Lines of the popup: the first one in bold. Plain text, escaped before it reaches the map. */
  popup: string[];
  /** Relative size, 1 by default (e.g. a stop's departures over the busiest stop's). */
  size?: number;
  /** Overrides the layer colour (e.g. the air quality band of a station). */
  color?: string;
}

export interface MapLayer {
  id: string;
  label: string;
  color: string;
  radius: number;
  points: MapPoint[];
}

const MALLORCA: [[number, number], [number, number]] = [
  [2.28, 39.25],
  [3.5, 40.0],
];

/** Spanish texts of the map controls. */
const LOCALE = {
  "CooperativeGesturesHandler.WindowsHelpText": "Usa Ctrl + rueda para hacer zoom",
  "CooperativeGesturesHandler.MacHelpText": "Usa ⌘ + rueda para hacer zoom",
  "CooperativeGesturesHandler.MobileHelpText": "Usa dos dedos para mover el mapa",
  "NavigationControl.ZoomIn": "Acercar",
  "NavigationControl.ZoomOut": "Alejar",
};

/**
 * OpenStreetMap tiles (no key), toned down so the points stand out: greyed in light mode and inverted in dark mode
 * (swapping the minimum and maximum brightness inverts the raster).
 */
function basemap(dark: boolean): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
    },
    layers: [
      {
        id: "osm",
        type: "raster",
        source: "osm",
        paint: dark
          ? { "raster-saturation": -1, "raster-brightness-min": 0.92, "raster-brightness-max": 0.1, "raster-contrast": 0.1 }
          : { "raster-saturation": -0.9, "raster-brightness-min": 0.1, "raster-contrast": -0.1 },
      },
    ],
  };
}

function escape(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function toGeoJson(layers: MapLayer[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: layers.flatMap((layer) =>
      layer.points.map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
        properties: { layer: layer.id, popup: JSON.stringify(p.popup), size: p.size ?? 1, color: p.color ?? null },
      })),
    ),
  };
}

/** A filled polygon drawn under the points (a municipality, a warning zone). */
export interface MapArea {
  polygon: [number, number][];
  color: string;
  /** Lines of the popup shown on a click on the area (not on a point over it), as for a point. */
  popup?: string[];
  /** Identifies the area in `onAreaSelect` and `focus` (several polygons may share it). */
  id?: string;
}

/** Lines drawn over the image and under the areas (contour lines, for instance). */
export interface MapLines {
  lines: [number, number][][];
  color: string;
}

/** A picture stretched over a box of the map, under the areas and points (an interpolated surface). */
export interface MapImage {
  url: string;
  west: number;
  south: number;
  east: number;
  north: number;
}

interface PointMapProps {
  layers: MapLayer[];
  areas?: MapArea[];
  image?: MapImage;
  height?: number;
  /** Opacity of the areas: lower when points are drawn over them. */
  areaOpacity?: number;
  /** Draws the border of each area. */
  outline?: boolean;
  lines?: MapLines;
  /** Text of a small label that follows the cursor (e.g. the value of the image under it), or null for none. */
  describe?: (lon: number, lat: number) => string | null;
  /** The area to highlight and zoom to, by its id. */
  focus?: string | null;
  /** Called with the id of an area clicked outside any point. */
  onAreaSelect?: (id: string) => void;
}

function areasGeoJson(areas: MapArea[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: areas.map((a) => ({
      type: "Feature" as const,
      geometry: { type: "Polygon" as const, coordinates: [a.polygon] },
      properties: { color: a.color, popup: a.popup ? JSON.stringify(a.popup) : null, id: a.id ?? null },
    })),
  };
}

function popupHtml(popup: unknown): string {
  const [title, ...rest] = JSON.parse(String(popup)) as string[];
  return `<strong>${escape(title ?? "")}</strong>${rest.map((l) => `<br/><span>${escape(l)}</span>`).join("")}`;
}

function linesGeoJson(lines: MapLines | undefined): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: lines
      ? [{ type: "Feature" as const, geometry: { type: "MultiLineString" as const, coordinates: lines.lines }, properties: {} }]
      : [],
  };
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

/** The polygons of an area by its id, to highlight it. */
function focusGeoJson(areas: MapArea[], id: string | null | undefined): FeatureCollection {
  if (!id) return EMPTY;
  return areasGeoJson(areas.filter((a) => a.id === id));
}

export function PointMap({
  layers,
  areas = [],
  image,
  height = 480,
  areaOpacity,
  outline = false,
  lines,
  describe,
  focus,
  onAreaSelect,
}: PointMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const { theme } = useTheme();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [label, setLabel] = useState<{ x: number; y: number; text: string } | null>(null);
  const data = useMemo(() => toGeoJson(layers), [layers]);
  const areaData = useMemo(() => areasGeoJson(areas), [areas]);
  const lineData = useMemo(() => linesGeoJson(lines), [lines]);
  const focusData = useMemo(() => focusGeoJson(areas, focus), [areas, focus]);
  // Read by the map's own handlers, which are bound once per map: changing them must not rebuild the map.
  const handlers = useRef({ describe, onAreaSelect, focusData });
  handlers.current = { describe, onAreaSelect, focusData };
  // The data the map is built with. Only a change of structure (the theme, which layers exist, their style) builds
  // a new map; new data of the same layers (another day, another colouring) is swapped into the sources below, so
  // the map neither flashes nor loses its zoom.
  const latest = useRef({ data, areaData, lineData, image });
  latest.current = { data, areaData, lineData, image };
  const structure = [
    layers.map((l) => `${l.id}:${l.color}:${l.radius}`).join(","),
    image ? "image" : "",
    lines ? `lines:${lines.color}` : "",
    areaData.features.length > 0 ? "areas" : "",
    areas.some((a) => a.popup) ? "popups" : "",
  ].join("|");

  useEffect(() => {
    if (!container.current) return;
    const dark = theme === "dark";
    const instance = new maplibregl.Map({
      container: container.current,
      style: basemap(dark),
      bounds: MALLORCA,
      fitBoundsOptions: { padding: 16 },
      attributionControl: { compact: true },
      cooperativeGestures: true,
      locale: LOCALE,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const pointLayers = layers.map((layer) => `points-${layer.id}`);
    const setup = () => {
      const { data, areaData, lineData, image } = latest.current;
      if (image) {
        instance.addSource("image", {
          type: "image",
          url: image.url,
          coordinates: [
            [image.west, image.north],
            [image.east, image.north],
            [image.east, image.south],
            [image.west, image.south],
          ],
        });
        instance.addLayer({
          id: "image",
          type: "raster",
          source: "image",
          paint: { "raster-opacity": dark ? 0.7 : 0.8, "raster-resampling": "linear", "raster-fade-duration": 0 },
        });
      }
      if (lines) {
        instance.addSource("lines", { type: "geojson", data: lineData });
        instance.addLayer({
          id: "lines",
          type: "line",
          source: "lines",
          paint: { "line-color": lines.color, "line-opacity": 0.55, "line-width": 0.8 },
        });
      }
      if (areaData.features.length > 0) {
        instance.addSource("areas", { type: "geojson", data: areaData });
        instance.addLayer({
          id: "areas",
          type: "fill",
          source: "areas",
          paint: {
            "fill-color": ["get", "color"],
            "fill-opacity": areaOpacity ?? (dark ? 0.6 : 0.7),
            "fill-antialias": false,
          },
        });
        if (outline) {
          instance.addLayer({
            id: "areas-outline",
            type: "line",
            source: "areas",
            paint: { "line-color": dark ? "#e5e7eb" : "#1f2937", "line-opacity": 0.35, "line-width": 0.6 },
          });
        }
        instance.addSource("focus", { type: "geojson", data: handlers.current.focusData });
        instance.addLayer({
          id: "focus",
          type: "line",
          source: "focus",
          paint: { "line-color": dark ? "#fde047" : "#0a120d", "line-width": 2.5 },
        });
        instance.on("click", "areas", (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          // A point over the area has its own popup.
          const visible = pointLayers.filter((id) => instance.getLayer(id));
          if (instance.queryRenderedFeatures(event.point, { layers: visible }).length > 0) return;
          if (feature.properties.id) handlers.current.onAreaSelect?.(String(feature.properties.id));
          if (!feature.properties.popup) return;
          new maplibregl.Popup({ closeButton: false })
            .setLngLat(event.lngLat)
            .setHTML(popupHtml(feature.properties.popup))
            .addTo(instance);
        });
        if (areas.some((a) => a.popup)) {
          instance.on("mouseenter", "areas", () => (instance.getCanvas().style.cursor = "pointer"));
          instance.on("mouseleave", "areas", () => (instance.getCanvas().style.cursor = ""));
        }
      }
      instance.addSource("points", { type: "geojson", data });
      // The first layer is drawn last, on top of the others.
      for (const layer of [...layers].reverse()) {
        const id = `points-${layer.id}`;
        instance.addLayer({
          id,
          type: "circle",
          source: "points",
          filter: ["==", ["get", "layer"], layer.id],
          paint: {
            "circle-color": ["coalesce", ["get", "color"], layer.color],
            // "zoom" may only sit at the top of an interpolate: the size multiplies each stop instead.
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              8,
              ["*", layer.radius, ["get", "size"]],
              13,
              ["*", layer.radius * 2.2, ["get", "size"]],
            ],
            "circle-opacity": layer.radius < 4 ? 0.6 : 0.92,
            "circle-stroke-width": layer.radius < 4 ? 0 : 1.5,
            "circle-stroke-color": dark ? "#0a120d" : "#ffffff",
          },
        });
        instance.on("click", id, (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          new maplibregl.Popup({ closeButton: false, offset: 8 })
            .setLngLat(feature.geometry.coordinates as [number, number])
            .setHTML(popupHtml(feature.properties.popup))
            .addTo(instance);
        });
        instance.on("mouseenter", id, () => (instance.getCanvas().style.cursor = "pointer"));
        instance.on("mouseleave", id, () => (instance.getCanvas().style.cursor = ""));
      }
    };
    // Layers go in as soon as the style is ready ("load" would wait for every OpenStreetMap tile), once.
    let added = false;
    const addOnce = () => {
      if (added || !instance.isStyleLoaded()) return;
      added = true;
      setup();
    };
    instance.on("styledata", addOnce);
    instance.once("load", addOnce);
    instance.on("mousemove", (event) => {
      const text = handlers.current.describe?.(event.lngLat.lng, event.lngLat.lat) ?? null;
      setLabel(text === null ? null : { x: event.point.x, y: event.point.y, text });
    });
    instance.on("mouseout", () => setLabel(null));
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // Rebuilt when the theme changes (basemap and strokes) or the structure does; `latest` holds the data.
  }, [theme, structure, areaOpacity, outline]);

  // New data of the same layers goes into the existing sources. A source that does not exist yet needs nothing:
  // `setup` reads `latest` when it adds it. (Not "wait for load": a loaded map never fires it again.)
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const source = instance.getSource("image") as ImageSource | undefined;
    if (source && image) {
      source.updateImage({
        url: image.url,
        coordinates: [
          [image.west, image.north],
          [image.east, image.north],
          [image.east, image.south],
          [image.west, image.south],
        ],
      });
    }
    (instance.getSource("lines") as GeoJSONSource | undefined)?.setData(lineData);
    (instance.getSource("areas") as GeoJSONSource | undefined)?.setData(areaData);
  }, [image, lineData, areaData]);

  // The highlighted area changes without rebuilding the map, and the map flies to it (and back to the island).
  const zoomed = useRef(false);
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      (instance.getSource("focus") as GeoJSONSource | undefined)?.setData(focusData);
      const points = focusData.features.flatMap((f) => (f.geometry.type === "Polygon" ? f.geometry.coordinates.flat() : []));
      if (points.length === 0) {
        if (zoomed.current) instance.fitBounds(MALLORCA, { padding: 16, duration: 600 });
        zoomed.current = false;
        return;
      }
      zoomed.current = true;
      const lons = points.map((p) => p[0] as number);
      const lats = points.map((p) => p[1] as number);
      instance.fitBounds(
        [
          [Math.min(...lons), Math.min(...lats)],
          [Math.max(...lons), Math.max(...lats)],
        ],
        { padding: 60, maxZoom: 12, duration: 600 },
      );
    };
    if (instance.getSource("focus")) apply();
    else instance.once("idle", apply);
  }, [focusData]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      for (const layer of layers) {
        const id = `points-${layer.id}`;
        if (instance.getLayer(id)) instance.setLayoutProperty(id, "visibility", hidden.has(layer.id) ? "none" : "visible");
      }
      (instance.getSource("points") as GeoJSONSource | undefined)?.setData(data);
    };
    if (instance.getSource("points")) apply();
    else instance.once("idle", apply); // the hidden layers of a map still being built
  }, [hidden, data, layers]);

  const toggle = (id: string) =>
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="map-wrap">
      <div ref={container} className="map" style={{ minHeight: height }} aria-label="Mapa" />
      {label && (
        <div className="map-label" style={{ left: label.x, top: label.y }} aria-hidden="true">
          {label.text}
        </div>
      )}
      {layers.length > 1 && (
        <div className="legend" role="group" aria-label="Capas del mapa">
          {layers.map(({ id, label, color, points }) => (
            <button key={id} type="button" className="legend-item" aria-pressed={!hidden.has(id)} onClick={() => toggle(id)}>
              <span className="dot" style={{ background: color }} />
              {label}
              <span className="legend-count">{number(points.length)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
