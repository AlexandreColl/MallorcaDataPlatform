// The figures of the mobility page: key figures, the rows of the municipalities, the stop layers and subtitles.

import type { HumanPressureDay, MobilityDay, Municipality, PopulationYear, StopService, TouristDwellings, TransitRoute } from "../api";
import type { MapLayer } from "../components/PointMap";
import { messages } from "../i18n";
import { compact, dayName, dayShort, number, signed } from "./format";
import type { Kpi } from "./kpis";
import { busiestDay, change, islandTotals, type Service, serviceByMunicipality } from "./population";

/** The municipal register starts in 1996 (there was none in 1997). */
export const FIRST_YEAR = 1996;
export const PALMA = "07040";

export const NETWORKS = {
  emt_palma: { label: "EMT Palma", color: "#dc2626" },
  ctm: { label: "CTM", color: "#2563eb" },
} as const;

/** Key figures of the latest day of each network, with its daily trend. */
export function mobilityKpis(days: MobilityDay[]): Kpi[] {
  const m = messages().mobility;
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).flatMap((network) => {
    const rows = days.filter((d) => d.network === network && d.scheduled_stop_calls !== null);
    const latest = rows.at(-1);
    if (!latest) return [];
    const { label } = NETWORKS[network];
    const history = rows.map((d) => ({ month: d.local_date, value: d.scheduled_stop_calls as number }));
    // One figure per network, so the row of key figures stays on one line next to the two of population.
    const day = latest.is_weekend ? m.weekend : m.weekday;
    return [
      {
        id: `${network}-calls`, label: m.calls(label), value: compact(latest.scheduled_stop_calls as number),
        unit: "", month: `${dayName(latest.local_date)}, ${day}`,
        deviation: m.stopsWithService(number(latest.stops_with_service), number(latest.stops)),
        tone: "neutral", history,
      },
    ];
  });
}

/** Mallorca's population on 1 January and the scheduled departures per 1,000 inhabitants on the latest day. */
export function populationKpis(rows: PopulationYear[], stops: StopService[]): Kpi[] {
  const totals = islandTotals(rows);
  const latest = totals.at(-1);
  if (!latest) return [];
  const yearly = change(latest.population, totals.at(-2)?.population);
  const departures = stops.reduce((sum, s) => sum + (s.departures ?? 0), 0);
  const m = messages().mobility;
  return [
    {
      id: "population", label: m.population, value: number(latest.population), unit: m.inhabitants,
      month: dayName(`${latest.year}-01-01`),
      deviation: yearly === null ? null : m.inAYear(signed(yearly * 100)), tone: "neutral",
      history: totals.slice(-15).map((t) => ({ month: String(t.year), value: t.population })),
    },
    {
      id: "service-per-inhabitant", label: m.perThousand,
      value: number((departures / latest.population) * 1000), unit: "",
      month: stops[0] ? dayName(stops[0].local_date) : "",
      deviation: m.callsOfBoth(compact(departures)), tone: "neutral", history: [],
    },
  ];
}

export interface MunicipalityRow {
  place: Municipality;
  latest: PopulationYear | undefined;
  growth: number | null;
  service: Service;
  perThousand: number | null;
  // The latest count of tourist dwellings (INE), twice a year.
  dwellings: TouristDwellings | undefined;
}

/**
 * One row per municipality: its latest register, the change in ten years, the service on the latest day and the
 * tourist dwellings of the latest count.
 */
export function municipalityRows(
  places: Municipality[], population: PopulationYear[], stops: StopService[], year: number,
  dwellings: TouristDwellings[] = [],
) {
  const service = serviceByMunicipality(stops, places);
  const month = dwellings.reduce((last, d) => (d.reference_month > last ? d.reference_month : last), "");
  const counted = new Map(dwellings.filter((d) => d.reference_month === month).map((d) => [d.municipality, d]));
  const of = (code: string, y: number) => population.find((p) => p.municipality === code && p.year === y);
  return places
    .map((place): MunicipalityRow => {
      const latest = of(place.municipality, year);
      const own = service.get(place.municipality) ?? { stops: 0, departures: 0 };
      return {
        place, latest, service: own,
        growth: change(latest?.population, of(place.municipality, year - 10)?.population),
        perThousand: latest?.population ? (own.departures / latest.population) * 1000 : null,
        dwellings: counted.get(place.municipality),
      };
    })
    .sort((a, b) => (b.latest?.population ?? 0) - (a.latest?.population ?? 0));
}

/** The twelve most populated municipalities, and the selected one at the end when it is not among them. */
export function withSelected(rows: MunicipalityRow[], selected: string | null): MunicipalityRow[] {
  const top = rows.slice(0, 12);
  const extra = rows.find((r) => r.place.municipality === selected);
  return extra && !top.includes(extra) ? [...top, extra] : top;
}

/** "Datos hasta el 31 de agosto de 2026; máximo del año: 1.517.631 personas el 11 de agosto (1,58 por residente)." */
export function pressureSubtitle(days: HumanPressureDay[] | null): string {
  const m = messages().mobility;
  const last = days?.at(-1);
  if (!days || !last) return m.pressureIntro;
  const year = last.local_date.slice(0, 4);
  const peak = busiestDay(days.filter((d) => d.local_date.startsWith(year)));
  const ratio = peak?.pressure_ratio ? number(peak.pressure_ratio, 2) : null;
  const top = peak ? m.pressurePeak(year, number(peak.people_present), dayShort(peak.local_date), ratio) : null;
  return [m.pressureIntro, m.pressureUpTo(dayName(last.local_date)), top].filter(Boolean).join(" ");
}

/** Subtitle of the lines map: the day of the timetables. */
export function routesSubtitle(routes: TransitRoute[] | null): string {
  const day = routes?.find((r) => r.local_date)?.local_date;
  return messages().mobility.routesSubtitle(day ? dayName(day) : null);
}

export function stopLayers(stops: StopService[]): MapLayer[] {
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).map((network) => {
    const own = stops.filter((s) => s.network === network);
    const busiest = Math.max(1, ...own.map((s) => s.departures ?? 0));
    return {
      id: network, label: NETWORKS[network].label, color: NETWORKS[network].color, radius: 2.2,
      points: own.map((s) => ({
        lat: s.lat, lon: s.lon,
        // Area proportional to the departures: the radius grows with their square root.
        size: 0.5 + 2 * Math.sqrt((s.departures ?? 0) / busiest),
        popup: [s.name ?? s.stop, NETWORKS[network].label, messages().mobility.stopPopup(number(s.departures ?? 0), number(s.lines ?? 0))],
      })),
    };
  });
}
