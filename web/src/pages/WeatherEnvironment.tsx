import { useCallback, useMemo, useState } from "react";

import { api, daysAgo, type SeaHour, type WeatherSourceDay } from "../api";
import { Async, Table } from "../components/Async";
import { Chart, SERIES } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { PointMap } from "../components/PointMap";
import { TemperatureZones } from "../components/TemperatureZones";
import { WarningsMap } from "../components/WarningsMap";
import { ready, useLoad } from "../hooks";
import { airLayers, EAQI, environmentKpis, episodeType, localTime, temperatureSubtitle } from "../lib/environment";
import { dayName, dayShort, number, orDash, placeName, signed } from "../lib/format";
import { describe, LEVELS } from "../lib/warnings";

function DailyTemperature({ days }: { days: WeatherSourceDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(days.map((d) => d.local_date))].sort();
    const sources = [...new Set(days.map((d) => d.source))];
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: "{value} °C" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} °C`) },
      // The three source names take two lines in the narrow panel: room for both above the plot.
      grid: { top: 60 },
      series: sources.map((source) => ({
        name: days.find((d) => d.source === source)?.source_label ?? source,
        type: "line", smooth: true, symbol: "none", connectNulls: true,
        data: dates.map((date) => days.find((d) => d.source === source && d.local_date === date)?.temperature_mean ?? null),
      })),
    };
  }, [days]);
  return <Chart option={option} label="Temperatura media diaria de cada fuente" height={300} />;
}

function Waves({ hours }: { hours: SeaHour[] }) {
  const option = useCallback(() => {
    const points = [...new Set(hours.map((h) => h.point))];
    return {
      xAxis: {
        type: "time", minInterval: 86_400_000, // one label per day, never two of the same day
        axisLabel: { formatter: (v: number) => dayShort(new Date(v).toISOString()) },
      },
      yAxis: { type: "value", axisLabel: { formatter: "{value} m" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 2)} m`) },
      legend: { type: "scroll", top: 0, left: 0, right: 0 },
      series: points.map((point, i) => ({
        name: placeName(point, hours.find((h) => h.point === point)?.name), type: "line", symbol: "none",
        color: SERIES[i % SERIES.length],
        data: hours.filter((h) => h.point === point).map((h) => [h.ts, h.wave_height_m]),
      })),
    };
  }, [hours]);
  return <Chart option={option} label="Altura de ola en cada punto de la costa" height={300} />;
}

