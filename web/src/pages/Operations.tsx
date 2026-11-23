import { useCallback, useMemo } from "react";

import { type AnomaliesDay, api, daysAgo, type DetectorBenchmark, type Source } from "../api";
import { Async, Table } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { messages } from "../i18n";
import { type BenchmarkRow, benchmarkRows, benchmarkWindow, FAULTS } from "../lib/benchmark";
import { age, compact, dayShort, number, placeName } from "../lib/format";
import type { Kpi } from "../lib/kpis";
import { byName, metricLabel } from "../lib/series";
import { accessLabel, slaText, sourceState, stateLabel } from "../lib/sources";

/** The colour of each detector; their names are in the dictionaries (`operations.detectors`). */
const DETECTORS: Record<string, { color: string }> = {
  robust_zscore: { color: "#d97706" },
  seasonal_residual: { color: "#0891b2" },
  isolation_forest: { color: "#7c3aed" },
  vote: { color: "#475569" },
};

/** The detector whose flags are the platform's answer: the vote, which already includes what its members flag. */
const COMBINED = "vote";

/**
 * A code in words, from one of the tables of the dictionaries: the correction methods (core/corrections/methods.py),
 * why an hour had no valid value, the quality rules (core/quality/rules.py) and the domains of the catalogue. A code
 * added later is shown as it is.
 */
function named(table: Record<string, string>, code: string): string {
  return table[code] ?? code;
}

/** Whether a source meets its SLA, and which part it misses. */
function SlaCell({ source }: { source: Source }) {
  const { met, age_met, success_met } = source.sla;
  if (met === null) return <span className="state state-inactive">—</span>;
  const m = messages().operations;
  if (met) return <span className="sla-met">{m.meets}</span>;
  return <span className="sla-breached" title={slaText(source)}>{m.breaches(age_met === false, success_met === false)}</span>;
}

function operationsKpis(sources: Source[], anomalies: AnomaliesDay[], failingRules: number): Kpi[] {
  const active = sources.filter((s) => sourceState(s) !== "inactive");
  const ok = active.filter((s) => sourceState(s) === "ok").length;
  const runs = active.reduce((n, s) => n + s.runs_7d, 0);
  const failed = active.reduce((n, s) => n + s.failed_7d, 0);
  const down = active.reduce((n, s) => n + s.unavailable_7d, 0);
  const combined = anomalies.filter((a) => a.detector === COMBINED);
  const flagged = (combined.length > 0 ? combined : anomalies).reduce((n, a) => n + a.anomalies, 0);
  const m = messages().operations;
  return [
    {
      id: "sources", label: m.sourcesUpToDate, value: `${ok}`, unit: m.of(String(active.length)), month: m.loadedIn36h,
      deviation: ok === active.length ? m.allUpToDate : m.notUpToDate(active.length - ok),
      tone: ok === active.length ? "good" : "bad", history: [],
    },
    {
      id: "values", label: m.valuesInSilver, value: compact(sources.reduce((n, s) => n + s.observations, 0)), unit: "",
      month: m.sourcesCount(sources.length), deviation: null, tone: "neutral", history: [],
    },
    {
      id: "runs", label: m.failedRuns, value: number(failed), unit: m.of(number(runs)), month: m.last7Days,
      // Our failures are the bad news; a source that was down recovers by itself and is only counted aside.
      deviation: down > 0 ? m.andDown(number(down)) : failed === 0 ? m.noFailures : null,
      tone: failed > 0 ? "bad" : down > 0 ? "neutral" : "good", history: [],
    },
    {
      id: "anomalies", label: m.anomalies, value: number(flagged), unit: "", month: m.last30Days,
      deviation: failingRules === 0 ? m.rulesPass : m.rulesFail(failingRules),
      tone: failingRules === 0 ? "good" : "bad", history: [],
    },
  ];
}

function AnomaliesPerDay({ rows }: { rows: AnomaliesDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(rows.map((r) => r.local_date))].sort();
    const names: Record<string, string> = messages().operations.detectors;
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value" },
      series: Object.entries(DETECTORS).map(([detector, { color }]) => ({
        name: named(names, detector), type: "bar", color, // side by side: the vote repeats what its members flag
        data: dates.map((d) => rows.find((r) => r.local_date === d && r.detector === detector)?.anomalies ?? 0),
      })),
    };
  }, [rows]);
  return <Chart option={option} label={messages().operations.anomaliesChart} />;
}

function percent(share: number | null): string {
  return share === null ? "—" : `${number(share * 100)} %`;
}

/** The days the latest benchmark covered, once it has loaded. */
function benchmarkSubtitle(rows: DetectorBenchmark[] | null): string {
  const window = rows ? benchmarkWindow(rows) : null;
  return messages().operations.benchmarkSubtitle(window ? dayShort(window.from) : "…", window ? dayShort(window.to) : "…");
}

/** How each detector did against the injected faults, one row per source and detector. */
function Benchmark({ rows, sources }: { rows: DetectorBenchmark[]; sources: Source[] | null }) {
  const m = messages().operations;
  const labels = new Map((sources ?? []).map((s) => [s.source, s.label ?? s.source]));
  return (
    <Table
      rows={benchmarkRows(rows)}
      empty={m.noBenchmark}
      columns={[
        {
          label: m.detector,
          value: (r) => (
            <span className="stacked">
              <strong>{named(m.detectors, r.detector)}</strong>
              <small>{labels.get(r.source) ?? r.source}</small>
            </span>
          ),
        },
        ...FAULTS.map((fault) => ({ label: m.faults[fault], value: (r: BenchmarkRow) => percent(r.caught[fault]), numeric: true })),
        { label: m.precision, value: (r) => percent(r.precision), numeric: true },
        { label: m.falseAlarms, value: (r) => (r.falseAlarms === null ? "—" : number(r.falseAlarms)), numeric: true },
      ]}
    />
  );
}

