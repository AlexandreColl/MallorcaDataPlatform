// Number and date formats in the language of the page, with Intl: "1.234,5" and "4 d’ag." in Catalan, "1,234.5"
// and "4 Aug" in English. The formatters are built once per language and options, since charts call them often.

import { locale, messages, TAGS } from "../i18n";

const numberFormats = new Map<string, Intl.NumberFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

function dateFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale()}|${JSON.stringify(options)}`;
  let format = dateFormats.get(key);
  if (!format) {
    // The dates are calendar days ("2026-11-04"): read and written in UTC, so that no time zone moves them a day.
    format = new Intl.DateTimeFormat(TAGS[locale()], { timeZone: "UTC", ...options });
    dateFormats.set(key, format);
  }
  return format;
}

/** "2026-11-04" (or "2026-11-04T10:00:00Z") -> that calendar day at midnight UTC. */
function utcDay(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1));
}

export function number(value: number, digits = 0): string {
  const key = `${locale()}|${digits}`;
  let format = numberFormats.get(key);
  if (!format) {
    format = new Intl.NumberFormat(TAGS[locale()], { minimumFractionDigits: digits, maximumFractionDigits: digits });
    numberFormats.set(key, format);
  }
  return format.format(value);
}

/**
 * A tooltip value formatter that shows "—" for a missing value. ECharts passes `undefined` (not `null`) for an empty
 * month, and a formatter that throws stops the tooltip from updating until the page reloads.
 */
export function orDash(format: (value: number) => string): (value: unknown) => string {
  return (value) => (typeof value === "number" && Number.isFinite(value) ? format(value) : "—");
}

/** 2.596.458 -> "2,6 M"; 61.950 -> "62 mil" ("62 k" in English); 619,5 -> "620". */
export function compact(value: number): string {
  const { thousands, millions } = messages().format;
  if (Math.abs(value) >= 1e6) return `${number(value / 1e6, 1)} ${millions}`;
  if (Math.abs(value) >= 1e4) return `${number(value / 1e3, 0)} ${thousands}`;
  return number(value, value < 100 ? 1 : 0);
}

/** A signed value with an explicit plus: "+2,1", "−11,5". */
export function signed(value: number, digits = 1): string {
  const text = number(Math.abs(value), digits);
  if (value > 0) return `+${text}`;
  if (value < 0) return `−${text}`;
  return text;
}

/** "2026-08-01" -> "agosto de 2026", "agost del 2026", "August 2026". */
export function monthName(isoMonth: string): string {
  return dateFormat({ month: "long", year: "numeric" }).format(utcDay(isoMonth));
}

/** "2026-08-01" -> "ago 26", "ag. 26", "Aug 26": short enough for a chart axis. */
export function monthShort(isoMonth: string): string {
  return `${dateFormat({ month: "short" }).format(utcDay(isoMonth))} ${isoMonth.slice(2, 4)}`;
}

/** "2026-11-04" -> "4 nov", "4 de nov.", "4 Nov". */
export function dayShort(isoDay: string): string {
  return dateFormat({ day: "numeric", month: "short" }).format(utcDay(isoDay));
}

/** "2026-11-04" -> "4 de noviembre de 2026", "4 de novembre del 2026", "4 November 2026". */
export function dayName(isoDay: string): string {
  return dateFormat({ dateStyle: "long" }).format(utcDay(isoDay));
}

/** Age of a value in words: "hace 3 h", "fa 5 dies", "5 days ago". */
export function age(hours: number): string {
  if (hours < 1) return messages().format.lessThanAnHourAgo;
  const tag = TAGS[locale()];
  if (hours < 48) return new Intl.RelativeTimeFormat(tag, { style: "short" }).format(-Math.round(hours), "hour");
  const relative = new Intl.RelativeTimeFormat(tag);
  const days = Math.round(hours / 24);
  if (days < 60) return relative.format(-days, "day");
  const months = Math.round(days / 30);
  if (months < 24) return relative.format(-months, "month");
  return relative.format(-Math.round(days / 365), "year");
}

/**
 * The name of a stop or station: the one its source publishes or, for identifiers that already read as a name
 * (`sa_pobla`, `palma`), the identifier with spaces and a capital.
 */
export function placeName(id: string, name?: string | null): string {
  if (name) return name;
  const text = id.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
