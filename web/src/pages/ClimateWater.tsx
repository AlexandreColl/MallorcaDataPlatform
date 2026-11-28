import { useCallback, useMemo } from "react";

import {
  api,
  type Aquifer,
  type BathingWaterSeason,
  type BathingWaterYear,
  type ClimateMonth,
  type SeaTemperatureMonth,
  type WaterReservesMonth,
} from "../api";
import { Async } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { messages } from "../i18n";
import { bathingLayers, QUALITY_CLASSES, QUALITY_COLORS, qualityName } from "../lib/bathing";
import { monthAbbreviation, monthName, monthShort, number, orDash } from "../lib/format";
import { buildKpi, HOT_DAYS_SPEC, type Kpi, RAIN_SPEC, WATER_SPECS } from "../lib/kpis";

const SINCE = "2016-01-01";
const KPI_COLORS = ["#0891b2", "#dc2626", "#2563eb", "#d97706"];
/** The hydrological year starts in September: September to August. */
const HYDRO_MONTHS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8];
const LOW_RESERVES_PCT = 30;

function Reserves({ rows }: { rows: WaterReservesMonth[] }) {
  const m = messages().climate;
  const option = useCallback(
    () => ({
      xAxis: { type: "category", data: rows.map((r) => monthShort(r.month)) },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value} %" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} %`) },
      series: [
        {
          name: m.reserves, type: "line", smooth: true, symbol: "none", data: rows.map((r) => r.reserves_pct),
          color: "#0891b2", lineStyle: { width: 2.5 }, areaStyle: { opacity: 0.12 },
        },
        {
          name: m.monthMean, type: "line", smooth: true, symbol: "none", color: "#94a3b8",
          lineStyle: { type: "dashed" }, data: rows.map((r) => r.same_month_mean_pct),
        },
      ],
    }),
    [rows, m],
  );
  return <Chart option={option} label={m.reservesChart} height={320} />;
}

/** Rain accumulated since September, one line per hydrological year, against the usual accumulation. */
function RainByYear({ rows }: { rows: ClimateMonth[] }) {
  const m = messages().climate;
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
      xAxis: { type: "category", data: HYDRO_MONTHS.map(monthAbbreviation) },
      yAxis: { type: "value", axisLabel: { formatter: "{value} mm" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 0)} mm`) },
      series: [
        ...series,
        { name: m.normal, type: "line", symbol: "none", data: mean, color: "#15803d", lineStyle: { type: "dashed", width: 2 } },
      ],
    };
  }, [rows, m]);
  return <Chart option={option} label={m.rainChart} />;
}

function TemperatureAnomaly({ rows }: { rows: ClimateMonth[] }) {
  const m = messages().climate;
  const option = useCallback(
    () => ({
      legend: { show: false },
      xAxis: { type: "category", data: rows.map((r) => monthShort(r.month)) },
      yAxis: { type: "value", axisLabel: { formatter: "{value} °C" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 2)} °C`) },
      series: [
        {
          name: m.anomaly, type: "bar",
          data: rows.map((r) => ({
            value: r.temperature_anomaly_c,
            itemStyle: { color: (r.temperature_anomaly_c ?? 0) >= 0 ? "#dc2626" : "#2563eb", borderRadius: 2 },
          })),
        },
      ],
    }),
    [rows, m],
  );
  return <Chart option={option} label={m.anomalyChart} />;
}

