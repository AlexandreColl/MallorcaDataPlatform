import { useCallback, useMemo } from "react";

import type { Municipality, PopulationYear } from "../api";
import { compact, number, signed } from "../lib/format";
import { PALMA } from "../lib/mobility";
import { islandTotals } from "../lib/population";
import { segmentedTrend } from "../lib/stats";
import { Chart, type ChartColors } from "./Chart";

/** The trend is carried on to this year, with its 95 % prediction interval. */
const PROJECTION_YEAR = 2030;

interface HistoryProps {
  rows: PopulationYear[];
  places: Municipality[];
  selected: string | null;
  onSelect: (code: string | null) => void;
}

/**
 * Population on 1 January since 1996, of the island (Palma and the rest) or of one municipality, with its trend in
 * one or two stretches and the last one carried on to 2030.
 */
export function PopulationHistory({ rows, places, selected, onSelect }: HistoryProps) {
  const place = places.find((p) => p.municipality === selected);
  const option = useCallback((c: ChartColors) => {
    const series: { year: number; value: number }[] = place
      ? rows
          .filter((r) => r.municipality === place.municipality && r.population !== null)
          .map((r) => ({ year: r.year, value: r.population as number }))
          .sort((a, b) => a.year - b.year)
      : islandTotals(rows).map((t) => ({ year: t.year, value: t.population }));
    const years = series.map((s) => s.year);
    const last = years.at(-1) ?? PROJECTION_YEAR;
    const ahead = Array.from({ length: Math.max(0, PROJECTION_YEAR - last) }, (_, i) => last + 1 + i);
    const categories = [...years, ...ahead];
    const trends = segmentedTrend(series);
    const latest = trends.at(-1);
    const projected = (year: number) => year >= last && latest !== undefined;
    const band = categories.map((year) => (projected(year) ? latest?.interval(year) : undefined));
    const value = new Map(series.map((s) => [s.year, s.value]));
    const palma = new Map(rows.filter((r) => r.municipality === PALMA).map((r) => [r.year, r.population ?? 0]));
    const bars = place
      ? [
          {
            name: place.name, type: "bar", color: "#15803d", itemStyle: { borderRadius: [3, 3, 0, 0] },
            data: categories.map((year) => value.get(year) ?? null),
          },
        ]
      : [
          { name: "Palma", type: "bar", stack: "island", color: "#15803d", data: categories.map((y) => palma.get(y) ?? null) },
          {
            name: "Resto de la isla", type: "bar", stack: "island", color: "#86efac", itemStyle: { borderRadius: [3, 3, 0, 0] },
            data: categories.map((y) => (value.has(y) ? (value.get(y) as number) - (palma.get(y) ?? 0) : null)),
          },
        ];
    const lines = trends.map((trend, i) => ({
      name: `${trend.from}–${trend.to}: ${signed(trend.rate * 100)} %/año`,
      type: "line", symbol: "none", z: 3, color: i === trends.length - 1 ? "#b45309" : "#7c3aed",
      lineStyle: { type: "dashed", width: 2 },
      data: categories.map((year) => (year >= trend.from && year <= trend.to ? Math.round(trend.at(year)) : null)),
    }));
    const projection = latest
      ? [
          {
            name: `Proyección a ${PROJECTION_YEAR}`, type: "line", symbol: "none", z: 3, color: "#b45309",
            lineStyle: { type: "dotted", width: 2 },
            data: categories.map((year) => (projected(year) ? Math.round(latest.at(year)) : null)),
          },
          // The interval as a band: an invisible line at its bottom and the width stacked on top of it.
          {
            name: "band-low", type: "line", symbol: "none", stack: "band", lineStyle: { opacity: 0 },
            data: band.map((b) => (b ? Math.round(b[0]) : null)),
          },
          {
            name: "band-width", type: "line", symbol: "none", stack: "band", lineStyle: { opacity: 0 },
            areaStyle: { color: "#b45309", opacity: 0.15 },
            data: band.map((b) => (b ? Math.round(b[1] - b[0]) : null)),
          },
        ]
      : [];
    return {
      xAxis: { type: "category", data: categories.map(String) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      // One line that scrolls on a phone: five entries would wrap over the chart.
      legend: {
        type: "scroll", top: 0, left: 0, right: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, itemGap: 16,
        textStyle: { color: c.muted }, pageTextStyle: { color: c.muted },
        data: [...bars, ...lines, ...projection].map((s) => s.name).filter((n) => !n.startsWith("band-")),
      },
      tooltip: {
        // Each series with a value that year, and the interval as a range instead of its two stacked parts.
        formatter: (params: { seriesName: string; value: unknown; marker: string; dataIndex: number; name: string }[]) => {
          const shown = params.filter((p) => typeof p.value === "number" && !p.seriesName.startsWith("band-"));
          const lines = shown.map((p) => `${p.marker} ${p.seriesName} <b>${number(p.value as number)}</b>`);
          const b = band[params[0]?.dataIndex ?? -1];
          if (b) lines.push(`Intervalo del 95 %: ${number(Math.round(b[0]))} – ${number(Math.round(b[1]))}`);
          return [params[0]?.name ?? "", ...lines].join("<br/>");
        },
      },
      series: [...lines, ...projection, ...bars],
    };
  }, [rows, place]);

  const sorted = useMemo(() => [...places].sort((a, b) => a.name.localeCompare(b.name, "es")), [places]);
  return (
    <>
      <label className="select-row">
        <span>Municipio</span>
        <select className="select" aria-label="Municipio" value={selected ?? ""} onChange={(e) => onSelect(e.target.value || null)}>
          <option value="">Toda la isla</option>
          {sorted.map((p) => (
            <option key={p.municipality} value={p.municipality}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <Chart
        option={option}
        label={`Población de ${place?.name ?? "Mallorca"} a 1 de enero, con su tendencia y la proyección a ${PROJECTION_YEAR}`}
        height={340}
      />
    </>
  );
}
