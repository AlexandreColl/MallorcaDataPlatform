import { useEffect } from "react";

import { api } from "./api";
import type { IconName } from "./components/Icon";
import { type Dashboard, Layout } from "./components/Layout";
import { type Messages, messages } from "./i18n";
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
const DASHBOARDS: { key: keyof Messages["dashboards"]; path: string; icon: IconName }[] = [
  { key: "home", path: "/", icon: "home" },
  { key: "tourism", path: "/turismo-y-recursos", icon: "tourism" },
  { key: "climate", path: "/clima-y-agua", icon: "water" },
  { key: "mobility", path: "/movilidad", icon: "mobility" },
  { key: "weather", path: "/tiempo-y-entorno", icon: "weather" },
  { key: "explorer", path: "/explorador", icon: "explore" },
  { key: "operations", path: "/operacion", icon: "operations" },
];

/** The dashboards with their names in the language of the page. The paths stay the same in every language. */
function dashboards(): Dashboard[] {
  const m = messages();
  return DASHBOARDS.map(({ key, path, icon }) => ({ path, icon, ...m.dashboards[key] }));
}

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
      return <Home dashboards={dashboards()} />;
  }
}

export default function App() {
  const path = usePath();
  const all = dashboards();
  const current = all.find((d) => d.path === path) ?? (all[0] as Dashboard);
  const health = useLoad(api.health);

  useEffect(() => {
    const name = messages().app.name;
    document.title = current.path === "/" ? name : `${current.label} · ${name}`;
  }, [current.path, current.label]);

  return (
    <Layout dashboards={all} current={current} version={ready(health)?.version ?? null}>
      {/* The key resets the page state, so each dashboard loads its own data when it is opened. */}
      <Page key={current.path} path={current.path} />
    </Layout>
  );
}
