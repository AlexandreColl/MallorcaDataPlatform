import { useCallback, useMemo, useState } from "react";

import { api, daysAgo, type MobilityDay, type Municipality, type PopulationYear, type StopService } from "../api";
import { Async, Table } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { type MapArea, type MapLayer, PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { compact, dayName, dayShort, number, signed } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { binColor, change, islandTotals, type Service, serviceByMunicipality } from "../lib/population";

/** The municipal register starts in 1996 (there was none in 1997). */
const FIRST_YEAR = 1996;
const PALMA = "07040";

const NETWORKS = {
  emt_palma: { label: "EMT Palma", detail: "autobuses urbanos de Palma", color: "#dc2626" },
  ctm: { label: "CTM", detail: "autobuses TIB, tren y metro de la isla", color: "#2563eb" },
} as const;

/** Key figures of the latest day of each network, with its daily trend. */
function mobilityKpis(days: MobilityDay[]): Kpi[] {
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
function populationKpis(rows: PopulationYear[], stops: StopService[]): Kpi[] {
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

type View = "density" | "service" | "growth";

const VIEWS: Record<View, { label: string; legend: string[]; bounds: number[]; colors: string[] }> = {
  density: {
    label: "Densidad",
    legend: ["< 25", "25-50", "50-100", "100-200", "200-500", "≥ 500 hab./km²"],
    bounds: [25, 50, 100, 200, 500],
    colors: ["#dcfce7", "#bbf7d0", "#86efac", "#4ade80", "#16a34a", "#14532d"],
  },
  service: {
    label: "Servicio por habitante",
    legend: ["< 50", "50-100", "100-200", "200-400", "400-800", "≥ 800 pasos por 1.000 hab."],
    bounds: [50, 100, 200, 400, 800],
    colors: ["#eff6ff", "#bfdbfe", "#93c5fd", "#60a5fa", "#2563eb", "#1e3a8a"],
  },
  growth: {
    label: "Crecimiento en 10 años",
    legend: ["< 0 %", "0-5 %", "5-10 %", "10-20 %", "20-30 %", "≥ 30 %"],
    bounds: [0, 0.05, 0.1, 0.2, 0.3],
    colors: ["#f87171", "#fde68a", "#d9f99d", "#86efac", "#22c55e", "#15803d"],
  },
};

interface MunicipalityRow {
  place: Municipality;
  latest: PopulationYear | undefined;
  growth: number | null;
  service: Service;
  perThousand: number | null;
}

/** One row per municipality: its latest register, the change in ten years and the service on the latest day. */
function municipalityRows(places: Municipality[], population: PopulationYear[], stops: StopService[], year: number) {
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

function MunicipalityMap({ rows, year }: { rows: MunicipalityRow[]; year: number }) {
  const [view, setView] = useState<View>("density");
  const { areas, layers } = useMemo(() => {
    const scale = VIEWS[view];
    const value = (r: MunicipalityRow) =>
      view === "density" ? (r.latest?.density_per_km2 ?? null) : view === "service" ? r.perThousand : r.growth;
    const areas: MapArea[] = rows.flatMap((r) =>
      r.place.polygon.map((ring) => ({ polygon: ring, color: binColor(value(r), scale.bounds, scale.colors) })),
    );
    const layers: MapLayer[] = [
      {
        id: "municipalities", label: "Municipios", color: "#0a120d", radius: 3,
        points: rows.map((r) => ({
          lat: r.place.lat, lon: r.place.lon,
          popup: [
            r.place.name,
            `${number(r.latest?.population ?? 0)} hab. · ${number(r.latest?.density_per_km2 ?? 0)} hab./km²`,
            r.growth === null ? "Sin dato de hace 10 años" : `${signed(r.growth * 100)} % desde ${year - 10}`,
            `${number(r.service.stops)} paradas · ${number(r.perThousand ?? 0)} pasos por 1.000 hab.`,
          ],
        })),
      },
    ];
    return { areas, layers };
  }, [rows, view, year]);

  return (
    <>
      <div className="segmented" role="group" aria-label="Indicador">
        {(Object.keys(VIEWS) as View[]).map((v) => (
          <button key={v} type="button" aria-pressed={v === view} onClick={() => setView(v)}>
            {VIEWS[v].label}
          </button>
        ))}
      </div>
      <PointMap layers={layers} areas={areas} height={480} />
      <div className="scale">
        {VIEWS[view].legend.map((label, i) => (
          <span key={label}>
            <span className="dot" style={{ background: VIEWS[view].colors[i] }} /> {label}
          </span>
        ))}
      </div>
    </>
  );
}

function PopulationHistory({ rows }: { rows: PopulationYear[] }) {
  const option = useCallback(() => {
    const totals = islandTotals(rows);
    const palma = new Map(rows.filter((r) => r.municipality === PALMA).map((r) => [r.year, r.population ?? 0]));
    return {
      xAxis: { type: "category", data: totals.map((t) => String(t.year)) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      tooltip: { valueFormatter: (v: number | null) => (v === null ? "—" : number(v)) },
      series: [
        { name: "Palma", type: "bar", stack: "island", color: "#15803d", data: totals.map((t) => palma.get(t.year) ?? null) },
        {
          name: "Resto de la isla", type: "bar", stack: "island", color: "#86efac",
          itemStyle: { borderRadius: [3, 3, 0, 0] },
          data: totals.map((t) => t.population - (palma.get(t.year) ?? 0)),
        },
      ],
    };
  }, [rows]);
  return <Chart option={option} label="Población de Mallorca a 1 de enero: Palma y el resto de la isla" height={320} />;
}

function DailyCalls({ days }: { days: MobilityDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(days.map((d) => d.local_date))].sort();
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      tooltip: { valueFormatter: (v: number | null) => (v === null ? "—" : number(v)) },
      series: (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).map((network) => ({
        name: NETWORKS[network].label, type: "bar", color: NETWORKS[network].color, barGap: "10%",
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        data: dates.map((date) => days.find((d) => d.network === network && d.local_date === date)?.scheduled_stop_calls ?? null),
      })),
    };
  }, [days]);
  return <Chart option={option} label="Pasos programados por día en cada red" height={320} />;
}

function stopLayers(stops: StopService[]): MapLayer[] {
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).map((network) => {
    const own = stops.filter((s) => s.network === network);
    const busiest = Math.max(1, ...own.map((s) => s.departures ?? 0));
    return {
      id: network, label: NETWORKS[network].label, color: NETWORKS[network].color, radius: 2.2,
      points: own.map((s) => ({
        lat: s.lat, lon: s.lon,
        // Area proportional to the departures: the radius grows with their square root.
        size: 0.5 + 2 * Math.sqrt((s.departures ?? 0) / busiest),
        popup: [s.stop, NETWORKS[network].label, `${number(s.departures ?? 0)} pasos · ${number(s.lines ?? 0)} líneas`],
      })),
    };
  });
}

export function Mobility() {
  const daily = useLoad(() => api.mobilityDaily(daysAgo(60)));
  const stops = useLoad(api.stops);
  const population = useLoad(() => api.population(FIRST_YEAR));
  const places = useLoad(api.municipalities);

  const kpis = useMemo(() => {
    const [d, s, p] = [ready(daily), ready(stops), ready(population)];
    return d && s && p ? [...populationKpis(p, s), ...mobilityKpis(d)] : null;
  }, [daily, stops, population]);
  const municipalities = useMemo(() => {
    const [m, p, s] = [ready(places), ready(population), ready(stops)];
    if (!m || !p || !s || p.length === 0) return null;
    const year = Math.max(...p.map((r) => r.year));
    return { rows: municipalityRows(m, p, s, year), year };
  }, [places, population, stops]);
  const layers = useMemo(() => (stops.status === "ready" ? stopLayers(stops.data) : []), [stops]);
  const stopDay = stops.status === "ready" && stops.data[0] ? dayName(stops.data[0].local_date) : "el último día";

  return (
    <>
      <KpiRow
        kpis={kpis}
        colors={["#15803d", "#15803d", NETWORKS.emt_palma.color, NETWORKS.ctm.color]}
      />
      <div className="grid">
        <Panel title="Servicio por parada" subtitle={`Pasos programados en cada parada el ${stopDay}: cuanto más grande, más servicio.`} wide>
          <Async state={stops} height={480}>{() => <PointMap layers={layers} />}</Async>
        </Panel>
        <Panel title="Paradas con más servicio" subtitle="Las diez con más pasos programados de las dos redes.">
          <Async state={stops}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 10)}
                columns={[
                  { label: "Parada", value: (s) => s.stop },
                  { label: "Red", value: (s) => NETWORKS[s.network].label },
                  { label: "Pasos", value: (s) => number(s.departures ?? 0), numeric: true },
                  { label: "Líneas", value: (s) => number(s.lines ?? 0), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title="Población y servicio por municipio"
          subtitle={`Padrón del INE a 1 de enero de ${municipalities?.year ?? "—"} y paradas de autobús, tren y metro de cada municipio; pulsa un municipio para ver sus cifras.`}
          wide
        >
          <Async state={places} height={520}>
            {() => (municipalities ? <MunicipalityMap rows={municipalities.rows} year={municipalities.year} /> : null)}
          </Async>
        </Panel>
        <Panel title="Municipios más poblados" subtitle="Habitantes, cambio en diez años y pasos programados por cada 1.000 habitantes.">
          <Async state={places}>
            {() =>
              municipalities ? (
                <Table
                  rows={municipalities.rows.slice(0, 12)}
                  columns={[
                    { label: "Municipio", value: (r) => r.place.name },
                    { label: "Hab.", value: (r) => number(r.latest?.population ?? 0), numeric: true },
                    { label: "10 años", value: (r) => (r.growth === null ? "—" : `${signed(r.growth * 100)} %`), numeric: true },
                    { label: "Pasos/1.000", value: (r) => (r.perThousand === null ? "—" : number(r.perThousand)), numeric: true },
                  ]}
                />
              ) : null
            }
          </Async>
        </Panel>
        <Panel title="Población de Mallorca desde 1996" subtitle="Suma de los municipios a 1 de enero (no hubo padrón en 1997)." wide>
          <Async state={population} height={320}>{(rows) => <PopulationHistory rows={rows} />}</Async>
        </Panel>
        <Panel title="Pasos programados por día" subtitle="Suma de los vehículos que pasan por cada parada, según los horarios GTFS." wide>
          <Async state={daily} height={320}>{(rows) => <DailyCalls days={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
