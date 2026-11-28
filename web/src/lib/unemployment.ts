// Registered unemployment (SEPE) on the tourism page and the mobility map: how it moves with the visitors, how
// seasonal it is and the line of each municipality's card.

import type { MunicipalUnemployment, ResourcesMonth, UnemploymentSeasonality } from "../api";
import { messages } from "../i18n";
import { monthName, number } from "./format";
import { type Correlation, deseasonalize, pearson } from "./stats";

export interface PairCorrelation {
  raw: Correlation | null;
  deseasonalized: Correlation | null;
}

/** Pearson's r of the raw months and of the months without their yearly cycle. */
function pair(rows: ResourcesMonth[], xs: (number | null)[], ys: (number | null)[]): PairCorrelation {
  const months = rows.map((r) => r.month);
  return { raw: pearson(xs, ys), deseasonalized: pearson(deseasonalize(months, xs), deseasonalize(months, ys)) };
}

/**
 * Unemployment against international tourists, Palma airport passengers and cruise passengers. The raw r is strongly
 * negative because both follow the season; without the cycle it says whether a busier summer means less unemployment.
 */
export function unemploymentCorrelations(rows: ResourcesMonth[]) {
  const unemployed = rows.map((r) => r.unemployed);
  return {
    tourists: pair(rows, rows.map((r) => r.international_tourists), unemployed),
    airport: pair(rows, rows.map((r) => r.airport_passengers), unemployed),
    cruises: pair(rows, rows.map((r) => r.cruise_passengers), unemployed),
  };
}

/** The latest year with a winter/summer ratio, as "2025: 1,14". */
export function latestSeasonality(rows: UnemploymentSeasonality[]): string | null {
  const latest = rows.filter((r) => r.area === "mallorca" && r.winter_summer_ratio !== null).at(-1);
  return latest ? `${latest.year}: ${number(latest.winter_summer_ratio as number, 2)}` : null;
}

/** The latest month of every municipality (the newest month of the answer), by INE code. */
export function latestByMunicipality(rows: MunicipalUnemployment[]): Map<string, MunicipalUnemployment> {
  const month = rows.reduce((last, r) => (r.month > last ? r.month : last), "");
  return new Map(rows.filter((r) => r.month === month).map((r) => [r.municipality, r]));
}

/** The unemployment line of a municipality's card on the map: a suppressed total ("<5") is never shown as 5. */
export function unemploymentLine(row: MunicipalUnemployment | undefined): string {
  const m = messages().mobility;
  if (!row) return m.noUnemployment;
  if (row.is_suppressed) return m.placeSuppressed(monthName(row.month));
  if (row.unemployed == null) return m.noUnemployment;
  return m.placeUnemployment(
    number(row.unemployed),
    number(row.unemployed_per_1000_inhabitants ?? 0, 1),
    monthName(row.month),
  );
}
