import { useMemo, useState } from "react";

import { number, signed } from "../lib/format";
import type { MunicipalityRow } from "../lib/mobility";
import { binColor } from "../lib/population";
import { type MapArea, type MapLayer, PointMap } from "./PointMap";

type View = "density" | "service" | "growth" | "none";

const VIEWS: Record<View, { label: string; legend: string[]; bounds: number[]; colors: string[] }> = {
  density: {
    label: "Densidad",
    legend: ["< 25", "25-50", "50-100", "100-200", "200-500", "≥ 500 hab./km²"],
    bounds: [25, 50, 100, 200, 500],
    colors: ["#dcfce7", "#bbf7d0", "#86efac", "#4ade80", "#16a34a", "#14532d"],
  },
  service: {
    label: "Servicio por habitante",
    legend: ["< 50", "50-100", "100-200", "200-400", "400-800", "≥ 800 pasos por 1.000 hab."],
    bounds: [50, 100, 200, 400, 800],
    // Violet, not blue: the CTM stops are blue.
    colors: ["#f5f3ff", "#ddd6fe", "#c4b5fd", "#a78bfa", "#7c3aed", "#4c1d95"],
  },
  growth: {
    label: "Crecimiento en 10 años",
    legend: ["< 0 %", "0-5 %", "5-10 %", "10-20 %", "20-30 %", "≥ 30 %"],
    bounds: [0, 0.05, 0.1, 0.2, 0.3],
    colors: ["#f87171", "#fde68a", "#d9f99d", "#86efac", "#22c55e", "#15803d"],
  },
  // Only the borders, so the stops stand out on the basemap.
  none: { label: "Sin colorear", legend: [], bounds: [], colors: [] },
};

/**
 * One map for both: the municipalities coloured by the chosen figure, with the stops of each network on top (sized
 * by their departures and toggled from the legend). A click on a stop shows the stop; anywhere else, the municipality.
 */
export function MobilityMap({ rows, stops, year, selected, onSelect }: {
  rows: MunicipalityRow[];
  stops: MapLayer[];
  year: number;
  selected: string | null;
  onSelect: (code: string) => void;
}) {
  const [view, setView] = useState<View>("density");
  const areas = useMemo(() => {
    const scale = VIEWS[view];
    const value = (r: MunicipalityRow) =>
      view === "density" ? (r.latest?.density_per_km2 ?? null) : view === "service" ? r.perThousand : r.growth;
    return rows.flatMap((r): MapArea[] => {
      const popup = [
        r.place.name,
        `${number(r.latest?.population ?? 0)} hab. · ${number(r.latest?.density_per_km2 ?? 0)} hab./km²`,
        r.growth === null ? "Sin dato de hace 10 años" : `${signed(r.growth * 100)} % desde ${year - 10}`,
        `${number(r.service.stops)} paradas · ${number(r.perThousand ?? 0)} pasos por 1.000 hab.`,
      ];
      const color = view === "none" ? "rgba(0, 0, 0, 0)" : binColor(value(r), scale.bounds, scale.colors);
      return r.place.polygon.map((ring) => ({ polygon: ring, color, popup, id: r.place.municipality }));
    });
  }, [rows, view, year]);

  return (
    <>
      <div className="segmented" role="group" aria-label="Color de los municipios">
        {(Object.keys(VIEWS) as View[]).map((v) => (
          <button key={v} type="button" aria-pressed={v === view} onClick={() => setView(v)}>
            {VIEWS[v].label}
          </button>
        ))}
      </div>
      <PointMap
        layers={stops}
        areas={areas}
        areaOpacity={0.55}
        outline
        focus={selected}
        onAreaSelect={onSelect}
        height={560}
      />
      {VIEWS[view].legend.length > 0 && (
        <div className="scale">
          {VIEWS[view].legend.map((label, i) => (
            <span key={label}>
              <span className="dot" style={{ background: VIEWS[view].colors[i] }} /> {label}
            </span>
          ))}
        </div>
      )}
    </>
  );
}
