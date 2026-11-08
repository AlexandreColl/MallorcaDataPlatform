import { useEffect } from "react";

import { api } from "./api";
import { type Dashboard, Layout } from "./components/Layout";
import { ready, useLoad } from "./hooks";
import { ClimateWater } from "./pages/ClimateWater";
import { Explorer } from "./pages/Explorer";
import { Home } from "./pages/Home";
import { Mobility } from "./pages/Mobility";
import { Operations } from "./pages/Operations";
import { Tourism } from "./pages/Tourism";
import { WeatherEnvironment } from "./pages/WeatherEnvironment";
import { usePath } from "./router";

/** The dashboards of the menu: each one groups data that belongs together, like the Grafana folders. */
const DASHBOARDS: Dashboard[] = [
  {
    path: "/", label: "Inicio", icon: "home", title: "Mallorca en datos",
    description: "Agua, clima, turismo y energía de la isla, comparados con lo normal para cada mes. Quince fuentes abiertas, con la calidad comprobada en cada carga.",
  },
  {
    path: "/turismo-y-recursos", label: "Turismo y recursos", icon: "tourism", title: "Turismo y recursos",
    description: "Cuántos turistas llegan cada mes y qué pasa a la vez con el agua y la electricidad.",
  },
  {
    path: "/clima-y-agua", label: "Clima y agua", icon: "water", title: "Clima y agua",
    description: "Reservas de los acuíferos, lluvia del año hidrológico y temperatura frente a lo normal.",
  },
  {
    path: "/movilidad", label: "Movilidad", icon: "mobility", title: "Movilidad",
    description: "Servicio programado de autobuses, tren y metro (EMT en Palma y CTM en toda la isla) frente a la población de cada municipio.",
  },
  {
    path: "/tiempo-y-entorno", label: "Tiempo y entorno", icon: "weather", title: "Tiempo y entorno",
    description: "Temperatura, calidad del aire, oleaje, episodios meteorológicos y sismos.",
  },
  {
    path: "/explorador", label: "Explorador", icon: "explore", title: "Explorador de series",
    description: "Cualquier serie de la plataforma día a día: fuente, métrica y estación, con su calidad y sus anomalías.",
  },
  {
    path: "/operacion", label: "Operación", icon: "operations", title: "Operación de la plataforma",
    description: "Estado de cada fuente, reglas de calidad, anomalías detectadas y correcciones propuestas.",
  },
];

function Page({ path }: { path: string }) {
  switch (path) {
    case "/turismo-y-recursos":
      return <Tourism />;
    case "/clima-y-agua":
      return <ClimateWater />;
    case "/movilidad":
      return <Mobility />;
    case "/tiempo-y-entorno":
      return <WeatherEnvironment />;
    case "/explorador":
      return <Explorer />;
    case "/operacion":
      return <Operations />;
    default:
      return <Home dashboards={DASHBOARDS} />;
  }
}

export default function App() {
  const path = usePath();
  const current = DASHBOARDS.find((d) => d.path === path) ?? (DASHBOARDS[0] as Dashboard);
  const health = useLoad(api.health);

  useEffect(() => {
    document.title = current.path === "/" ? "Mallorca en datos" : `${current.label} · Mallorca en datos`;
  }, [current]);

  return (
    <Layout dashboards={DASHBOARDS} current={current} version={ready(health)?.version ?? null}>
      {/* The key resets the page state, so each dashboard loads its own data when it is opened. */}
      <Page key={current.path} path={current.path} />
    </Layout>
  );
}
