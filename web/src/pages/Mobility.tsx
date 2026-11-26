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
import { messages } from "../i18n";
import { compact, dayName, dayShort, monthAbbreviation, number, orDash, signed } from "../lib/format";
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
import { kindLabel } from "../lib/transit";

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
  return <Chart option={option} label={messages().mobilityPage.dailyCallsChart} height={320} />;
}

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
              const month = monthAbbreviation(Number(day.slice(0, 2)));
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
                  label: { formatter: messages().mobilityPage.registered(compact(residents)), position: "insideMiddleBottom", color: c.muted },
                  data: [{ yAxis: residents }],
                },
              }
            : {}),
        })),
      };
    },
    [days],
  );
  return <Chart option={option} label={messages().mobilityPage.pressureChart} height={340} />;
}

export function Mobility() {
  const daily = useLoad(() => api.mobilityDaily(daysAgo(60)));
  const stops = useLoad(api.stops);
  const population = useLoad(() => api.population(FIRST_YEAR));
  const places = useLoad(api.municipalities);
  const dwellings = useLoad(api.touristDwellings);
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
    // The tourist dwellings are a layer more: the map does not wait for them, nor fails with them.
    return { rows: municipalityRows(m, p, s, year, ready(dwellings) ?? []), year };
  }, [places, population, stops, dwellings]);
  const layers = useMemo(() => (stops.status === "ready" ? stopLayers(stops.data) : []), [stops]);
  const m = messages().mobilityPage;
  const stopDay = stops.status === "ready" && stops.data[0] ? dayName(stops.data[0].local_date) : m.lastDay;

  return (
    <>
      <KpiRow
        kpis={kpis}
        colors={["#15803d", "#15803d", NETWORKS.emt_palma.color, NETWORKS.ctm.color]}
      />
      <div className="grid">
        <Panel
          title={m.mapTitle}
          subtitle={m.mapSubtitle(String(municipalities?.year ?? "—"), stopDay)}
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
        <Panel title={m.busiestStopsTitle} subtitle={m.busiestStopsSubtitle}>
          <Async state={stops}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 10)}
                columns={[
                  { label: m.stop, value: (s) => s.name ?? s.stop },
                  { label: m.network, value: (s) => NETWORKS[s.network].label },
                  { label: m.calls, value: (s) => number(s.departures ?? 0), numeric: true },
                  { label: m.lines, value: (s) => number(s.lines ?? 0), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.linesTitle} subtitle={routesSubtitle(ready(routes))} wide>
          <Async state={routes} height={600}>{(rows) => <TransitMap routes={rows} />}</Async>
        </Panel>
        <Panel title={m.busiestLinesTitle} subtitle={m.busiestLinesSubtitle}>
          <Async state={routes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 10)}
                columns={[
                  { label: m.line, value: (r) => r.name },
                  { label: m.network, value: (r) => `${NETWORKS[r.network].label} · ${kindLabel(r.kind)}` },
                  { label: m.departures, value: (r) => (r.trips === null ? "—" : number(r.trips)), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title={m.historyTitle}
          subtitle={m.historySubtitle}
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
          title={m.placesTitle}
          subtitle={m.placesSubtitle}
        >
          <Async state={places}>
            {() =>
              municipalities ? (
                <Table
                  rows={withSelected(municipalities.rows, selected)}
                  onSelect={(r) => setSelected(r.place.municipality === selected ? null : r.place.municipality)}
                  selected={(r) => r.place.municipality === selected}
                  columns={[
                    { label: m.municipality, value: (r) => r.place.name },
                    { label: m.inhabitants, value: (r) => number(r.latest?.population ?? 0), numeric: true },
                    { label: m.tenYears, value: (r) => (r.growth === null ? "—" : `${signed(r.growth * 100)} %`), numeric: true },
                    { label: m.callsPerThousand, value: (r) => (r.perThousand === null ? "—" : number(r.perThousand)), numeric: true },
                    {
                      label: m.dwellingsPerThousand,
                      value: (r) => {
                        const ratio = r.dwellings?.dwellings_per_1000_inhabitants;
                        return ratio == null ? "—" : number(ratio, 1);
                      },
                      numeric: true,
                    },
                  ]}
                />
              ) : null
            }
          </Async>
        </Panel>
        <Panel title={m.pressureTitle} subtitle={pressureSubtitle(ready(pressure))} full>
          <Async state={pressure} height={340}>{(rows) => <HumanPressure days={rows} />}</Async>
        </Panel>
        <Panel title={m.dailyCallsTitle} subtitle={m.dailyCallsSubtitle} full>
          <Async state={daily} height={320}>{(rows) => <DailyCalls days={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
