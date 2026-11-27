import { useCallback, useMemo } from "react";

import { api, type ResourcesMonth, type TourismMonth } from "../api";
import { Async } from "../components/Async";
import { Chart, type ChartColors } from "../components/Chart";
import { CorrelationCard } from "../components/CorrelationCard";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { messages } from "../i18n";
import { compact, monthShort, number, orDash } from "../lib/format";
import { buildKpi, type Kpi, RESOURCE_SPECS, TOURISM_SPECS } from "../lib/kpis";
import { deseasonalize, movingAverage, pearson } from "../lib/stats";

const SINCE = "2016-01-01";
const KPI_COLORS = ["#d97706", "#2563eb", "#0d9488", "#db2777", "#7c3aed"];
const TOURISTS = "#d97706";
const WATER = "#0891b2";
const ELECTRICITY = "#7c3aed";
const HOTELS = "#db2777";
const SPENDING = "#15803d";
const CRUISES = "#0d9488";
const AIRPORT = "#2563eb";

const months = (rows: { month: string }[]) => rows.map((r) => monthShort(r.month));

/** A dashed 12-month trend of a series, on the same axis as the series. */
function trend(name: string, values: (number | null)[], color: string, yAxisIndex = 0) {
  return {
    name, type: "line", symbol: "none", yAxisIndex, color, data: movingAverage(values),
    lineStyle: { type: "dashed", width: 2 }, tooltip: { show: true },
  };
}

/** Both series and their 12-month trends: bars or a line for each month, dashed lines for the trend. */
function PairChart({ rows, left, right, label }: {
  rows: { month: string }[];
  left: { name: string; values: (number | null)[]; color: string; format: (v: number) => string; bars?: boolean };
  right: { name: string; values: (number | null)[]; color: string; format: (v: number) => string; max?: number };
  label: string;
}) {
  const option = useCallback(
    (c: ChartColors) => ({
      xAxis: { type: "category", data: months(rows) },
      yAxis: [
        { type: "value", axisLabel: { formatter: left.format } },
        { type: "value", min: right.max === undefined ? undefined : 0, max: right.max, splitLine: { show: false }, axisLabel: { color: c.muted, formatter: right.format } },
      ],
      tooltip: {
        valueFormatter: orDash((v) => number(v, v < 100 ? 1 : 0)),
      },
      series: [
        left.bars
          ? { name: left.name, type: "bar", data: left.values, color: left.color, itemStyle: { opacity: 0.55 } }
          : { name: left.name, type: "line", smooth: true, symbol: "none", data: left.values, color: left.color, lineStyle: { opacity: 0.55 } },
        { name: right.name, type: "line", smooth: true, symbol: "none", yAxisIndex: 1, data: right.values, color: right.color, lineStyle: { opacity: 0.55 } },
        trend(messages().tourism.trend(left.name), left.values, left.color),
        trend(messages().tourism.trend(right.name), right.values, right.color, 1),
      ],
    }),
    [rows, left, right],
  );
  return <Chart option={option} label={label} height={320} />;
}

function correlations(resources: ResourcesMonth[], tourism: TourismMonth[]) {
  const pair = (rows: { month: string }[], xs: (number | null)[], ys: (number | null)[]) => {
    const ms = rows.map((r) => r.month);
    return { raw: pearson(xs, ys), deseasonalized: pearson(deseasonalize(ms, xs), deseasonalize(ms, ys)) };
  };
  const tourists = resources.map((r) => r.international_tourists);
  return {
    water: pair(resources, tourists, resources.map((r) => r.reserves_pct)),
    electricity: pair(resources, tourists, resources.map((r) => r.electricity_demand_gwh)),
    hotels: pair(tourism, tourism.map((r) => r.hotel_bed_occupancy_pct), tourism.map((r) => r.spending_per_tourist_eur)),
  };
}

const percent = (v: number) => `${number(v)} %`;

export function Tourism() {
  const tourism = useLoad(() => api.tourism(SINCE));
  const resources = useLoad(() => api.resources(SINCE));

  const kpis = useMemo(() => {
    const t = ready(tourism);
    const r = ready(resources);
    if (!t || !r) return null;
    const [tourists, airport, cruise, occupancy] = TOURISM_SPECS.map((spec) => buildKpi(spec, t));
    const electricity = buildKpi(RESOURCE_SPECS.find((s) => s.id === "electricity")!, r);
    return [tourists, airport, cruise, occupancy, electricity].filter((k): k is Kpi => k !== null);
  }, [tourism, resources]);

  const r = useMemo(() => {
    const t = ready(tourism);
    const res = ready(resources);
    return t && res ? correlations(res, t) : null;
  }, [tourism, resources]);
  const m = messages().tourism;

  return (
    <>
      <KpiRow kpis={kpis} colors={KPI_COLORS} />
      {r && (
        <section className="kpis correlations" aria-label={m.correlations}>
          <CorrelationCard label={m.touristsWater} color={WATER} {...r.water} />
          <CorrelationCard label={m.touristsElectricity} color={ELECTRICITY} {...r.electricity} />
          <CorrelationCard label={m.hotelsSpending} color={HOTELS} {...r.hotels} />
        </section>
      )}
      <div className="grid">
        <Panel
          title={m.touristsWater}
          subtitle={m.touristsWaterSubtitle}
          full
        >
          <Async state={resources} height={320}>
            {(rows) => (
              <PairChart
                rows={rows}
                label={m.touristsWaterChart}
                left={{ name: m.tourists, values: rows.map((x) => x.international_tourists), color: TOURISTS, format: compact, bars: true }}
                right={{ name: m.reservesPct, values: rows.map((x) => x.reserves_pct), color: WATER, format: percent, max: 100 }}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.touristsElectricity} subtitle={m.touristsElectricitySubtitle} full>
          <Async state={resources} height={320}>
            {(rows) => (
              <PairChart
                rows={rows}
                label={m.touristsElectricityChart}
                left={{ name: m.tourists, values: rows.map((x) => x.international_tourists), color: TOURISTS, format: compact, bars: true }}
                right={{ name: m.demandGwh, values: rows.map((x) => x.electricity_demand_gwh), color: ELECTRICITY, format: (v) => `${number(v)} GWh` }}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.cruisesTitle} subtitle={m.cruisesSubtitle} full>
          <Async state={tourism} height={320}>
            {(rows) => (
              <PairChart
                rows={rows}
                label={m.cruisesChart}
                left={{ name: m.cruisePassengers, values: rows.map((x) => x.cruise_passengers), color: CRUISES, format: compact, bars: true }}
                right={{ name: m.airportPassengers, values: rows.map((x) => x.airport_passengers), color: AIRPORT, format: compact }}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.hotelsTitle} subtitle={m.hotelsSubtitle} full>
          <Async state={tourism} height={320}>
            {(rows) => (
              <PairChart
                rows={rows}
                label={m.hotelsChart}
                left={{ name: m.occupancyPct, values: rows.map((x) => x.hotel_bed_occupancy_pct), color: HOTELS, format: percent }}
                right={{ name: m.spendingEur, values: rows.map((x) => x.spending_per_tourist_eur), color: SPENDING, format: (v) => `${number(v)} €` }}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
