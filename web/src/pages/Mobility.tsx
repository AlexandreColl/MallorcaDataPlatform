import { useCallback, useMemo, useState } from "react";

import { api, daysAgo, type HumanPressureDay, type MobilityDay } from "../api";
import { Async, Table } from "../components/Async";
import { Chart, type ChartColors } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { MobilityMap } from "../components/MobilityMap";
import { PopulationHistory } from "../components/PopulationHistory";
import { TransitMap } from "../components/TransitMap";
import { ready, useLoad } from "../hooks";
import { compact, dayName, dayShort, number, orDash, signed } from "../lib/format";
import {
  FIRST_YEAR,
  mobilityKpis,
  municipalityRows,
  NETWORKS,
  populationKpis,
  pressureSubtitle,
  routesSubtitle,
  stopLayers,
  withSelected,
} from "../lib/mobility";
import { DAYS_OF_YEAR, pressureByYear } from "../lib/population";
import { KINDS } from "../lib/transit";

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

/** Month names for the axis of the days of the year. */
const MONTH_LABELS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/**
 * The people present in Mallorca each day (Ibestat IPH), the last three years laid over each other, against the
 * residents of the latest register: how far the summer pushes the island above its population.
 */
function HumanPressure({ days }: { days: HumanPressureDay[] }) {
  const option = useCallback(
    (c: ChartColors) => {
      const years = pressureByYear(days).slice(0, 3);
      const residents = days.at(-1)?.residents ?? null;
      const colors = ["#15803d", "#2563eb", c.muted];
      const narrow = window.innerWidth < 640; // twelve month names do not fit a phone: their initials do
      return {
        xAxis: {
          type: "category",
          data: DAYS_OF_YEAR,
          boundaryGap: false,
          axisLabel: {
            interval: (_: number, day: string) => day.endsWith("-01"),
            formatter: (day: string) => {
              const month = MONTH_LABELS[Number(day.slice(0, 2)) - 1] ?? "";
              return narrow ? month.charAt(0).toUpperCase() : month;
            },
          },
        },
        yAxis: { type: "value", min: (v: { min: number }) => Math.floor(v.min / 100_000) * 100_000, axisLabel: { formatter: compact } },
        tooltip: {
          valueFormatter: orDash((v) => number(v)),
          axisPointer: { label: { formatter: (p: { value: string }) => dayShort(`2024-${p.value}`) } },
        },
        series: years.map((y, i) => ({
          name: String(y.year), type: "line", symbol: "none", data: y.values, color: colors[i],
          lineStyle: { width: i === 0 ? 2.5 : 1.5, opacity: i === 0 ? 1 : 0.7 },
          z: 3 - i,
          ...(i === 0 && residents !== null
            ? {
                markLine: {
                  symbol: "none", silent: true,
                  lineStyle: { color: c.text, type: "dashed", opacity: 0.6 },
                  label: { formatter: `Empadronados: ${compact(residents)}`, position: "insideMiddleBottom", color: c.muted },
                  data: [{ yAxis: residents }],
                },
              }
            : {}),
        })),
      };
    },
    [days],
  );
  return <Chart option={option} label="Personas presentes en Mallorca cada día, por año, frente a los empadronados" height={340} />;
}

export function Mobility() {
  const daily = useLoad(() => api.mobilityDaily(daysAgo(60)));
  const stops = useLoad(api.stops);
  const population = useLoad(() => api.population(FIRST_YEAR));
  const places = useLoad(api.municipalities);
  const pressure = useLoad(() => api.humanPressure(daysAgo(3 * 366 + 120)));
  const routes = useLoad(api.routes);
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
                  { label: "Parada", value: (s) => s.name ?? s.stop },
                  { label: "Red", value: (s) => NETWORKS[s.network].label },
                  { label: "Pasos", value: (s) => number(s.departures ?? 0), numeric: true },
                  { label: "Líneas", value: (s) => number(s.lines ?? 0), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Líneas de autobús, tren y metro" subtitle={routesSubtitle(ready(routes))} wide>
          <Async state={routes} height={600}>{(rows) => <TransitMap routes={rows} />}</Async>
        </Panel>
        <Panel title="Líneas con más salidas" subtitle="Las diez con más salidas programadas de las dos redes.">
          <Async state={routes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 10)}
                columns={[
                  { label: "Línea", value: (r) => r.name },
                  { label: "Red", value: (r) => `${NETWORKS[r.network].label} · ${KINDS[r.kind] ?? r.kind}` },
                  { label: "Salidas", value: (r) => (r.trips === null ? "—" : number(r.trips)), numeric: true },
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
        <Panel title="Población real presente" subtitle={pressureSubtitle(ready(pressure))} full>
          <Async state={pressure} height={340}>{(rows) => <HumanPressure days={rows} />}</Async>
        </Panel>
        <Panel title="Pasos programados por día" subtitle="Suma de los vehículos que pasan por cada parada, según los horarios GTFS." full>
          <Async state={daily} height={320}>{(rows) => <DailyCalls days={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
