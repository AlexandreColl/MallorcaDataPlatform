// The figures of the mobility page: key figures, the rows of the municipalities, the stop layers and subtitles.

import type { HumanPressureDay, MobilityDay, Municipality, PopulationYear, StopService, TransitRoute } from "../api";
import type { MapLayer } from "../components/PointMap";
import { compact, dayName, dayShort, number, signed } from "./format";
import type { Kpi } from "./kpis";
import { busiestDay, change, islandTotals, type Service, serviceByMunicipality } from "./population";

/** The municipal register starts in 1996 (there was none in 1997). */
export const FIRST_YEAR = 1996;
export const PALMA = "07040";

export const NETWORKS = {
  emt_palma: { label: "EMT Palma", detail: "autobuses urbanos de Palma", color: "#dc2626" },
  ctm: { label: "CTM", detail: "autobuses TIB, tren y metro de la isla", color: "#2563eb" },
} as const;

/** Key figures of the latest day of each network, with its daily trend. */
export function mobilityKpis(days: MobilityDay[]): Kpi[] {
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).flatMap((network) => {
    const rows = days.filter((d) => d.network === network && d.scheduled_stop_calls !== null);
    const latest = rows.at(-1);
    if (!latest) return [];
    const { label } = NETWORKS[network];
    const history = rows.map((d) => ({ month: d.local_date, value: d.scheduled_stop_calls as number }));
    // One figure per network, so the row of key figures stays on one line next to the two of population.
    const day = latest.is_weekend ? "fin de semana" : "laborable";
    return [
      {
        id: `${network}-calls`, label: `${label} · pasos programados`, value: compact(latest.scheduled_stop_calls as number),
        unit: "", month: `${dayName(latest.local_date)}, ${day}`,
        deviation: `${number(latest.stops_with_service)} de ${number(latest.stops)} paradas con servicio`,
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
  return [
    {
      id: "population", label: "Población de Mallorca", value: number(latest.population), unit: "hab.",
      month: `1 de enero de ${latest.year}`,
      deviation: yearly === null ? null : `${signed(yearly * 100)} % en un año`, tone: "neutral",
      history: totals.slice(-15).map((t) => ({ month: String(t.year), value: t.population })),
    },
    {
      id: "service-per-inhabitant", label: "Pasos por 1.000 habitantes",
      value: number((departures / latest.population) * 1000), unit: "",
      month: stops[0] ? dayName(stops[0].local_date) : "",
      deviation: `${compact(departures)} pasos de EMT y CTM`, tone: "neutral", history: [],
    },
  ];
}

export interface MunicipalityRow {
  place: Municipality;
  latest: PopulationYear | undefined;
  growth: number | null;
  service: Service;
  perThousand: number | null;
}

/** One row per municipality: its latest register, the change in ten years and the service on the latest day. */
export function municipalityRows(places: Municipality[], population: PopulationYear[], stops: StopService[], year: number) {
  const service = serviceByMunicipality(stops, places);
  const of = (code: string, y: number) => population.find((p) => p.municipality === code && p.year === y);
  return places
    .map((place): MunicipalityRow => {
      const latest = of(place.municipality, year);
      const own = service.get(place.municipality) ?? { stops: 0, departures: 0 };
      return {
        place, latest, service: own,
        growth: change(latest?.population, of(place.municipality, year - 10)?.population),
        perThousand: latest?.population ? (own.departures / latest.population) * 1000 : null,
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
  const intro = "Residentes más visitantes en la isla cada día (Indicador de Presión Humana del Ibestat), los últimos tres años.";
  const last = days?.at(-1);
  if (!days || !last) return intro;
  const year = last.local_date.slice(0, 4);
  const peak = busiestDay(days.filter((d) => d.local_date.startsWith(year)));
  const ratio = peak?.pressure_ratio ? ` (${number(peak.pressure_ratio, 2)} por residente)` : "";
  const top = peak ? ` Máximo de ${year}: ${number(peak.people_present)} personas el ${dayShort(peak.local_date)}${ratio}.` : "";
  return `${intro} Datos hasta el ${dayName(last.local_date)}: el Ibestat publica con unos dos meses de retraso.${top}`;
}

/** Subtitle of the lines map: the day of the timetables. */
export function routesSubtitle(routes: TransitRoute[] | null): string {
  const day = routes?.find((r) => r.local_date)?.local_date;
  const when = day ? `el ${dayName(day)}` : "el último día";
  return `Recorrido de cada línea con el color de su operador; cuanto más gruesa, más salidas tiene ${when}. Pulsa una línea para ver sus cifras.`;
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
        popup: [s.name ?? s.stop, NETWORKS[network].label, `${number(s.departures ?? 0)} pasos · ${number(s.lines ?? 0)} líneas`],
      })),
    };
  });
}
