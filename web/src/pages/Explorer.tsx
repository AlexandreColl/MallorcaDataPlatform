import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type Series, type SeriesDay, type Source } from "../api";
import { Async } from "../components/Async";
import { Chart, type ChartColors } from "../components/Chart";
import { Panel } from "../components/Layout";
import { ready, useLoad } from "../hooks";
import { dayName, number, orDash, placeName } from "../lib/format";
import {
  axisDate,
  entitiesOf,
  longest,
  metricLabel,
  metricsOf,
  type Range,
  RANGES,
  rangeStart,
  spanOf,
  summarize,
  unitLabel,
} from "../lib/series";

/** The selection lives in the address (?source=aemet&metric=…&entity=…&range=year), so a view can be shared. */
interface Selection {
  source: string;
  metric: string | null;
  entity: string | null;
  range: Range;
}

function readSelection(): Selection {
  const params = new URLSearchParams(window.location.search);
  const range = params.get("range");
  return {
    source: params.get("source") ?? "aemet",
    metric: params.get("metric"),
    entity: params.get("entity"),
    range: range && range in RANGES ? (range as Range) : "year",
  };
}

function writeSelection(s: Selection) {
  const params = new URLSearchParams({ source: s.source, range: s.range });
  if (s.metric) params.set("metric", s.metric);
  if (s.entity) params.set("entity", s.entity);
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}

const ANOMALY = "#dc2626";

/** The daily mean over the band of the daily minimum and maximum, with the days the detectors flagged. */
function SeriesChart({ days, unit }: { days: SeriesDay[]; unit: string }) {
  const option = useCallback(
    (c: ChartColors) => {
      const byDate = new Map(days.map((d) => [d.local_date, d]));
      const suffix = unit ? ` ${unit}` : "";
      const value = orDash((v) => `${number(v, 1)}${suffix}`);
      const span = spanOf(days);
      return {
        xAxis: { type: "time", axisLabel: { formatter: (v: number) => axisDate(v, span) } },
        yAxis: { type: "value", scale: true, axisLabel: { formatter: (v: number) => `${number(v, 1)}${suffix}` } },
        legend: { data: ["Media", "Mínimo y máximo", "Anomalías"] },
        tooltip: {
          formatter: (params: { value: [string, number] }[]) => {
            const day = byDate.get(String(params[0]?.value[0]).slice(0, 10));
            if (!day) return "";
            const flagged = day.anomalies ? `<br/>${number(day.anomalies)} valores anómalos` : "";
            const suspect = day.suspect ? `<br/>${number(day.suspect)} sospechosos` : "";
            return `<strong>${dayName(day.local_date)}</strong><br/>Media ${value(day.avg_value)}<br/>Mínimo ${value(day.min_value)} · máximo ${value(day.max_value)}<br/>Completitud ${number((day.completeness ?? 0) * 100)} %${suspect}${flagged}`;
          },
        },
        series: [
          // The band is two stacked lines: the minimum (invisible) and the distance to the maximum (filled).
          {
            name: "Mínimo", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 }, silent: true,
            data: days.map((d) => [d.local_date, d.min_value]),
          },
          {
            name: "Mínimo y máximo", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 },
            areaStyle: { color: c.muted, opacity: 0.18 }, color: c.muted, silent: true,
            data: days.map((d) => [d.local_date, d.max_value === null || d.min_value === null ? null : d.max_value - d.min_value]),
          },
          {
            name: "Media", type: "line", symbol: "none", sampling: "lttb", color: "#15803d", lineStyle: { width: 1.5 },
            data: days.map((d) => [d.local_date, d.avg_value]),
          },
          {
            name: "Anomalías", type: "scatter", symbolSize: 6, color: ANOMALY,
            data: days.filter((d) => d.anomalies > 0 && d.avg_value !== null).map((d) => [d.local_date, d.avg_value]),
          },
        ],
      };
    },
    [days, unit],
  );
  return <Chart option={option} label="Media diaria de la serie con su mínimo y su máximo" height={380} />;
}

/** Share of the day's samples that have a value, one bar per day. */
function CompletenessChart({ days }: { days: SeriesDay[] }) {
  const option = useCallback(
    () => ({
      xAxis: { type: "time", axisLabel: { formatter: (v: number) => axisDate(v, spanOf(days)) } },
      yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value} %" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v)} %`) },
      legend: { show: false },
      grid: { top: 12 },
      series: [
        {
          name: "Completitud", type: "bar", barMaxWidth: 6, color: "#2563eb",
          data: days.map((d) => [d.local_date, d.completeness === null ? null : d.completeness * 100]),
        },
      ],
    }),
    [days],
  );
  return <Chart option={option} label="Completitud diaria de la serie" height={160} />;
}

