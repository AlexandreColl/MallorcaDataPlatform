import { useCallback, useMemo, useState } from "react";

import { api, daysAgo, type MobilityDay, type Municipality, type PopulationYear, type StopService } from "../api";
import { Async, Table } from "../components/Async";
import { Chart, type ChartColors } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { type MapArea, type MapLayer, PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { compact, dayName, dayShort, number, orDash, signed } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { binColor, change, islandTotals, type Service, serviceByMunicipality } from "../lib/population";
import { segmentedTrend } from "../lib/stats";

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

type View = "density" | "service" | "growth" | "none";

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
    // Violet, not blue: the CTM stops are blue.
    colors: ["#f5f3ff", "#ddd6fe", "#c4b5fd", "#a78bfa", "#7c3aed", "#4c1d95"],
  },
  growth: {
    label: "Crecimiento en 10 años",
    legend: ["< 0 %", "0-5 %", "5-10 %", "10-20 %", "20-30 %", "≥ 30 %"],
    bounds: [0, 0.05, 0.1, 0.2, 0.3],
    colors: ["#f87171", "#fde68a", "#d9f99d", "#86efac", "#22c55e", "#15803d"],
  },
  // Only the borders, so the stops stand out on the basemap.
  none: { label: "Sin colorear", legend: [], bounds: [], colors: [] },
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

/**
 * One map for both: the municipalities coloured by the chosen figure, with the stops of each network on top (sized
 * by their departures and toggled from the legend). A click on a stop shows the stop; anywhere else, the municipality.
 */