export function Operations() {
  const sources = useLoad(api.sources);
  const anomalies = useLoad(() => api.anomaliesDaily(daysAgo(30)));
  const rules = useLoad(api.qualityRules);
  const corrections = useLoad(() => api.corrections(daysAgo(30)));
  const benchmark = useLoad(api.detectorBenchmark);

  const kpis = useMemo(() => {
    const s = ready(sources);
    const a = ready(anomalies);
    const r = ready(rules);
    if (!s || !a || !r) return null;
    return operationsKpis(s, a, r.filter((rule) => !rule.passed).length);
  }, [sources, anomalies, rules]);
  const m = messages().operations;

  return (
    <>
      <KpiRow kpis={kpis} colors={["#15803d", "#0891b2", "#dc2626", "#d97706"]} />
      <div className="grid">
        <Panel title={m.sourcesTitle} subtitle={m.sourcesSubtitle} wide>
          <Async state={sources}>
            {(rows) => (
              <Table
                rows={[...rows].sort((a, b) => byName(a.label ?? a.source, b.label ?? b.source))}
                columns={[
                  {
                    label: m.source,
                    value: (s) => (
                      <span className="source-cell">
                        <span className={`status status-${sourceState(s)}`} />
                        {s.label ?? s.source}
                      </span>
                    ),
                  },
                  { label: m.state, value: (s) => <span className={`state state-${sourceState(s)}`}>{stateLabel(sourceState(s))}</span> },
                  { label: m.lastValue, value: (s) => (s.data_age_hours === null ? "—" : age(s.data_age_hours)) },
                  { label: m.notLoaded7Days, value: (s) => `${number((s.failure_rate_7d ?? 0) * 100)} %`, numeric: true },
                  { label: m.sla, value: (s) => <SlaCell source={s} /> },
                  { label: m.values, value: (s) => compact(s.observations), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title={m.governanceTitle}
          subtitle={m.governanceSubtitle}
          wide
        >
          <Async state={sources}>
            {(rows) => (
              <Table
                rows={[...rows].sort((a, b) => a.governance.domain.localeCompare(b.governance.domain) || byName(a.label ?? a.source, b.label ?? b.source))}
                columns={[
                  {
                    label: m.source,
                    value: (s) => (
                      <span className="stacked">
                        <strong>{s.label ?? s.source}</strong>
                        <small>{named(m.domains, s.governance.domain)}</small>
                      </span>
                    ),
                  },
                  { label: m.owner, value: (s) => s.governance.owner },
                  {
                    label: m.licence,
                    value: (s) => (
                      <a href={s.governance.terms_url} target="_blank" rel="noreferrer">
                        {s.governance.license}
                      </a>
                    ),
                  },
                  { label: m.access, value: (s) => accessLabel(s.governance.access) },
                  { label: m.personalData, value: (s) => (s.governance.personal_data ? m.yes : m.no) },
                  { label: m.slaShort, value: (s) => (s.governance.lifecycle === "history" ? stateLabel("inactive") : slaText(s)) },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.rulesTitle} subtitle={m.rulesSubtitle}>
          <Async state={rules}>
            {(rows) => (
              <Table
                rows={rows.filter((r) => !r.passed).slice(0, 10)}
                empty={m.allRulesPass}
                columns={[
                  {
                    label: m.rule,
                    value: (r) => (
                      <span className="stacked">
                        <strong>{named(m.rules, r.rule)}</strong> · {r.target}
                        <small>{r.source}</small>
                      </span>
                    ),
                  },
                  { label: m.failing, value: (r) => `${number((r.failed_ratio ?? 0) * 100, 1)} %`, numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.anomaliesTitle} subtitle={m.anomaliesSubtitle}>
          <Async state={anomalies}>{(rows) => <AnomaliesPerDay rows={rows} />}</Async>
        </Panel>
        <Panel title={m.benchmarkTitle} subtitle={benchmarkSubtitle(ready(benchmark))} wide>
          <Async state={benchmark}>{(rows) => <Benchmark rows={rows} sources={ready(sources)} />}</Async>
        </Panel>
        <Panel title={m.correctionsTitle} subtitle={m.correctionsSubtitle} wide>
          <Async state={corrections}>
            {(rows) => (
              <Table
                rows={rows}
                empty={m.noCorrections}
                columns={[
                  { label: m.station, value: (c) => `${placeName(c.entity, c.name)} · ${metricLabel(c.metric)}` },
                  { label: m.hour, value: (c) => `${dayShort(c.ts)} ${c.ts.slice(11, 16)}` },
                  { label: m.original, value: (c) => (c.original_value === null ? named(m.quality, c.original_quality) : number(c.original_value, 1)), numeric: true },
                  { label: m.corrected, value: (c) => `${number(c.corrected_value, 1)} ${c.unit ?? ""}`, numeric: true },
                  { label: m.method, value: (c) => named(m.methods, c.method) },
                  { label: m.confidence, value: (c) => `${number(c.confidence * 100)} %`, numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
