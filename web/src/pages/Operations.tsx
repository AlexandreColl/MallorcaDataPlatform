import { useCallback, useMemo } from "react";

import { type AnomaliesDay, api, daysAgo, type Source } from "../api";
import { Async, Table } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { age, compact, dayShort, number, placeName } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { ACCESS_LABELS, slaText, sourceState, STATE_LABELS } from "../lib/sources";

const DETECTORS: Record<string, { label: string; color: string }> = {
  robust_zscore: { label: "Z-score robusto", color: "#d97706" },
  isolation_forest: { label: "Isolation Forest", color: "#7c3aed" },
};

/** Why a station hour had no valid value. */
const QUALITY: Record<string, string> = { missing: "falta", suspect: "dudoso", absent: "sin dato" };

/** The quality rules in words (core/quality/rules.py). */
const RULES: Record<string, string> = {
  gaps: "Huecos",
  range: "Fuera de rango",
  duplicate: "Duplicados",
  not_null: "Nulos",
  source_qc: "Dudoso según la fuente",
};

/** The domains of the catalogue of sources (dim_sources) in words. */
const DOMAINS: Record<string, string> = {
  weather: "Tiempo", air: "Calidad del aire", sea: "Mar", energy: "Energía", seismic: "Sismos",
  mobility: "Movilidad", tourism: "Turismo", water: "Agua", population: "Población",
};

/** Whether a source meets its SLA, and which part it misses. */
function SlaCell({ source }: { source: Source }) {
  const { met, age_met, success_met } = source.sla;
  if (met === null) return <span className="state state-inactive">—</span>;
  if (met) return <span className="sla-met">Cumple</span>;
  const missed = [age_met === false && "dato antiguo", success_met === false && "fallos"].filter(Boolean).join(" y ");
  return <span className="sla-breached" title={slaText(source)}>Incumple ({missed})</span>;
}

function operationsKpis(sources: Source[], anomalies: AnomaliesDay[], failingRules: number): Kpi[] {
  const active = sources.filter((s) => sourceState(s) !== "inactive");
  const ok = active.filter((s) => sourceState(s) === "ok").length;
  const runs = active.reduce((n, s) => n + s.runs_7d, 0);
  const failed = active.reduce((n, s) => n + s.failed_7d, 0);
  const down = active.reduce((n, s) => n + s.unavailable_7d, 0);
  const flagged = anomalies.reduce((n, a) => n + a.anomalies, 0);
  return [
    {
      id: "sources", label: "Fuentes al día", value: `${ok}`, unit: `de ${active.length}`, month: "Carga correcta en 36 h y dentro de su SLA",
      deviation: ok === active.length ? "Todas al día" : `${active.length - ok} caídas, atrasadas, con fallos o fuera de SLA`,
      tone: ok === active.length ? "good" : "bad", history: [],
    },
    {
      id: "values", label: "Valores en silver", value: compact(sources.reduce((n, s) => n + s.observations, 0)), unit: "",
      month: `${sources.length} fuentes`, deviation: null, tone: "neutral", history: [],
    },
    {
      id: "runs", label: "Ejecuciones fallidas", value: number(failed), unit: `de ${number(runs)}`, month: "Últimos 7 días",
      // Our failures are the bad news; a source that was down recovers by itself and is only counted aside.
      deviation: down > 0 ? `y ${number(down)} con la fuente caída` : failed === 0 ? "Ningún fallo" : null,
      tone: failed > 0 ? "bad" : down > 0 ? "neutral" : "good", history: [],
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
                  { label: "Sin cargar 7 días", value: (s) => `${number((s.failure_rate_7d ?? 0) * 100)} %`, numeric: true },
                  { label: "SLA", value: (s) => <SlaCell source={s} /> },
                  { label: "Valores", value: (s) => compact(s.observations), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title="Gobierno del dato"
          subtitle="Dueño, licencia y acceso de cada fuente, y el SLA acordado: antigüedad máxima del último dato y cargas correctas en 7 días."
          wide
        >
          <Async state={sources}>
            {(rows) => (
              <Table
                rows={[...rows].sort((a, b) => a.governance.domain.localeCompare(b.governance.domain) || (a.label ?? a.source).localeCompare(b.label ?? b.source, "es"))}
                columns={[
                  {
                    label: "Fuente",
                    value: (s) => (
                      <span className="stacked">
                        <strong>{s.label ?? s.source}</strong>
                        <small>{DOMAINS[s.governance.domain] ?? s.governance.domain}</small>
                      </span>
                    ),
                  },
                  { label: "Dueño", value: (s) => s.governance.owner },
                  {
                    label: "Licencia",
                    value: (s) => (
                      <a href={s.governance.terms_url} target="_blank" rel="noreferrer">
                        {s.governance.license}
                      </a>
                    ),
                  },
                  { label: "Acceso", value: (s) => ACCESS_LABELS[s.governance.access] },
                  { label: "Datos personales", value: (s) => (s.governance.personal_data ? "Sí" : "No") },
                  { label: "SLA (dato · cargas)", value: (s) => (s.governance.lifecycle === "history" ? "Histórico" : slaText(s)) },
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
                  {
                    label: "Regla",
                    value: (r) => (
                      <span className="stacked">
                        <strong>{RULES[r.rule] ?? r.rule}</strong> · {r.target}
                        <small>{r.source}</small>
                      </span>
                    ),
                  },
                  { label: "Fallan", value: (r) => `${number((r.failed_ratio ?? 0) * 100, 1)} %`, numeric: true },
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
                  { label: "Estación", value: (c) => `${placeName(c.entity, c.name)} · ${c.metric}` },
                  { label: "Hora", value: (c) => `${dayShort(c.ts)} ${c.ts.slice(11, 16)}` },
                  { label: "Original", value: (c) => (c.original_value === null ? (QUALITY[c.original_quality] ?? c.original_quality) : number(c.original_value, 1)), numeric: true },
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
