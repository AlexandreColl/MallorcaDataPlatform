// The language of the page. It is fixed for the whole page load: the selector links to the same page in another
// language, so changing it loads the page again (ADR 0024). That is why it is a module value and not a React context:
// the number and date formats also run in ECharts formatters and map popups, outside React.

export const LOCALES = ["es", "ca", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "es";

/** The BCP 47 tag each language formats numbers and dates with. */
export const TAGS: Record<Locale, string> = { es: "es-ES", ca: "ca-ES", en: "en-GB" };

/** Each language named in itself, as the selector shows it. */
export const NATIVE_NAMES: Record<Locale, string> = { es: "Castellano", ca: "Català", en: "English" };

const STORAGE_KEY = "mdp-locale";

let active: Locale = DEFAULT_LOCALE;

/** The language of this page load. */
export function locale(): Locale {
  return active;
}

/** Sets the language of the page, and of `<html lang>` for screen readers, spelling and hyphenation. */
export function setLocale(next: Locale): void {
  active = next;
  document.documentElement.lang = next;
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** "/ca/movilidad" -> {locale: "ca", path: "/movilidad"}; "/movilidad" -> {locale: null, path: "/movilidad"}. */
export function splitPath(pathname: string): { locale: Locale | null; path: string } {
  const match = /^\/([a-z]{2})(?=\/|$)(.*)$/.exec(pathname);
  if (match && isLocale(match[1])) return { locale: match[1], path: match[2] || "/" };
  return { locale: null, path: pathname || "/" };
}

/** ("ca", "/movilidad") -> "/ca/movilidad"; ("ca", "/") -> "/ca/". */
export function localizedPath(language: Locale, path: string): string {
  return `/${language}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * The language of a link without one: the one chosen before with the selector, else the first of the browser's
 * languages that the web speaks ("ca-ES-valencia" is Catalan, "en-US" is English), else Spanish.
 */
export function preferredLocale(stored: string | null, languages: readonly string[]): Locale {
  if (isLocale(stored)) return stored;
  for (const tag of languages) {
    const primary = tag.toLowerCase().split("-")[0];
    if (isLocale(primary)) return primary;
  }
  return DEFAULT_LOCALE;
}

export function storedLocale(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode): follow the browser
  }
}

/** Remembers the language chosen with the selector, for the links that carry none. */
export function rememberLocale(language: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // not remembered, but the link still opens the page in that language
  }
}

/**
 * Takes the language from the address or, for an address without one (an old link, the bare domain), picks it and
 * rewrites the address so that it carries it: a link copied from the page always opens in the same language.
 */
export function startLocale(): Locale {
  const { pathname, search, hash } = window.location;
  const split = splitPath(pathname);
  const language = split.locale ?? preferredLocale(storedLocale(), navigator.languages ?? [navigator.language]);
  if (!split.locale) window.history.replaceState(null, "", `${localizedPath(language, split.path)}${search}${hash}`);
  setLocale(language);
  return language;
}
