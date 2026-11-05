import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, StyleSpecification } from "maplibre-gl";
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

export function PointMap({ layers, height = 480 }: { layers: MapLayer[]; height?: number }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const { theme } = useTheme();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const data = useMemo(() => toGeoJson(layers), [layers]);

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
    instance.on("load", () => {
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
          const [title, ...rest] = JSON.parse(String(feature.properties.popup)) as string[];
          new maplibregl.Popup({ closeButton: false, offset: 8 })
            .setLngLat(feature.geometry.coordinates as [number, number])
            .setHTML(`<strong>${escape(title ?? "")}</strong>${rest.map((l) => `<br/><span>${escape(l)}</span>`).join("")}`)
            .addTo(instance);
        });
        instance.on("mouseenter", id, () => (instance.getCanvas().style.cursor = "pointer"));
        instance.on("mouseleave", id, () => (instance.getCanvas().style.cursor = ""));
      }
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // Rebuilt when the theme changes (basemap and strokes) or the layers do.
  }, [theme, data, layers]);

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
    if (instance.isStyleLoaded()) apply();
    else instance.once("load", apply);
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
