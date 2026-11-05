import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, StyleSpecification } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Location } from "../api";
import { useDarkMode } from "../hooks";
import { number } from "../lib/format";

/** The kinds of place on the map, in legend order, with their colour and size. */
export const KINDS = [
  { kind: "observation", label: "Estaciones", color: "#0891b2", radius: 6 },
  { kind: "model", label: "Puntos de modelo", color: "#d97706", radius: 5 },
  { kind: "schedule", label: "Paradas de bus y tren", color: "#7c3aed", radius: 2.5 },
] as const;

const MALLORCA: [[number, number], [number, number]] = [
  [2.28, 39.25],
  [3.5, 40.0],
];

function basemap(dark: boolean): StyleSpecification {
  const theme = dark ? "dark_all" : "light_all";
  return {
    version: 8,
    sources: {
      carto: {
        type: "raster",
        tiles: ["a", "b", "c"].map((s) => `https://${s}.basemaps.cartocdn.com/${theme}/{z}/{x}/{y}@2x.png`),
        tileSize: 256,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
      },
    },
    layers: [{ id: "carto", type: "raster", source: "carto" }],
  };
}

function toGeoJson(locations: Location[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: locations.map((l) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [l.lon, l.lat] },
      properties: { kind: l.kind, label: l.label ?? l.source, entity: l.entity, metrics: l.n_metrics },
    })),
  };
}

function addPlaces(map: maplibregl.Map, data: FeatureCollection, dark: boolean) {
  map.addSource("places", { type: "geojson", data });
  // Stops first, so the stations are drawn on top of them.
  for (const { kind, color, radius } of [...KINDS].reverse()) {
    map.addLayer({
      id: `places-${kind}`,
      type: "circle",
      source: "places",
      filter: ["==", ["get", "kind"], kind],
      paint: {
        "circle-color": color,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, radius, 13, radius * 2.2],
        "circle-opacity": kind === "schedule" ? 0.55 : 0.9,
        "circle-stroke-width": kind === "schedule" ? 0 : 1.5,
        "circle-stroke-color": dark ? "#0f172a" : "#ffffff",
      },
    });
  }
}

export function SourceMap({ locations }: { locations: Location[] }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const dark = useDarkMode();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const data = useMemo(() => toGeoJson(locations), [locations]);
  const counts = useMemo(() => {
    const byKind = new Map<string, number>();
    for (const l of locations) byKind.set(l.kind ?? "", (byKind.get(l.kind ?? "") ?? 0) + 1);
    return byKind;
  }, [locations]);

  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: basemap(dark),
      bounds: MALLORCA,
      fitBoundsOptions: { padding: 16 },
      attributionControl: { compact: true },
      cooperativeGestures: true,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      addPlaces(instance, data, dark);
      for (const { kind } of KINDS) {
        instance.on("click", `places-${kind}`, (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          const p = feature.properties as { label: string; entity: string; metrics: number };
          new maplibregl.Popup({ closeButton: false, offset: 8 })
            .setLngLat(feature.geometry.coordinates as [number, number])
            .setHTML(
              `<strong>${p.entity}</strong><br/><span>${p.label}</span><br/>` +
                `<span>${number(p.metrics)} ${p.metrics === 1 ? "métrica" : "métricas"}</span>`,
            )
            .addTo(instance);
        });
        instance.on("mouseenter", `places-${kind}`, () => (instance.getCanvas().style.cursor = "pointer"));
        instance.on("mouseleave", `places-${kind}`, () => (instance.getCanvas().style.cursor = ""));
      }
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // The map is rebuilt when the theme changes: the basemap and the stroke colour depend on it.
  }, [dark, data]);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      for (const { kind } of KINDS) {
        if (instance.getLayer(`places-${kind}`)) {
          instance.setLayoutProperty(`places-${kind}`, "visibility", hidden.has(kind) ? "none" : "visible");
        }
      }
      (instance.getSource("places") as GeoJSONSource | undefined)?.setData(data);
    };
    if (instance.isStyleLoaded()) apply();
    else instance.once("load", apply);
  }, [hidden, data]);

  const toggle = (kind: string) =>
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  return (
    <div className="map-wrap">
      <div ref={container} className="map" aria-label="Mapa de los puntos de medida" />
      <div className="legend" role="group" aria-label="Capas del mapa">
        {KINDS.map(({ kind, label, color }) => (
          <button
            key={kind}
            type="button"
            className="legend-item"
            aria-pressed={!hidden.has(kind)}
            onClick={() => toggle(kind)}
          >
            <span className="dot" style={{ background: color }} />
            {label}
            <span className="legend-count">{number(counts.get(kind) ?? 0)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
