import { useCallback, useMemo } from "react";

import { api, daysAgo, type MobilityDay, type StopService } from "../api";
import { Async, Table } from "../components/Async";
import { Chart } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { type MapLayer, PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { compact, dayName, dayShort, number } from "../lib/format";
import type { Kpi } from "../lib/kpis";

const NETWORKS = {
  emt_palma: { label: "EMT Palma", detail: "autobuses urbanos de Palma", color: "#dc2626" },
  ctm: { label: "CTM", detail: "autobuses TIB, tren y metro de la isla", color: "#2563eb" },
} as const;

/** Key figures of the latest day of each network, with its daily trend. */
function mobilityKpis(days: MobilityDay[]): Kpi[] {
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).flatMap((network) => {
    const rows = days.filter((d) => d.network === network && d.scheduled_stop_calls !== null);
    const latest = rows.at(-1);
    if (!latest) return [];
    const { label } = NETWORKS[network];
    const history = rows.map((d) => ({ month: d.local_date, value: d.scheduled_stop_calls as number }));
    return [
      {
        id: `${network}-calls`, label: `${label} · pasos programados`, value: compact(latest.scheduled_stop_calls as number),
        unit: "", month: dayName(latest.local_date), deviation: latest.is_weekend ? "Fin de semana" : "Día laborable",
        tone: "neutral", history,
      },
      {
        id: `${network}-stops`, label: `${label} · paradas con servicio`, value: number(latest.stops_with_service),
        unit: `de ${number(latest.stops)}`, month: dayName(latest.local_date),
        deviation: latest.busiest_stop ? `Más servicio: ${latest.busiest_stop} (${number(latest.busiest_stop_departures ?? 0)})` : null,
        tone: "neutral", history: [],
      },
    ];
  });
}

function DailyCalls({ days }: { days: MobilityDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(days.map((d) => d.local_date))].sort();
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value", axisLabel: { formatter: compact } },
      tooltip: { valueFormatter: (v: number | null) => (v === null ? "—" : number(v)) },
      series: (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).map((network) => ({
        name: NETWORKS[network].label, type: "bar", color: NETWORKS[network].color, barGap: "10%",
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        data: dates.map((date) => days.find((d) => d.network === network && d.local_date === date)?.scheduled_stop_calls ?? null),
      })),
    };
  }, [days]);
  return <Chart option={option} label="Pasos programados por día en cada red" height={320} />;
}

function stopLayers(stops: StopService[]): MapLayer[] {
  return (Object.keys(NETWORKS) as (keyof typeof NETWORKS)[]).map((network) => {
    const own = stops.filter((s) => s.network === network);
    const busiest = Math.max(1, ...own.map((s) => s.departures ?? 0));
    return {
      id: network, label: NETWORKS[network].label, color: NETWORKS[network].color, radius: 2.2,
      points: own.map((s) => ({
        lat: s.lat, lon: s.lon,
        // Area proportional to the departures: the radius grows with their square root.
        size: 0.5 + 2 * Math.sqrt((s.departures ?? 0) / busiest),
        popup: [s.stop, NETWORKS[network].label, `${number(s.departures ?? 0)} pasos · ${number(s.lines ?? 0)} líneas`],
      })),
    };
  });
}

export function Mobility() {
  const daily = useLoad(() => api.mobilityDaily(daysAgo(60)));
  const stops = useLoad(api.stops);

  const kpis = useMemo(() => {
    const d = ready(daily);
    return d ? mobilityKpis(d) : null;
  }, [daily]);
  const layers = useMemo(() => (stops.status === "ready" ? stopLayers(stops.data) : []), [stops]);
  const stopDay = stops.status === "ready" && stops.data[0] ? dayName(stops.data[0].local_date) : "el último día";

  return (
    <>
      <KpiRow kpis={kpis} colors={[NETWORKS.emt_palma.color, NETWORKS.emt_palma.color, NETWORKS.ctm.color, NETWORKS.ctm.color]} />
      <div className="grid">
        <Panel title="Servicio por parada" subtitle={`Pasos programados en cada parada el ${stopDay}: cuanto más grande, más servicio.`} wide>
          <Async state={stops} height={480}>{() => <PointMap layers={layers} />}</Async>
        </Panel>
        <Panel title="Paradas con más servicio" subtitle="Las diez con más pasos programados de las dos redes.">
          <Async state={stops}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 10)}
                columns={[
                  { label: "Parada", value: (s) => s.stop },
                  { label: "Red", value: (s) => NETWORKS[s.network].label },
                  { label: "Pasos", value: (s) => number(s.departures ?? 0), numeric: true },
                  { label: "Líneas", value: (s) => number(s.lines ?? 0), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Pasos programados por día" subtitle="Suma de los vehículos que pasan por cada parada, según los horarios GTFS." wide>
          <Async state={daily} height={320}>{(rows) => <DailyCalls days={rows} />}</Async>
        </Panel>
      </div>
    </>
  );
}
