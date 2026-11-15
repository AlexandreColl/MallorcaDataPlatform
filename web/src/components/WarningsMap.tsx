import { useMemo, useState } from "react";

import type { WarningZone, WeatherWarning } from "../api";
import { localTime } from "../lib/environment";
import { describe, LEVELS, overlapping, zoneLevels } from "../lib/warnings";
import { type MapArea, type MapLayer, PointMap } from "./PointMap";

const WARNING_PERIODS = {
  now: { label: "Ahora", hours: 1 },
  next: { label: "Próximas 72 h", hours: 72 },
} as const;

type WarningPeriod = keyof typeof WARNING_PERIODS;

/**
 * The AEMET warning zones of Mallorca coloured by their highest level in the period, with the warnings listed by
 * zone in the popup of each one.
 */
export function WarningsMap({ zones, warnings }: { zones: WarningZone[]; warnings: WeatherWarning[] }) {
  const [period, setPeriod] = useState<WarningPeriod>("next");
  const { areas, layers, active } = useMemo(() => {
    const now = new Date();
    const active = overlapping(warnings, now, new Date(now.getTime() + WARNING_PERIODS[period].hours * 3_600_000));
    const levels = zoneLevels(active);
    // Coastal waters first, so the land zones are drawn over them.
    const ordered = [...zones].sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "coast" ? -1 : 1));
    const areas: MapArea[] = ordered.map((z) => ({ polygon: z.polygon, color: LEVELS[levels.get(z.zone) ?? 0]?.color ?? "#4ade80" }));
    const layers: MapLayer[] = [
      {
        id: "zones", label: "Zonas", color: "#0a120d", radius: 4,
        points: zones.filter((z) => z.kind === "land").map((z) => {
          // A land zone and its coastal waters (same code with a C) share the popup.
          const own = active.filter((w) => w.zone === z.zone || w.zone === `${z.zone}C`);
          const [lon, lat] = z.polygon.reduce(
            ([x, y], [px, py]) => [x + px / z.polygon.length, y + py / z.polygon.length],
            [0, 0],
          );
          const lines = own.map((w) => `${describe(w)}${w.zone_kind === "coast" ? " (costa)" : ""} · ${localTime(w.start_ts)}`);
          return {
            lat, lon, color: LEVELS[levels.get(z.zone) ?? 0]?.color,
            popup: [z.name, ...(lines.length ? lines : ["Sin avisos"])],
          };
        }),
      },
    ];
    return { areas, layers, active };
  }, [zones, warnings, period]);

  return (
    <>
      <div className="segmented" role="group" aria-label="Periodo">
        {(Object.keys(WARNING_PERIODS) as WarningPeriod[]).map((p) => (
          <button key={p} type="button" aria-pressed={p === period} onClick={() => setPeriod(p)}>
            {WARNING_PERIODS[p].label}
          </button>
        ))}
      </div>
      <PointMap layers={layers} areas={areas} height={420} />
      <div className="scale">
        {LEVELS.map((l) => (
          <span key={l.label}>
            <span className="dot" style={{ background: l.color }} /> {l.label}
          </span>
        ))}
        <span>{active.length === 0 ? "Ningún aviso en el periodo" : `${active.length} avisos en el periodo`}</span>
      </div>
    </>
  );
}
