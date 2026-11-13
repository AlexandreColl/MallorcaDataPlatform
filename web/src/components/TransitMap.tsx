import { useMemo, useState } from "react";

import type { TransitRoute } from "../api";
import { NETWORKS } from "../lib/mobility";
import { routePopup, routeWidth } from "../lib/transit";
import { type MapRoute, PointMap } from "./PointMap";

type NetworkFilter = "all" | keyof typeof NETWORKS;

/** Every line of both networks in its operator's colour, wider the more departures it has; filtered by network. */
export function TransitMap({ routes }: { routes: TransitRoute[] }) {
  const [network, setNetwork] = useState<NetworkFilter>("all");
  const lines = useMemo((): MapRoute[] => {
    const shown = routes.filter((r) => network === "all" || r.network === network);
    const busiest = Math.max(0, ...shown.map((r) => r.trips ?? 0));
    return shown.map((r) => ({
      lines: r.geometry.coordinates,
      color: r.color ?? NETWORKS[r.network].color,
      width: routeWidth(r.trips, busiest),
      popup: routePopup(r, NETWORKS[r.network].label),
    }));
  }, [routes, network]);
  const filters: [NetworkFilter, string][] = [["all", "Las dos redes"], ["emt_palma", NETWORKS.emt_palma.label], ["ctm", NETWORKS.ctm.label]];

  return (
    <>
      <div className="segmented" role="group" aria-label="Red de transporte">
        {filters.map(([value, label]) => (
          <button key={value} type="button" aria-pressed={value === network} onClick={() => setNetwork(value)}>
            {label}
          </button>
        ))}
      </div>
      <PointMap layers={[]} routes={lines} height={560} />
    </>
  );
}
