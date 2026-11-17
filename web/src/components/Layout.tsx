import { type MouseEvent, type ReactNode, useState } from "react";

import { LOCALES, type Locale, locale, localizedPath, messages, NATIVE_NAMES, rememberLocale } from "../i18n";
import { Link, usePath } from "../router";
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
  const m = messages().layout;
  const dark = theme === "dark";
  return (
    <button type="button" className="theme-button" onClick={toggle} aria-label={dark ? m.switchToLight : m.switchToDark}>
      <Icon name={dark ? "sun" : "moon"} size={18} />
      <span>{dark ? m.lightMode : m.darkMode}</span>
    </button>
  );
}

/** The same page, with its filters, in another language. */
function pageIn(language: Locale, path: string): string {
  return `${localizedPath(language, path)}${window.location.search}${window.location.hash}`;
}

/**
 * Links to the same page in each language, each named in itself. Changing language loads the page again: the texts
 * and formats are read once per load (ADR 0024). The choice is remembered for links that carry no language.
 */
function LanguageSelector() {
  const path = usePath();
  const current = locale();
  const choose = (language: Locale) => (event: MouseEvent<HTMLAnchorElement>) => {
    rememberLocale(language);
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    // The explorer keeps its filters in the query without rendering this again: read the address at the click.
    if (language !== current) window.location.assign(pageIn(language, path));
  };
  return (
    <nav className="languages" aria-label={messages().layout.language}>
      {LOCALES.map((language) => (
        <a
          key={language}
          href={pageIn(language, path)}
          lang={language}
          hrefLang={language}
          aria-current={language === current ? "true" : undefined}
          onClick={choose(language)}
        >
          {NATIVE_NAMES[language]}
        </a>
      ))}
    </nav>
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
  const m = messages().layout;
  return (
    <div className={`shell${open ? " menu-open" : ""}`}>
      <aside className="sidebar" aria-label={m.dashboards}>
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
          <LanguageSelector />
          <ThemeButton />
          <nav className="links">
            <a href={`${window.location.protocol}//${window.location.hostname}:8000/docs`}>API</a>
            <a href="https://alexandrecoll.github.io/MallorcaDataPlatform/">{m.catalogue}</a>
            <a href="https://github.com/AlexandreColl/MallorcaDataPlatform">GitHub</a>
          </nav>
          {version && <span className="version">v{version}</span>}
        </div>
      </aside>
      <button type="button" className="scrim" aria-label={m.closeMenu} onClick={() => setOpen(false)} />

      <div className="content">
        <header className="mobile-bar">
          <button type="button" className="icon-button" aria-label={m.openMenu} onClick={() => setOpen(true)}>
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
        <footer className="footer">{m.footer}</footer>
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
