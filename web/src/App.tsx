import { useMemo } from "react";

import { api } from "./api";
import { KpiCard, KpiSkeleton } from "./components/KpiCard";
import { SourceList } from "./components/SourceList";
import { SourceMap } from "./components/SourceMap";
import { useLoad } from "./hooks";
import { buildKpi, type Kpi, RAIN_SPEC, RESOURCE_SPECS } from "./lib/kpis";
import { sourceState } from "./lib/sources";

/** The first month the sparklines need: three years back, plus a margin for the series published late. */
function since(): string {
  const date = new Date();
  date.setMonth(date.getMonth() - 40, 1);
  return date.toISOString().slice(0, 10);
}

async function loadKpis(): Promise<Kpi[]> {
  const from = since();
  const [resources, climate] = await Promise.all([api.resources(from), api.climate(from)]);
  const [reserves, ...rest] = RESOURCE_SPECS.map((spec) => buildKpi(spec, resources));
  return [reserves, buildKpi(RAIN_SPEC, climate), ...rest].filter((kpi): kpi is Kpi => kpi !== null);
}

export default function App() {
  const kpis = useLoad(loadKpis);
  const sources = useLoad(api.sources);
  const locations = useLoad(api.locations);
  const health = useLoad(api.health);

  const upToDate = useMemo(() => {
    if (sources.status !== "ready") return null;
    const active = sources.data.filter((s) => sourceState(s) !== "inactive");
    return { ok: active.filter((s) => sourceState(s) === "ok").length, total: active.length };
  }, [sources]);

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          <span>Mallorca Data Platform</span>
        </div>
        {upToDate && (
          <span className={`pill ${upToDate.ok === upToDate.total ? "pill-ok" : "pill-warn"}`}>
            <span className="pill-dot" />
            {upToDate.ok} de {upToDate.total} fuentes al día
          </span>
        )}
      </header>

      <main>
        <section className="hero">
          <h1>Mallorca en datos</h1>
          <p>
            Agua, clima, turismo y energía de la isla, mes a mes y comparados con lo normal para cada mes. Doce
            fuentes abiertas, cargadas cada día y con la calidad comprobada.
          </p>
        </section>

        <section className="kpis" aria-label="Cifras clave">
          {kpis.status === "loading" && Array.from({ length: 5 }, (_, i) => <KpiSkeleton key={i} />)}
          {kpis.status === "error" && <p className="error">No se pudieron cargar las cifras: {kpis.error}</p>}
          {kpis.status === "ready" && kpis.data.map((kpi) => <KpiCard key={kpi.id} kpi={kpi} />)}
        </section>

        <section className="grid">
          <div className="card panel map-panel">
            <header className="panel-header">
              <h2>Dónde se mide</h2>
              <p>Estaciones oficiales, puntos de modelo y paradas de transporte. Pulsa un punto para ver qué mide.</p>
            </header>
            {locations.status === "ready" && <SourceMap locations={locations.data} />}
            {locations.status === "loading" && <div className="map skeleton" />}
            {locations.status === "error" && <p className="error">No se pudo cargar el mapa: {locations.error}</p>}
          </div>

          <div className="card panel">
            <header className="panel-header">
              <h2>Fuentes</h2>
              <p>Estado de la última carga de cada una.</p>
            </header>
            {sources.status === "ready" && <SourceList sources={sources.data} />}
            {sources.status === "loading" && <div className="list skeleton" />}
            {sources.status === "error" && <p className="error">No se pudieron cargar las fuentes: {sources.error}</p>}
          </div>
        </section>
      </main>

      <footer className="footer">
        <span>
          Datos abiertos de AEMET, SOCIB, EEA, REData, IGN, EMT, CTM, SEGITTUR, Govern de les Illes Balears y
          Open-Meteo.
        </span>
        <nav>
          <a href={`${window.location.protocol}//${window.location.hostname}:8000/docs`}>API</a>
          <a href="https://alexandrecoll.github.io/MallorcaDataPlatform/">Catálogo de datos</a>
          <a href="https://github.com/AlexandreColl/MallorcaDataPlatform">GitHub</a>
          {health.status === "ready" && <span className="version">v{health.data.version}</span>}
        </nav>
      </footer>
    </>
  );
}