function Summary({ days, unit }: { days: SeriesDay[]; unit: string }) {
  const s = summarize(days);
  const suffix = unit ? ` ${unit}` : "";
  const value = (v: number | null) => (v === null ? "—" : `${number(v, 1)}${suffix}`);
  const items: [string, string][] = [
    ["Días", number(s.days)],
    ["Completitud", s.completeness === null ? "—" : `${number(s.completeness * 100, 1)} %`],
    ["Sospechosos", number(s.suspect)],
    ["Anomalías", number(s.anomalies)],
    ["Mínimo", value(s.min)],
    ["Media", value(s.mean)],
    ["Máximo", value(s.max)],
  ];
  return (
    <dl className="series-stats">
      {items.map(([label, text]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{text}</dd>
        </div>
      ))}
    </dl>
  );
}

function Controls({ sources, catalog, selection, onChange }: {
  sources: Source[];
  catalog: Series[];
  selection: Selection;
  onChange: (s: Selection) => void;
}) {
  const metrics = metricsOf(catalog);
  const entities = selection.metric ? entitiesOf(catalog, selection.metric) : [];
  return (
    <div className="controls">
      <label className="select-row">
        <span>Fuente</span>
        <select
          className="select"
          value={selection.source}
          onChange={(e) => onChange({ ...selection, source: e.target.value, metric: null, entity: null })}
        >
          {sources.map((s) => (
            <option key={s.source} value={s.source}>
              {s.label ?? s.source}
            </option>
          ))}
        </select>
      </label>
      <label className="select-row">
        <span>Métrica</span>
        <select
          className="select"
          value={selection.metric ?? ""}
          onChange={(e) => onChange({ ...selection, metric: e.target.value, entity: null })}
        >
          {metrics.map((m) => (
            <option key={m} value={m}>
              {metricLabel(m)}
            </option>
          ))}
        </select>
      </label>
      <label className="select-row">
        <span>Entidad</span>
        <select
          className="select"
          value={selection.entity ?? ""}
          onChange={(e) => onChange({ ...selection, entity: e.target.value })}
        >
          {entities.map((s) => (
            <option key={s.entity} value={s.entity}>
              {placeName(s.entity, s.name)}
            </option>
          ))}
        </select>
      </label>
      <div className="segmented" role="group" aria-label="Periodo">
        {(Object.keys(RANGES) as Range[]).map((r) => (
          <button key={r} type="button" aria-pressed={r === selection.range} onClick={() => onChange({ ...selection, range: r })}>
            {RANGES[r]}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Explorer() {
  const [selection, setSelection] = useState<Selection>(readSelection);
  const sources = useLoad(api.sources);
  const catalog = useLoad(() => api.series(selection.source), [selection.source]);

  // The catalog of the source fills a missing or unknown metric and entity: the longest series of the metric.
  const series = useMemo((): Series | null => {
    const all = ready(catalog);
    if (!all || all.length === 0 || all[0]?.source !== selection.source) return null;
    const metric = selection.metric && all.some((s) => s.metric === selection.metric) ? selection.metric : longest(all)?.metric;
    const ofMetric = all.filter((s) => s.metric === metric);
    return ofMetric.find((s) => s.entity === selection.entity) ?? longest(ofMetric) ?? null;
  }, [catalog, selection]);

  useEffect(() => {
    if (series && (series.metric !== selection.metric || series.entity !== selection.entity)) {
      setSelection((s) => ({ ...s, metric: series.metric, entity: series.entity }));
    }
  }, [series, selection.metric, selection.entity]);
  useEffect(() => writeSelection(selection), [selection]);

  const from = series ? rangeStart(series, selection.range) : null;
  const days = useLoad(
    () => (series && from ? api.seriesDaily(series, from) : Promise.resolve([] as SeriesDay[])),
    [series?.source, series?.entity, series?.metric, from],
  );

  const unit = unitLabel(series?.unit);
  const sourceLabel = ready(sources)?.find((s) => s.source === selection.source)?.label ?? selection.source;
  const subtitle = series
    ? `${sourceLabel} · ${placeName(series.entity, series.name)} (${series.entity}) · ${metricLabel(series.metric)}${unit ? ` en ${unit}` : ""}. Datos del ${dayName(series.first_day)} al ${dayName(series.last_day)}; la banda va del mínimo al máximo de cada día y los puntos rojos son días con valores anómalos.`
    : "Elige una fuente, una métrica y una entidad.";

  return (
    <div className="grid">
      <Panel title={series ? `${metricLabel(series.metric)} · ${placeName(series.entity, series.name)}` : "Serie"} subtitle={subtitle} full>
        <Async state={sources} height={40}>
          {(list) => (
            <Async state={catalog} height={40}>
              {(all) => <Controls sources={list} catalog={all} selection={selection} onChange={setSelection} />}
            </Async>
          )}
        </Async>
        <Async state={days} height={380}>
          {(rows) =>
            rows.length === 0 ? (
              <p className="empty">Sin datos en el periodo</p>
            ) : (
              <>
                <Summary days={rows} unit={unit} />
                <SeriesChart days={rows} unit={unit} />
                <h3 className="chart-title">Completitud por día</h3>
                <CompletenessChart days={rows} />
              </>
            )
          }
        </Async>
      </Panel>
    </div>
  );
}
