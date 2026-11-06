import { useCallback, useMemo } from "react";

import { api, type Aquifer, type ClimateMonth, type WaterReservesMonth } from "../api";
import { Async } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { monthName, monthShort, number, orDash } from "../lib/format";
import { buildKpi, HOT_DAYS_SPEC, type Kpi, RAIN_SPEC, WATER_SPECS } from "../lib/kpis";

const SINCE = "2016-01-01";
const KPI_COLORS = ["#0891b2", "#dc2626", "#2563eb", "#d97706"];
/** The hydrological year starts in September. */
const HYDRO_MONTHS = ["sep", "oct", "nov", "dic", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago"];
const LOW_RESERVES_PCT = 30;

function Reserves({ rows }: { rows: WaterReservesMonth[] }) {
  const option = useCallback(
    () => ({
      xAxis: { type: "category", data: rows.map((r) => monthShort(r.month)) },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value} %" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} %`) },
      series: [
        {
          name: "Reservas", type: "line", smooth: true, symbol: "none", data: rows.map((r) => r.reserves_pct),
          color: "#0891b2", lineStyle: { width: 2.5 }, areaStyle: { opacity: 0.12 },
        },
        {
          name: "Media de ese mes", type: "line", smooth: true, symbol: "none", color: "#94a3b8",
          lineStyle: { type: "dashed" }, data: rows.map((r) => r.same_month_mean_pct),
        },
      ],
    }),
    [rows],
  );
  return <Chart option={option} label="Reservas de agua frente a la media del mes" height={320} />;
}

/** Rain accumulated since September, one line per hydrological year, against the usual accumulation. */
function RainByYear({ rows }: { rows: ClimateMonth[] }) {
  const option = useCallback(() => {
    const years = [...new Set(rows.map((r) => r.hydrological_year))].sort().slice(-5);
    const slot = (month: string) => (Number(month.slice(5, 7)) + 3) % 12; // september -> 0
    const series = years.map((year, i) => {
      const data: (number | null)[] = Array(12).fill(null);
      for (const r of rows.filter((x) => x.hydrological_year === year)) data[slot(r.month)] = r.rain_hydrological_year_mm;
      const latest = i === years.length - 1;
      return {
        name: `${year - 1}-${String(year).slice(2)}`, type: "line", symbol: latest ? "circle" : "none", data,
        lineStyle: { width: latest ? 3 : 1.5, opacity: latest ? 1 : 0.55 },
      };
    });
    const mean: (number | null)[] = Array(12).fill(null);
    for (const r of rows) mean[slot(r.month)] = r.rain_hydrological_year_mean_mm;
    return {
      color: ["#94a3b8", "#a3a3a3", "#65a30d", "#0891b2", "#2563eb"],
      xAxis: { type: "category", data: HYDRO_MONTHS },
      yAxis: { type: "value", axisLabel: { formatter: "{value} mm" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 0)} mm`) },
      series: [
        ...series,
        { name: "Normal", type: "line", symbol: "none", data: mean, color: "#15803d", lineStyle: { type: "dashed", width: 2 } },
      ],
    };
  }, [rows]);
  return <Chart option={option} label="Lluvia acumulada en cada año hidrológico" />;
}

function TemperatureAnomaly({ rows }: { rows: ClimateMonth[] }) {
  const option = useCallback(
    () => ({
      legend: { show: false },
      xAxis: { type: "category", data: rows.map((r) => monthShort(r.month)) },
      yAxis: { type: "value", axisLabel: { formatter: "{value} °C" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 2)} °C`) },
      series: [
        {
          name: "Anomalía", type: "bar",
          data: rows.map((r) => ({
            value: r.temperature_anomaly_c,
            itemStyle: { color: (r.temperature_anomaly_c ?? 0) >= 0 ? "#dc2626" : "#2563eb", borderRadius: 2 },
          })),
        },
      ],
    }),
    [rows],
  );
  return <Chart option={option} label="Anomalía de temperatura de cada mes" />;
}

function Aquifers({ rows }: { rows: Aquifer[] }) {
  const sorted = useMemo(() => [...rows].sort((a, b) => (b.reserves_pct ?? 0) - (a.reserves_pct ?? 0)), [rows]);
  const option = useCallback(
    () => ({
      legend: { show: false },
      grid: { left: 8, right: 24, top: 8, bottom: 8 },
      xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value} %" } },
      yAxis: { type: "category", data: sorted.map((a) => a.aquifer), axisLabel: { fontSize: 11 } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: orDash((v) => `${number(v, 0)} %`) },
      series: [
        {
          name: "Reservas", type: "bar", barWidth: "62%",
          data: sorted.map((a) => ({
            value: a.reserves_pct,
            itemStyle: { color: (a.reserves_pct ?? 0) < LOW_RESERVES_PCT ? "#dc2626" : "#0891b2", borderRadius: 3 },
          })),
          markLine: { symbol: "none", data: [{ xAxis: LOW_RESERVES_PCT }], lineStyle: { color: "#dc2626", type: "dashed" }, label: { show: false } },
        },
      ],
    }),
    [sorted],
  );
  return <Chart option={option} label="Reservas de cada acuífero" height={460} />;
}

export function ClimateWater() {
  const water = useLoad(() => api.water(SINCE));
  const climate = useLoad(() => api.climate(SINCE));
  const aquifers = useLoad(api.aquifers);

  const kpis = useMemo(() => {
    const w = ready(water);
    const c = ready(climate);
    if (!w || !c) return null;
    return [...WATER_SPECS.map((s) => buildKpi(s, w)), buildKpi(RAIN_SPEC, c), buildKpi(HOT_DAYS_SPEC, c)].filter(
      (k): k is Kpi => k !== null,
    );
  }, [water, climate]);

  const aquiferMonth = aquifers.status === "ready" && aquifers.data[0] ? monthName(aquifers.data[0].month) : "";

  return (
    <>
      <KpiRow kpis={kpis} colors={KPI_COLORS} />
      <div className="grid">
        <Panel title="Reservas de agua subterránea" subtitle="Porcentaje de llenado de los acuíferos de la isla, frente a la media de cada mes." wide>
          <Async state={water} height={320}>{(rows) => <Reserves rows={rows} />}</Async>
        </Panel>
        <Panel title="Acuíferos" subtitle={`Reservas de cada uno en ${aquiferMonth}. En rojo, los que están por debajo del 30 %.`}>
          <Async state={aquifers} height={460}>{(rows) => <Aquifers rows={rows} />}</Async>
        </Panel>
        <Panel title="Lluvia del año hidrológico" subtitle="Lluvia acumulada desde septiembre en las estaciones de AEMET, año a año.">
          <Async state={climate}>{(rows) => <RainByYear rows={rows} />}</Async>
        </Panel>
        <Panel title="Temperatura frente a lo normal" subtitle="Diferencia entre la temperatura media de cada mes y la de ese mes en otros años." wide>
          <Async state={climate}>{(rows) => <TemperatureAnomaly rows={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
