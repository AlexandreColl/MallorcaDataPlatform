import { type ReactNode, useState } from "react";

import { Link } from "../router";
import { useTheme } from "../theme";
import { Icon, type IconName } from "./Icon";
import { Logo } from "./Logo";

export interface Dashboard {
  path: string;
  label: string;
  icon: IconName;
  title: string;
  description: string;
}

function ThemeButton() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "claro" : "oscuro";
  return (
    <button type="button" className="theme-button" onClick={toggle} aria-label={`Cambiar a modo ${next}`}>
      <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
      <span>Modo {next}</span>
    </button>
  );
}

/** The menu of dashboards on the left (a drawer on phones) and the page on the right. */
export function Layout({ dashboards, current, children, version }: {
  dashboards: Dashboard[];
  current: Dashboard;
  children: ReactNode;
  version: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`shell${open ? " menu-open" : ""}`}>
      <aside className="sidebar" aria-label="Dashboards">
        <Link to="/" className="brand" onClick={() => setOpen(false)}>
          <Logo size={30} />
          <span>
            Mallorca
            <small>Data Platform</small>
          </span>
        </Link>
        <nav className="nav">
          {dashboards.map((d) => (
            <Link key={d.path} to={d.path} className="nav-item" onClick={() => setOpen(false)}>
              <Icon name={d.icon} />
              {d.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          <ThemeButton />
          <nav className="links">
            <a href={`${window.location.protocol}//${window.location.hostname}:8000/docs`}>API</a>
            <a href="https://alexandrecoll.github.io/MallorcaDataPlatform/">Catálogo</a>
            <a href="https://github.com/AlexandreColl/MallorcaDataPlatform">GitHub</a>
          </nav>
          {version && <span className="version">v{version}</span>}
        </div>
      </aside>
      <button type="button" className="scrim" aria-label="Cerrar el menú" onClick={() => setOpen(false)} />

      <div className="content">
        <header className="mobile-bar">
          <button type="button" className="icon-button" aria-label="Abrir el menú" onClick={() => setOpen(true)}>
            <Icon name="menu" />
          </button>
          <Logo size={26} />
          <span className="mobile-title">{current.label}</span>
        </header>
        <main>
          <header className="page-header">
            <h1>{current.title}</h1>
            <p>{current.description}</p>
          </header>
          {children}
        </main>
        <footer className="footer">
          Datos abiertos de AEMET, SOCIB, EEA, REData, IGN, EMT, CTM, SEGITTUR, Govern de les Illes Balears y
          Open-Meteo. Mapa © OpenStreetMap.
        </footer>
      </div>
    </div>
  );
}

/** A card with a title, an optional subtitle and its content. */
export function Panel({ title, subtitle, children, wide, full }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  wide?: boolean;
  /** Spans the whole row. */
  full?: boolean;
}) {
  return (
    <section className={`card panel${wide ? " wide" : ""}${full ? " full" : ""}`}>
      <header className="panel-header">
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </header>
      {children}
    </section>
  );
}