export function WeatherEnvironment() {
  const weather = useLoad(() => api.weatherDaily(daysAgo(30)));
  const air = useLoad(api.airQuality);
  const sea = useLoad(() => api.sea(daysAgo(7)));
  const episodes = useLoad(() => api.episodes(daysAgo(365)));
  const quakes = useLoad(api.earthquakes);
  const bias = useLoad(api.modelBias);

  const kpis = useMemo(() => {
    const w = ready(weather);
    const a = ready(air);
    const s = ready(sea);
    const q = ready(quakes);
    if (!w || !a || !s || !q) return null;
    const lastYear = q.filter((e) => Date.parse(e.ts) > Date.now() - 365 * 86_400_000).length;
    return environmentKpis(w, a, s, lastYear);
  }, [weather, air, sea, quakes]);
  const layers = useMemo(() => (air.status === "ready" ? airLayers(air.data) : []), [air]);
  const [day, setDay] = useState<string | null>(null); // null: the latest day AEMET has published
  const stations = useLoad(() => api.stations("aemet", day), [day]);
  const aemetDays = useMemo(
    () =>
      (ready(weather) ?? [])
        .filter((d) => d.source === "aemet" && d.temperature_mean !== null)
        .map((d) => d.local_date.slice(0, 10))
        .reverse(),
    [weather],
  );
  const places = useLoad(api.municipalities);
  const warnings = useLoad(api.warnings);
  const zones = useLoad(api.warningZones);

  return (
    <>
      <KpiRow kpis={kpis} colors={["#dc2626", "#0891b2", "#2563eb", "#7c3aed"]} />
      <div className="grid">
        <Panel title="Avisos de AEMET" subtitle="Zonas de aviso de Mallorca con el nivel más alto en vigor o anunciado; pulsa una zona para ver sus avisos." wide>
          <Async state={zones} height={420}>
            {(z) => <Async state={warnings} height={420}>{(w) => <WarningsMap zones={z} warnings={w} />}</Async>}
          </Async>
        </Panel>
        <Panel title="Avisos en vigor y anunciados" subtitle="Los próximos 3 días, por orden de inicio (hora de Mallorca).">
          <Async state={warnings}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 12)}
                empty="Ningún aviso en los próximos 3 días"
                columns={[
                  {
                    label: "Aviso",
                    value: (w) => (
                      <span className="source-cell">
                        <span className="dot" style={{ background: LEVELS[w.level]?.color }} />
                        <span className="stacked">
                          {describe(w)}
                          <small>{w.zone_name ?? w.zone}{w.zone_kind === "coast" ? " (costa)" : ""}</small>
                        </span>
                      </span>
                    ),
                  },
                  { label: "Desde", value: (w) => localTime(w.start_ts) },
                  { label: "Hasta", value: (w) => localTime(w.end_ts) },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title="Temperatura por zonas"
          subtitle={temperatureSubtitle(ready(stations), day)}
          wide
        >
          <Async state={stations} height={480}>
            {(rows) => <Async state={places} height={480}>{(p) => <TemperatureZones stations={rows} places={p} days={aemetDays} onDay={setDay} />}</Async>}
          </Async>
        </Panel>
        <Panel title="Temperatura de los últimos 30 días" subtitle="Media diaria de la isla según cada fuente: estaciones oficiales frente al modelo.">
          <Async state={weather} height={300}>{(rows) => <DailyTemperature days={rows} />}</Async>
        </Panel>
        <Panel title="Calidad del aire ahora" subtitle="Índice europeo de la última hora: el color es el del peor contaminante." wide>
          <Async state={air} height={480}>
            {() => (
              <>
                <PointMap layers={layers} height={480} />
                <div className="scale">
                  {EAQI.slice(0, 4).map((b) => (
                    <span key={b.label}>
                      <span className="dot" style={{ background: b.color }} /> {b.label}
                    </span>
                  ))}
                </div>
              </>
            )}
          </Async>
        </Panel>
        <Panel title="Estaciones de calidad del aire" subtitle="Concentraciones de la última hora en µg/m³, de la peor a la mejor.">
          <Async state={air}>
            {(rows) => (
              <Table
                rows={rows.filter((a) => a.source === "eea_air_quality").sort((a, b) => b.eaqi_band - a.eaqi_band)}
                columns={[
                  {
                    label: "Estación",
                    value: (a) => (
                      <span className="source-cell">
                        <span className="dot" style={{ background: EAQI[a.eaqi_band - 1]?.color }} />
                        {placeName(a.entity, a.name)}
                      </span>
                    ),
                  },
                  { label: "NO₂", value: (a) => (a.no2 === null ? "—" : number(a.no2)), numeric: true },
                  { label: "O₃", value: (a) => (a.o3 === null ? "—" : number(a.o3)), numeric: true },
                  { label: "PM10", value: (a) => (a.pm10 === null ? "—" : number(a.pm10)), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Oleaje de la última semana" subtitle="Altura significativa de ola en los puntos de la costa (modelo)." wide>
          <Async state={sea} height={300}>{(rows) => <Waves hours={rows} />}</Async>
        </Panel>
        <Panel title="Episodios del último año" subtitle="Días seguidos de lluvia intensa, viento fuerte o mar alta en algún punto de la isla.">
          <Async state={episodes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                empty="Ningún episodio en el último año"
                columns={[
                  { label: "Inicio", value: (e) => dayShort(e.start_date) },
                  { label: "Tipo", value: (e) => episodeType(e.episode_type) },
                  { label: "Lluvia", value: (e) => (e.peak_rain_mm === null ? "—" : `${number(e.peak_rain_mm, 0)} mm`), numeric: true },
                  { label: "Racha", value: (e) => (e.peak_gust_kmh === null ? "—" : `${number(e.peak_gust_kmh, 0)} km/h`), numeric: true },
                  { label: "Ola", value: (e) => (e.peak_wave_m === null ? "—" : `${number(e.peak_wave_m, 1)} m`), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title="Sismos" subtitle="Localizados por el IGN en Mallorca y el mar que la rodea.">
          <Async state={quakes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                empty="Ningún sismo"
                columns={[
                  { label: "Fecha", value: (e) => dayName(e.ts) },
                  { label: "Magnitud", value: (e) => (e.magnitude === null ? "—" : number(e.magnitude, 1)), numeric: true },
                  { label: "Profundidad", value: (e) => (e.depth_km === null ? "—" : `${number(e.depth_km, 0)} km`), numeric: true },
                  { label: "A Palma", value: (e) => (e.distance_to_palma_km === null ? "—" : `${number(e.distance_to_palma_km, 0)} km`), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title="Modelo frente a estaciones"
          subtitle="Error del modelo en la temperatura media diaria de cada estación de AEMET y SOCIB, a la altura de la estación (6,5 °C por km de desnivel con su celda)."
        >
          <Async state={bias}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                columns={[
                  { label: "Estación", value: (b) => b.station_name ?? b.station },
                  { label: "Desnivel", value: (b) => (b.elevation_diff_m === null ? "—" : `${signed(Number(b.elevation_diff_m), 0)} m`), numeric: true },
                  { label: "Sesgo bruto", value: (b) => (b.temperature_bias_c === null ? "—" : `${signed(Number(b.temperature_bias_c))} °C`), numeric: true },
                  { label: "Sesgo", value: (b) => (b.temperature_bias_adjusted_c === null ? "—" : `${signed(Number(b.temperature_bias_adjusted_c))} °C`), numeric: true },
                  { label: "Error", value: (b) => (b.temperature_mae_adjusted_c === null ? "—" : `${number(Number(b.temperature_mae_adjusted_c), 1)} °C`), numeric: true },
                  { label: "Días", value: (b) => number(b.days_compared), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
