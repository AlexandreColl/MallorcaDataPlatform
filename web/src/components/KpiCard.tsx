import type { Kpi } from "../lib/kpis";
import { Sparkline } from "./Sparkline";

const COLORS: Record<string, string> = {
  reserves: "#0891b2",
  rain: "#2563eb",
  tourists: "#d97706",
  electricity: "#7c3aed",
  temperature: "#dc2626",
};

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const color = COLORS[kpi.id] ?? "#0891b2";
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
      <Sparkline points={kpi.history} color={color} unit={kpi.unit} />
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
