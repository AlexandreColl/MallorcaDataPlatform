import { useMemo } from "react";

import { api, type Location } from "../api";
import { Async } from "../components/Async";
import { Icon } from "../components/Icon";
import { KpiRow } from "../components/KpiCard";
import { type Dashboard, Panel } from "../components/Layout";
import { type MapLayer, PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { number } from "../lib/format";
import { buildKpi, type Kpi, RAIN_SPEC, RESOURCE_SPECS } from "../lib/kpis";
import { Link } from "../router";

const KPI_COLORS = ["#0891b2", "#2563eb", "#d97706", "#7c3aed", "#dc2626"];

/** Three years of months for the sparklines, plus a margin for the series published late. */
export const SINCE_40_MONTHS = (() => {
  const date = new Date();
  date.setMonth(date.getMonth() - 40, 1);
  return date.toISOString().slice(0, 10);
})();

function placeLayers(locations: Location[]): MapLayer[] {
  const of = (kind: string) =>
    locations
      .filter((l) => l.kind === kind)
      .map((l) => ({
        lat: l.lat,
        lon: l.lon,
        popup: [l.entity, l.label ?? l.source, `${number(l.n_metrics)} ${l.n_metrics === 1 ? "métrica" : "métricas"}`],
      }));
  return [
    { id: "observation", label: "Estaciones oficiales", color: "#15803d", radius: 6, points: of("observation") },
    { id: "model", label: "Puntos de modelo", color: "#d97706", radius: 5, points: of("model") },
  ];
}

export function Home({ dashboards }: { dashboards: Dashboard[] }) {
  const resources = useLoad(() => api.resources(SINCE_40_MONTHS));
  const climate = useLoad(() => api.climate(SINCE_40_MONTHS));
  const locations = useLoad(api.locations);

  const kpis = useMemo(() => {
    const r = ready(resources);
    const c = ready(climate);
    if (!r || !c) return null;
    const [reserves, ...rest] = RESOURCE_SPECS.map((spec) => buildKpi(spec, r));
    return [reserves, buildKpi(RAIN_SPEC, c), ...rest].filter((k): k is Kpi => k !== null);
  }, [resources, climate]);

  const layers = useMemo(() => (locations.status === "ready" ? placeLayers(locations.data) : []), [locations]);

  return (
    <>
      <KpiRow kpis={kpis} colors={KPI_COLORS} />
      <div className="grid">
        <Panel title="Dónde se mide" subtitle="Estaciones oficiales del tiempo y del aire, y puntos del modelo meteorológico." wide>
          <Async state={locations} height={480}>
            {() => <PointMap layers={layers} />}
          </Async>
        </Panel>
        <Panel title="Dashboards" subtitle="Datos relacionados, agrupados por tema.">
          <ul className="dashboard-list">
            {dashboards.slice(1).map((d) => (
              <li key={d.path}>
                <Link to={d.path} className="dashboard-link">
                  <span className="dashboard-icon">
                    <Icon name={d.icon} />
                  </span>
                  <span>
                    <strong>{d.label}</strong>
                    <small>{d.description}</small>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