function MobilityMap({ rows, stops, year, selected, onSelect }: {
  rows: MunicipalityRow[];
  stops: MapLayer[];
  year: number;
  selected: string | null;
  onSelect: (code: string) => void;
}) {
  const [view, setView] = useState<View>("density");
  const areas = useMemo(() => {
    const scale = VIEWS[view];
    const value = (r: MunicipalityRow) =>
      view === "density" ? (r.latest?.density_per_km2 ?? null) : view === "service" ? r.perThousand : r.growth;
    return rows.flatMap((r): MapArea[] => {
      const popup = [
        r.place.name,
        `${number(r.latest?.population ?? 0)} hab. · ${number(r.latest?.density_per_km2 ?? 0)} hab./km²`,
        r.growth === null ? "Sin dato de hace 10 años" : `${signed(r.growth * 100)} % desde ${year - 10}`,
        `${number(r.service.stops)} paradas · ${number(r.perThousand ?? 0)} pasos por 1.000 hab.`,
      ];
      const color = view === "none" ? "rgba(0, 0, 0, 0)" : binColor(value(r), scale.bounds, scale.colors);
      return r.place.polygon.map((ring) => ({ polygon: ring, color, popup, id: r.place.municipality }));
    });
  }, [rows, view, year]);

  return (
    <>
      <div className="segmented" role="group" aria-label="Color de los municipios">
        {(Object.keys(VIEWS) as View[]).map((v) => (
          <button key={v} type="button" aria-pressed={v === view} onClick={() => setView(v)}>
            {VIEWS[v].label}
          </button>
        ))}
      </div>
      <PointMap
        layers={stops}
        areas={areas}
        areaOpacity={0.55}
        outline
        focus={selected}
        onAreaSelect={onSelect}
        height={560}
      />
      {VIEWS[view].legend.length > 0 && (
        <div className="scale">
          {VIEWS[view].legend.map((label, i) => (
            <span key={label}>
              <span className="dot" style={{ background: VIEWS[view].colors[i] }} /> {label}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

/** The trend is carried on to this year, with its 95 % prediction interval. */
const PROJECTION_YEAR = 2030;

interface HistoryProps {
  rows: PopulationYear[];
  places: Municipality[];
  selected: string | null;
  onSelect: (code: string | null) => void;
}

/**
 * Population on 1 January since 1996, of the island (Palma and the rest) or of one municipality, with its trend in
 * one or two stretches and the last one carried on to 2030.
 */
function PopulationHistory({ rows, places, selected, onSelect }: HistoryProps) {
  const place = places.find((p) => p.municipality === selected);
  const option = useCallback((c: ChartColors) => {
    const series: { year: number; value: number }[] = place
      ? rows
          .filter((r) => r.municipality === place.municipality && r.population !== null)
          .map((r) => ({ year: r.year, value: r.population as number }))
          .sort((a, b) => a.year - b.year)
      : islandTotals(rows).map((t) => ({ year: t.year, value: t.population }));
    const years = series.map((s) => s.year);
    const last = years.at(-1) ?? PROJECTION_YEAR;
    const ahead = Array.from({ length: Math.max(0, PROJECTION_YEAR - last) }, (_, i) => last + 1 + i);
    const categories = [...years, ...ahead];
    const trends = segmentedTrend(series);
    const latest = trends.at(-1);
    const projected = (year: number) => year >= last && latest !== undefined;
    const band = categories.map((year) => (projected(year) ? latest?.interval(year) : undefined));
    const value = new Map(series.map((s) => [s.year, s.value]));
    const palma = new Map(rows.filter((r) => r.municipality === PALMA).map((r) => [r.year, r.population ?? 0]));
    const bars = place
      ? [
          {
            name: place.name, type: "bar", color: "#15803d", itemStyle: { borderRadius: [3, 3, 0, 0] },
            data: categories.map((year) => value.get(year) ?? null),
          },
        ]
      : [
          { name: "Palma", type: "bar", stack: "island", color: "#15803d", data: categories.map((y) => palma.get(y) ?? null) },
          {
            name: "Resto de la isla", type: "bar", stack: "island", color: "#86efac", itemStyle: { borderRadius: [3, 3, 0, 0] },
            data: categories.map((y) => (value.has(y) ? (value.get(y) as number) - (palma.get(y) ?? 0) : null)),
          },
        ];
    const lines = trends.map((trend, i) => ({
      name: `${trend.from}–${trend.to}: ${signed(trend.rate * 100)} %/año`,
      type: "line", symbol: "none", z: 3, color: i === trends.length - 1 ? "#b45309" : "#7c3aed",
      lineStyle: { type: "dashed", width: 2 },
      data: categories.map((year) => (year >= trend.from && year <= trend.to ? Math.round(trend.at(year)) : null)),
    }));
    const projection = latest
      ? [
          {
            name: `Proyección a ${PROJECTION_YEAR}`, type: "line", symbol: "none", z: 3, color: "#b45309",
            lineStyle: { type: "dotted", width: 2 },
            data: categories.map((year) => (projected(year) ? Math.round(latest.at(year)) : null)),
          },
          // The interval as a band: an invisible line at its bottom and the width stacked on top of it.
          {
            name: "band-low", type: "line", symbol: "none", stack: "band", lineStyle: { opacity: 0 },
            data: band.map((b) => (b ? Math.round(b[0]) : null)),
          },
          {
            name: "band-width", type: "line", symbol: "none", stack: "band", lineStyle: { opacity: 0 },
            areaStyle: { color: "#b45309", opacity: 0.15 },
            data: band.map((b) => (b ? Math.round(b[1] - b[0]) : null)),
          },
        ]
      : [];
    return {
      xAxis: { type: "category", data: categories.map(String) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      // One line that scrolls on a phone: five entries would wrap over the chart.
      legend: {
        type: "scroll", top: 0, left: 0, right: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, itemGap: 16,
        textStyle: { color: c.muted }, pageTextStyle: { color: c.muted },
        data: [...bars, ...lines, ...projection].map((s) => s.name).filter((n) => !n.startsWith("band-")),
      },
      tooltip: {
        // Each series with a value that year, and the interval as a range instead of its two stacked parts.
        formatter: (params: { seriesName: string; value: unknown; marker: string; dataIndex: number; name: string }[]) => {
          const shown = params.filter((p) => typeof p.value === "number" && !p.seriesName.startsWith("band-"));
          const lines = shown.map((p) => `${p.marker} ${p.seriesName} <b>${number(p.value as number)}</b>`);
          const b = band[params[0]?.dataIndex ?? -1];
          if (b) lines.push(`Intervalo del 95 %: ${number(Math.round(b[0]))} – ${number(Math.round(b[1]))}`);
          return [params[0]?.name ?? "", ...lines].join("<br/>");
        },
      },
      series: [...lines, ...projection, ...bars],
    };
  }, [rows, place]);

  const sorted = useMemo(() => [...places].sort((a, b) => a.name.localeCompare(b.name, "es")), [places]);
  return (
    <>
      <label className="select-row">
        <span>Municipio</span>
        <select className="select" aria-label="Municipio" value={selected ?? ""} onChange={(e) => onSelect(e.target.value || null)}>
          <option value="">Toda la isla</option>
          {sorted.map((p) => (
            <option key={p.municipality} value={p.municipality}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <Chart
        option={option}
        label={`Población de ${place?.name ?? "Mallorca"} a 1 de enero, con su tendencia y la proyección a ${PROJECTION_YEAR}`}
        height={340}
      />
    </>
  );
}

/** The twelve most populated municipalities, and the selected one at the end when it is not among them. */
function withSelected(rows: MunicipalityRow[], selected: string | null): MunicipalityRow[] {
  const top = rows.slice(0, 12);
  const extra = rows.find((r) => r.place.municipality === selected);
  return extra && !top.includes(extra) ? [...top, extra] : top;
}

function DailyCalls({ days }: { days: MobilityDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(days.map((d) => d.local_date))].sort();
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      tooltip: { valueFormatter: orDash((v) => number(v)) },
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
  // The municipality chosen on the map, the table or the chart: the three follow it.
  const [selected, setSelected] = useState<string | null>(null);

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
        <Panel
          title="Población y servicio por municipio"
          subtitle={`Padrón del INE a 1 de enero de ${municipalities?.year ?? "—"} y pasos programados en cada parada el ${stopDay} (cuanto más grande, más servicio); pulsa un municipio o una parada para ver sus cifras.`}
          wide
        >
          <Async state={places} height={600}>
            {() =>
              municipalities ? (
                <MobilityMap
                  rows={municipalities.rows}
                  stops={layers}
                  year={municipalities.year}
                  selected={selected}
                  onSelect={setSelected}
                />
              ) : null
            }
          </Async>
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
          title="Población desde 1996"
          subtitle="A 1 de enero (no hubo padrón en 1997). En discontinua, el crecimiento medio anual de cada tramo; en punteado, la proyección a 2030 si sigue la tendencia del último, con su intervalo del 95 %."
          wide
        >
          <Async state={population} height={360}>
            {(rows) => (
              <Async state={places} height={360}>
                {(p) => <PopulationHistory rows={rows} places={p} selected={selected} onSelect={setSelected} />}
              </Async>
            )}
          </Async>
        </Panel>
        <Panel
          title="Municipios más poblados"
          subtitle="Habitantes, cambio en diez años y pasos programados por cada 1.000 habitantes; pulsa uno para verlo en el mapa y en el gráfico."
        >
          <Async state={places}>
            {() =>
              municipalities ? (
                <Table
                  rows={withSelected(municipalities.rows, selected)}
                  onSelect={(r) => setSelected(r.place.municipality === selected ? null : r.place.municipality)}
                  selected={(r) => r.place.municipality === selected}
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
        <Panel title="Pasos programados por día" subtitle="Suma de los vehículos que pasan por cada parada, según los horarios GTFS." full>
          <Async state={daily} height={320}>{(rows) => <DailyCalls days={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
