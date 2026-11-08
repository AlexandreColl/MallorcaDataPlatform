import type { TransitRoute } from "../api";
import { dayName, number } from "./format";

/** Spanish names of the kinds of line (GTFS route types). */
export const KINDS: Record<string, string> = { bus: "autobús", train: "tren", metro: "metro", tram: "tranvía" };

/** Width of a line on the map: proportional to the square root of its departures, from 1 to 5 px. */
export function routeWidth(trips: number | null, busiest: number): number {
  return 1 + 4 * Math.sqrt(Math.max(trips ?? 0, 0) / Math.max(busiest, 1));
}

/** The lines of the popup of a line: its name, network and kind, and its departures that day. */
export function routePopup(route: TransitRoute, network: string): string[] {
  const trips =
    route.trips === null || route.local_date === null
      ? "Sin horario el último día"
      : `${number(route.trips)} ${route.trips === 1 ? "salida" : "salidas"} el ${dayName(route.local_date)}`;
  return [route.name, `${network} · ${KINDS[route.kind] ?? route.kind}`, trips];
}
