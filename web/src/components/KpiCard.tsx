import { useCallback } from "react";

import { monthShort, number } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { Chart, type ChartColors } from "./Chart";

function Sparkline({ points, color, unit }: { points: Kpi["history"]; color: string; unit: string }) {
  const option = useCallback(
    (c: ChartColors) => ({
      grid: { left: 0, right: 0, top: 4, bottom: 0, outerBoundsMode: "none" },
      legend: { show: false },
      xAxis: { type: "category", show: false, boundaryGap: false, data: points.map((p) => p.month) },
      yAxis: { type: "value", show: false, scale: true },
      tooltip: {
        axisPointer: { type: "line", lineStyle: { color, opacity: 0.4 } },
        formatter: (params: { name: string; value: number }[]) => {
          const point = params[0];
          if (!point) return "";
          // Yearly series (the municipal register) are labelled by their year; large values need no decimals.
          const label = /^\d{4}$/.test(point.name) ? point.name : monthShort(point.name);
          return `${label} · <b>${number(point.value, Math.abs(point.value) >= 1000 ? 0 : 1)}</b> ${unit}`;
        },
      },
      series: [
        {
          type: "line",
          data: points.map((p) => p.value),
          smooth: 0.3,
          symbol: "none",
          lineStyle: { width: 2, color },
          areaStyle: { color, opacity: c.theme === "dark" ? 0.18 : 0.12 },
        },
      ],
    }),
    [points, color, unit],
  );
  return <Chart option={option} height={60} label="Evolución reciente" />;
}

export function KpiCard({ kpi, color = "var(--brand)" }: { kpi: Kpi; color?: string }) {
  return (
    <article className="card kpi" style={{ "--accent": color } as React.CSSProperties}>
      <header className="kpi-header">
        <h3>{kpi.label}</h3>
        <span className="kpi-month">{kpi.month}</span>
      </header>
      <p className="kpi-value">
        {kpi.value}
        {kpi.unit && <span className="kpi-unit">{kpi.unit}</span>}
      </p>
      {kpi.deviation && <p className={`chip chip-${kpi.tone}`}>{kpi.deviation}</p>}
      {kpi.history.length > 1 && (
        <div className="kpi-spark">
          <Sparkline points={kpi.history} color={color.startsWith("var") ? "#15803d" : color} unit={kpi.unit} />
        </div>
      )}
    </article>
  );
}

export function KpiSkeleton() {
  return (
    <article className="card kpi skeleton" aria-hidden="true">
      <div className="bar short" />
      <div className="bar tall" />
      <div className="bar" />
    </article>
  );
}

/** A row of key figures, with skeletons while they load. */
export function KpiRow({ kpis, colors }: { kpis: Kpi[] | null; colors?: string[] }) {
  return (
    <section className="kpis" aria-label="Cifras clave">
      {kpis === null
        ? Array.from({ length: 4 }, (_, i) => <KpiSkeleton key={i} />)
        : kpis.map((kpi, i) => <KpiCard key={kpi.id} kpi={kpi} color={colors?.[i]} />)}
    </section>
  );
}
