import { useCallback, useMemo } from "react";

import { type AnomaliesDay, api, daysAgo, type Source } from "../api";
import { Async, Table } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { age, compact, dayShort, number } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { sourceState, STATE_LABELS } from "../lib/sources";

const DETECTORS: Record<string, { label: string; color: string }> = {
  robust_zscore: { label: "Z-score robusto", color: "#d97706" },
  isolation_forest: { label: "Isolation Forest", color: "#7c3aed" },
};

function operationsKpis(sources: Source[], anomalies: AnomaliesDay[], failingRules: number): Kpi[] {
  const active = sources.filter((s) => sourceState(s) !== "inactive");
  const ok = active.filter((s) => sourceState(s) === "ok").length;
  const runs = active.reduce((n, s) => n + s.runs_7d, 0);
  const failed = active.reduce((n, s) => n + Math.round((s.failure_rate_7d ?? 0) * s.runs_7d), 0);
  const flagged = anomalies.reduce((n, a) => n + a.anomalies, 0);
  return [
    {
      id: "sources", label: "Fuentes al día", value: `${ok}`, unit: `de ${active.length}`, month: "Con una carga correcta en 36 h",
      deviation: ok === active.length ? "Todas al día" : `${active.length - ok} atrasadas o con fallos`,
      tone: ok === active.length ? "good" : "bad", history: [],
    },
    {
      id: "values", label: "Valores en silver", value: compact(sources.reduce((n, s) => n + s.observations, 0)), unit: "",
      month: `${sources.length} fuentes`, deviation: null, tone: "neutral", history: [],
    },
    {
      id: "runs", label: "Ejecuciones fallidas", value: number(failed), unit: `de ${number(runs)}`, month: "Últimos 7 días",
      deviation: failed === 0 ? "Ningún fallo" : null, tone: failed === 0 ? "good" : "bad", history: [],
    },
    {
      id: "anomalies", label: "Anomalías", value: number(flagged), unit: "", month: "Últimos 30 días",
      deviation: failingRules === 0 ? "Todas las reglas de calidad pasan" : `${failingRules} reglas de calidad fallan`,
      tone: failingRules === 0 ? "good" : "bad", history: [],
    },
  ];
}

function AnomaliesPerDay({ rows }: { rows: AnomaliesDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(rows.map((r) => r.local_date))].sort();
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value" },
      series: Object.entries(DETECTORS).map(([detector, { label, color }]) => ({
        name: label, type: "bar", stack: "total", color,
        data: dates.map((d) => rows.find((r) => r.local_date === d && r.detector === detector)?.anomalies ?? 0),
      })),
    };
  }, [rows]);
  return <Chart option={option} label="Valores marcados por cada detector y día" />;
}

export function Operations() {
  const sources = useLoad(api.sources);
  const anomalies = useLoad(() => api.anomaliesDaily(daysAgo(30)));
  const rules = useLoad(api.qualityRules);
  const corrections = useLoad(() => api.corrections(daysAgo(30)));

  const kpis = useMemo(() => {
    const s = ready(sources);
    const a = ready(anomalies);
    const r = ready(rules);
    if (!s || !a || !r) return null;
    return operationsKpis(s, a, r.filter((rule) => !rule.passed).length);
  }, [sources, anomalies, rules]);

  return (
    <>
      <KpiRow kpis={kpis} colors={["#15803d", "#0891b2", "#dc2626", "#d97706"]} />
      <div className="grid">
        <Panel title="Fuentes" subtitle="Estado de la última carga de cada una y antigüedad de su último dato." wide>
          <Async state={sources}>
            {(rows) => (
              <Table
                rows={[...rows].sort((a, b) => (a.label ?? a.source).localeCompare(b.label ?? b.source, "es"))}
                columns={[
                  {
                    label: "Fuente",
                    value: (s) => (
                      <span className="source-cell">
                        <span className={`status status-${sourceState(s)}`} />
                        {s.label ?? s.source}
                      </span>
                    ),
                  },
                  { label: "Estado", value: (s) => <span className={`state state-${sourceState(s)}`}>{STATE_LABELS[sourceState(s)]}</span> },
                  { label: "Último dato", value: (s) => (s.data_age_hours === null ? "—" : age(s.data_age_hours)) },
                  { label: "Fallos 7 días", value: (s) => `${number((s.failure_rate_7d ?? 0) * 100)} %`, numeric: true },
                  { label: "Valores", value: (s) => compact(s.observations), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Reglas de calidad que fallan" subtitle="Último chequeo de cada regla: la fila se marca como sospechosa, no se borra.">
          <Async state={rules}>
            {(rows) => (
              <Table
                rows={rows.filter((r) => !r.passed).slice(0, 10)}
                empty="Todas las reglas pasan"
                columns={[
                  { label: "Fuente", value: (r) => r.source },
                  { label: "Regla", value: (r) => `${r.rule} · ${r.target}` },
                  { label: "Fallan", value: (r) => `${number(r.failed)} de ${number(r.checked)}`, numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Anomalías por día" subtitle="Valores que marca cada detector en los últimos 30 días; marcar no cambia el dato.">
          <Async state={anomalies}>{(rows) => <AnomaliesPerDay rows={rows} />}</Async>
        </Panel>
        <Panel title="Últimas correcciones" subtitle="Valores propuestos para huecos de las estaciones, con su método y su confianza." wide>
          <Async state={corrections}>
            {(rows) => (
              <Table
                rows={rows}
                empty="Ninguna corrección en los últimos 30 días"
                columns={[
                  { label: "Estación", value: (c) => `${c.entity} · ${c.metric}` },
                  { label: "Hora", value: (c) => `${dayShort(c.ts)} ${c.ts.slice(11, 16)}` },
                  { label: "Original", value: (c) => (c.original_value === null ? c.original_quality : number(c.original_value, 1)), numeric: true },
                  { label: "Corregido", value: (c) => `${number(c.corrected_value, 1)} ${c.unit ?? ""}`, numeric: true },
                  { label: "Método", value: (c) => (c.method === "support" ? "Fuente de apoyo" : "Interpolación") },
                  { label: "Confianza", value: (c) => `${number(c.confidence * 100)} %`, numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
