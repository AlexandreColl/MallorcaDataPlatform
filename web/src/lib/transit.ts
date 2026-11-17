import type { TransitRoute } from "../api";
import { messages } from "../i18n";
import { dayName, number } from "./format";

/** The kind of a line (GTFS route type) in words; another kind is shown by its code. */
export function kindLabel(kind: string): string {
  const names: Record<string, string> = messages().transit.kinds;
  return names[kind] ?? kind;
}

/** Width of a line on the map: proportional to the square root of its departures, from 1 to 5 px. */
export function routeWidth(trips: number | null, busiest: number): number {
  return 1 + 4 * Math.sqrt(Math.max(trips ?? 0, 0) / Math.max(busiest, 1));
}

/** The lines of the popup of a line: its name, network and kind, and its departures that day. */
export function routePopup(route: TransitRoute, network: string): string[] {
  const m = messages().transit;
  const trips =
    route.trips === null || route.local_date === null
      ? m.noTimetable
      : m.departuresOn(route.trips, number(route.trips), dayName(route.local_date));
  return [route.name, `${network} · ${kindLabel(route.kind)}`, trips];
}