/** The sea against 1991-2020 (bars, °C) and its marine heatwave days (line, right axis), month by month. */
function SeaAnomaly({ rows }: { rows: SeaTemperatureMonth[] }) {
  const m = messages().climate;
  const option = useCallback(
    () => ({
      xAxis: { type: "category", data: rows.map((r) => monthShort(r.month)) },
      yAxis: [
        { type: "value", axisLabel: { formatter: "{value} °C" } },
        { type: "value", min: 0, max: 31, splitLine: { show: false }, axisLabel: { formatter: "{value} d" } },
      ],
      tooltip: { trigger: "axis" },
      series: [
        {
          name: m.seaAnomaly, type: "bar", color: "#ea580c",
          tooltip: { valueFormatter: orDash((v) => `${number(v, 2)} °C`) },
          data: rows.map((r) => ({
            value: r.sst_anomaly_c,
            itemStyle: { color: (r.sst_anomaly_c ?? 0) >= 0 ? "#ea580c" : "#0891b2", borderRadius: 2, opacity: r.has_preliminary_days ? 0.55 : 1 },
          })),
        },
        {
          name: m.heatwaveDays, type: "line", yAxisIndex: 1, symbol: "none", step: "middle", color: "#b91c1c",
          tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} d`) },
          lineStyle: { width: 1.5 }, data: rows.map((r) => r.heatwave_days),
        },
      ],
    }),
    [rows, m],
  );
  return <Chart option={option} label={m.seaChart} />;
}

function Aquifers({ rows }: { rows: Aquifer[] }) {
  const sorted = useMemo(() => [...rows].sort((a, b) => (b.reserves_pct ?? 0) - (a.reserves_pct ?? 0)), [rows]);
  const m = messages().climate;
  const option = useCallback(
    () => ({
      legend: { show: false },
      grid: { left: 8, right: 24, top: 8, bottom: 8 },
      xAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value} %" } },
      yAxis: { type: "category", data: sorted.map((a) => a.aquifer), axisLabel: { fontSize: 11 } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: orDash((v) => `${number(v, 0)} %`) },
      series: [
        {
          name: m.reserves, type: "bar", barWidth: "62%",
          data: sorted.map((a) => ({
            value: a.reserves_pct,
            itemStyle: { color: (a.reserves_pct ?? 0) < LOW_RESERVES_PCT ? "#dc2626" : "#0891b2", borderRadius: 3 },
          })),
          markLine: { symbol: "none", data: [{ xAxis: LOW_RESERVES_PCT }], lineStyle: { color: "#dc2626", type: "dashed" }, label: { show: false } },
        },
      ],
    }),
    [sorted, m],
  );
  return <Chart option={option} label={m.aquifersChart} height={460} />;
}

/** The beaches coloured by their class of the directive in the latest season; a click opens the beach's card. */
function BathingMap({ rows }: { rows: BathingWaterSeason[] }) {
  const layers = useMemo(() => bathingLayers(rows), [rows]);
  return <PointMap layers={layers} height={440} />;
}

/** Beaches of each class per season (stacked bars) and the share of excellent ones among the classified (line). */
function BathingTrend({ rows }: { rows: BathingWaterYear[] }) {
  const m = messages().bathing;
  const option = useCallback(() => {
    const counts = { 4: "excellent", 3: "good", 2: "sufficient", 1: "poor" } as const;
    return {
      xAxis: { type: "category", data: rows.map((r) => String(r.season)) },
      yAxis: [
        { type: "value", minInterval: 1 },
        { type: "value", min: 0, max: 100, splitLine: { show: false }, axisLabel: { formatter: "{value} %" } },
      ],
      tooltip: { trigger: "axis" },
      series: [
        ...QUALITY_CLASSES.map((c) => ({
          name: qualityName(c), type: "bar", stack: "classes", color: QUALITY_COLORS[c],
          data: rows.map((r) => r[counts[c]]),
        })),
        {
          name: m.excellentShare, type: "line", yAxisIndex: 1, color: "#9333ea", symbolSize: 7,
          tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} %`) },
          data: rows.map((r) => (r.excellent_share === null ? null : 100 * r.excellent_share)),
        },
      ],
    };
  }, [rows, m]);
  return <Chart option={option} label={m.trendChart} />;
}

export function ClimateWater() {
  const water = useLoad(() => api.water(SINCE));
  const climate = useLoad(() => api.climate(SINCE));
  const aquifers = useLoad(api.aquifers);
  const sea = useLoad(() => api.seaTemperature(SINCE));
  const bathing = useLoad(api.bathingWaters);
  const bathingYears = useLoad(api.bathingWaterYears);

  const kpis = useMemo(() => {
    const w = ready(water);
    const c = ready(climate);
    if (!w || !c) return null;
    return [...WATER_SPECS.map((s) => buildKpi(s, w)), buildKpi(RAIN_SPEC, c), buildKpi(HOT_DAYS_SPEC, c)].filter(
      (k): k is Kpi => k !== null,
    );
  }, [water, climate]);

  const aquiferMonth = aquifers.status === "ready" && aquifers.data[0] ? monthName(aquifers.data[0].month) : "";
  const bathingSeason = bathing.status === "ready" && bathing.data[0] ? String(bathing.data[0].season) : "";
  const m = messages().climate;
  const b = messages().bathing;

  return (
    <>
      <KpiRow kpis={kpis} colors={KPI_COLORS} />
      <div className="grid">
        <Panel title={m.groundwaterTitle} subtitle={m.groundwaterSubtitle} wide>
          <Async state={water} height={320}>{(rows) => <Reserves rows={rows} />}</Async>
        </Panel>
        <Panel title={m.aquifersTitle} subtitle={m.aquifersSubtitle(aquiferMonth)}>
          <Async state={aquifers} height={460}>{(rows) => <Aquifers rows={rows} />}</Async>
        </Panel>
        <Panel title={m.rainTitle} subtitle={m.rainSubtitle}>
          <Async state={climate}>{(rows) => <RainByYear rows={rows} />}</Async>
        </Panel>
        <Panel title={m.temperatureTitle} subtitle={m.temperatureSubtitle}>
          <Async state={climate}>{(rows) => <TemperatureAnomaly rows={rows} />}</Async>
        </Panel>
        <Panel title={m.seaTitle} subtitle={m.seaSubtitle}>
          <Async state={sea}>{(rows) => <SeaAnomaly rows={rows} />}</Async>
        </Panel>
        <Panel title={b.mapTitle} subtitle={b.mapSubtitle(bathingSeason)}>
          <Async state={bathing} height={440}>{(rows) => <BathingMap rows={rows} />}</Async>
        </Panel>
        <Panel title={b.trendTitle} subtitle={b.trendSubtitle}>
          <Async state={bathingYears}>{(rows) => <BathingTrend rows={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
