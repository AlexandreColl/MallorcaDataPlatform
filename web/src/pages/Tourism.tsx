import { useCallback, useMemo } from "react";

import { api, type ResourcesMonth, type TourismMonth } from "../api";
import { Async } from "../components/Async";
import { Chart, type ChartColors } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { compact, monthShort, number } from "../lib/format";
import { buildKpi, type Kpi, RESOURCE_SPECS, TOURISM_SPECS } from "../lib/kpis";

const SINCE = "2016-01-01";
const KPI_COLORS = ["#d97706", "#2563eb", "#db2777", "#7c3aed"];

const months = (rows: { month: string }[]) => rows.map((r) => monthShort(r.month));

function TouristsAndWater({ rows }: { rows: ResourcesMonth[] }) {
  const option = useCallback(
    (c: ChartColors) => ({
      xAxis: { type: "category", data: months(rows) },
      yAxis: [
        { type: "value", name: "Turistas", axisLabel: { formatter: compact } },
        { type: "value", name: "Reservas %", min: 0, max: 100, splitLine: { show: false }, axisLabel: { color: c.muted } },
      ],
      series: [
        { name: "Turistas internacionales", type: "bar", data: rows.map((r) => r.international_tourists), color: "#d97706" },
        {
          name: "Reservas de agua (%)", type: "line", yAxisIndex: 1, smooth: true, symbol: "none",
          data: rows.map((r) => r.reserves_pct), color: "#0891b2", lineStyle: { width: 2.5 },
        },
      ],
    }),
    [rows],
  );
  return <Chart option={option} label="Turistas por mes y reservas de agua" height={320} />;
}

function Anomalies({ rows }: { rows: ResourcesMonth[] }) {
  const option = useCallback(
    () => ({
      xAxis: { type: "category", data: months(rows) },
      yAxis: { type: "value", axisLabel: { formatter: (v: number) => `${number(v * 100)} %` } },
      tooltip: { valueFormatter: (v: number | null) => (v === null ? "—" : `${number(v * 100, 1)} %`) },
      series: [
        { name: "Turistas", type: "line", symbol: "none", data: rows.map((r) => r.tourists_anomaly), color: "#d97706" },
        {
          name: "Demanda eléctrica", type: "line", symbol: "none",
          data: rows.map((r) => r.electricity_demand_anomaly), color: "#7c3aed",
        },
        { name: "Lluvia", type: "line", symbol: "none", data: rows.map((r) => r.rain_anomaly), color: "#2563eb", lineStyle: { opacity: 0.6 } },
      ],
    }),
    [rows],
  );
  return <Chart option={option} label="Desviación de cada serie frente al mismo mes" />;
}

function HotelsAndSpending({ rows }: { rows: TourismMonth[] }) {
  const option = useCallback(
    () => ({
      xAxis: { type: "category", data: months(rows) },
      yAxis: [
        { type: "value", name: "Ocupación %", min: 0, max: 100 },
        { type: "value", name: "€ por turista", splitLine: { show: false } },
      ],
      series: [
        {
          name: "Ocupación hotelera (%)", type: "line", smooth: true, symbol: "none",
          data: rows.map((r) => r.hotel_bed_occupancy_pct), color: "#db2777", areaStyle: { opacity: 0.1 },
        },
        {
          name: "Gasto por turista (€)", type: "line", smooth: true, symbol: "none", yAxisIndex: 1,
          data: rows.map((r) => r.spending_per_tourist_eur), color: "#15803d",
        },
      ],
    }),
    [rows],
  );
  return <Chart option={option} label="Ocupación hotelera y gasto por turista" />;
}

export function Tourism() {
  const tourism = useLoad(() => api.tourism(SINCE));
  const resources = useLoad(() => api.resources(SINCE));

  const kpis = useMemo(() => {
    const t = ready(tourism);
    const r = ready(resources);
    if (!t || !r) return null;
    const [tourists, airport, occupancy] = TOURISM_SPECS.map((spec) => buildKpi(spec, t));
    const electricity = buildKpi(RESOURCE_SPECS.find((s) => s.id === "electricity")!, r);
    return [tourists, airport, occupancy, electricity].filter((k): k is Kpi => k !== null);
  }, [tourism, resources]);

  return (
    <>
      <KpiRow kpis={kpis} colors={KPI_COLORS} />
      <div className="grid">
        <Panel title="Turistas y reservas de agua" subtitle="Cada verano llegan más de dos millones de turistas al mes, justo cuando bajan las reservas." wide>
          <Async state={resources} height={320}>{(rows) => <TouristsAndWater rows={rows} />}</Async>
        </Panel>
        <Panel title="Frente a lo normal" subtitle="Desviación de cada mes frente a la media de ese mes en otros años.">
          <Async state={resources}>{(rows) => <Anomalies rows={rows} />}</Async>
        </Panel>
        <Panel title="Hoteles y gasto" subtitle="Ocupación de plazas hoteleras y gasto medio de cada turista internacional.">
          <Async state={tourism}>{(rows) => <HotelsAndSpending rows={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
