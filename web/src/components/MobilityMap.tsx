import { useMemo, useState } from "react";

import { messages } from "../i18n";
import { number, signed } from "../lib/format";
import type { MunicipalityRow } from "../lib/mobility";
import { binColor } from "../lib/population";
import { type MapArea, type MapLayer, PointMap } from "./PointMap";

type View = "density" | "service" | "growth" | "none";

/** The legends are functions: their last entry names the unit in the language of the page. */
const VIEWS: Record<View, { legend: () => string[]; bounds: number[]; colors: string[] }> = {
  density: {
    legend: () => ["< 25", "25-50", "50-100", "100-200", "200-500", messages().mobility.densityTop],
    bounds: [25, 50, 100, 200, 500],
    colors: ["#dcfce7", "#bbf7d0", "#86efac", "#4ade80", "#16a34a", "#14532d"],
  },
  service: {
    legend: () => ["< 50", "50-100", "100-200", "200-400", "400-800", messages().mobility.serviceTop],
    bounds: [50, 100, 200, 400, 800],
    // Violet, not blue: the CTM stops are blue.
    colors: ["#f5f3ff", "#ddd6fe", "#c4b5fd", "#a78bfa", "#7c3aed", "#4c1d95"],
  },
  growth: {
    legend: () => ["< 0 %", "0-5 %", "5-10 %", "10-20 %", "20-30 %", "≥ 30 %"],
    bounds: [0, 0.05, 0.1, 0.2, 0.3],
    colors: ["#f87171", "#fde68a", "#d9f99d", "#86efac", "#22c55e", "#15803d"],
  },
  // Only the borders, so the stops stand out on the basemap.
  none: { legend: () => [], bounds: [], colors: [] },
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
  const m = messages().mobility;
  const areas = useMemo(() => {
    const scale = VIEWS[view];
    const value = (r: MunicipalityRow) =>
      view === "density" ? (r.latest?.density_per_km2 ?? null) : view === "service" ? r.perThousand : r.growth;
    return rows.flatMap((r): MapArea[] => {
      const popup = [
        r.place.name,
        m.placePopulation(number(r.latest?.population ?? 0), number(r.latest?.density_per_km2 ?? 0)),
        r.growth === null ? m.noGrowth : m.growthSince(signed(r.growth * 100), year - 10),
        m.placeService(number(r.service.stops), number(r.perThousand ?? 0)),
      ];
      const color = view === "none" ? "rgba(0, 0, 0, 0)" : binColor(value(r), scale.bounds, scale.colors);
      return r.place.polygon.map((ring) => ({ polygon: ring, color, popup, id: r.place.municipality }));
    });
  }, [rows, view, year, m]);

  return (
    <>
      <div className="segmented" role="group" aria-label={m.colourBy}>
        {(Object.keys(VIEWS) as View[]).map((v) => (
          <button key={v} type="button" aria-pressed={v === view} onClick={() => setView(v)}>
            {m.views[v]}
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
      {VIEWS[view].legend().length > 0 && (
        <div className="scale">
          {VIEWS[view].legend().map((label, i) => (
            <span key={label}>
              <span className="dot" style={{ background: VIEWS[view].colors[i] }} /> {label}
            </span>
          ))}
        </div>
      )}
    </>
  );
}
