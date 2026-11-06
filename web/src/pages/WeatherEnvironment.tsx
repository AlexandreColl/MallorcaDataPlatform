import { useCallback, useMemo, useState } from "react";

import {
  type AirQualityNow,
  api,
  daysAgo,
  type SeaHour,
  type StationDay,
  type WarningZone,
  type WeatherSourceDay,
  type WeatherWarning,
} from "../api";
import { Async, Table } from "../components/Async";
import { Chart, SERIES } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { type MapArea, type MapLayer, PointMap } from "../components/PointMap";
import { ready, useLoad } from "../hooks";
import { dayName, dayShort, number, orDash, signed } from "../lib/format";
import { surface, TEMPERATURE_STOPS, temperatureColor } from "../lib/interpolate";
import { describe, LEVELS, overlapping, zoneLevels } from "../lib/warnings";
import type { Kpi } from "../lib/kpis";

/** Bands of the European Air Quality Index, with the EEA's own colours. */
export const EAQI = [
  { label: "Buena", color: "#50f0e6" },
  { label: "Razonable", color: "#50ccaa" },
  { label: "Regular", color: "#f0e641" },
  { label: "Mala", color: "#ff5050" },
  { label: "Muy mala", color: "#960032" },
  { label: "Extremadamente mala", color: "#7d2181" },
];

const EPISODE_TYPES: Record<string, string> = { rain: "lluvia", wind: "viento", sea: "mar" };

/** "cala_millor" -> "Cala millor": the identifiers of points and stations, readable. */
export function placeName(id: string): string {
  const text = id.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function episodeType(type: string): string {
  return type.split(" + ").map((t) => EPISODE_TYPES[t] ?? t).join(" + ");
}

function environmentKpis(weather: WeatherSourceDay[], air: AirQualityNow[], sea: SeaHour[], quakes: number): Kpi[] {
  const kpis: Kpi[] = [];
  const model = weather.filter((d) => d.source === "open_meteo" && d.temperature_mean !== null);
  const today = model.at(-1);
  if (today) {
    kpis.push({
      id: "temperature", label: "Temperatura media", value: number(today.temperature_mean as number, 1), unit: "°C",
      month: `${dayName(today.local_date)} · modelo`,
      deviation: today.temperature_max === null ? null : `Máxima ${number(today.temperature_max, 1)} °C`,
      tone: "neutral", history: model.map((d) => ({ month: d.local_date, value: d.temperature_mean as number })),
    });
  }
  const stations = air.filter((a) => a.source === "eea_air_quality");
  if (stations.length > 0) {
    const worst = Math.max(...stations.map((a) => a.eaqi_band));
    const good = stations.filter((a) => a.eaqi_band <= 2).length;
    kpis.push({
      id: "air", label: "Calidad del aire", value: EAQI[worst - 1]?.label ?? "—", unit: "",
      month: "La peor estación, en la última hora", deviation: `${good} de ${stations.length} estaciones buenas o razonables`,
      tone: worst <= 2 ? "good" : worst >= 4 ? "bad" : "neutral", history: [],
    });
  }
  const recent = sea.filter((s) => s.wave_height_m !== null && Date.parse(s.ts) > Date.now() - 86_400_000);
  if (recent.length > 0) {
    const top = recent.reduce((a, b) => ((b.wave_height_m ?? 0) > (a.wave_height_m ?? 0) ? b : a));
    kpis.push({
      id: "waves", label: "Ola más alta", value: number(top.wave_height_m as number, 1), unit: "m",
      month: "Últimas 24 horas", deviation: `En ${placeName(top.point)}`, tone: "neutral", history: [],
    });
  }
  kpis.push({
    id: "quakes", label: "Sismos", value: number(quakes), unit: "", month: "Último año, IGN",
    deviation: null, tone: "neutral", history: [],
  });
  return kpis;
}

function DailyTemperature({ days }: { days: WeatherSourceDay[] }) {
  const option = useCallback(() => {
    const dates = [...new Set(days.map((d) => d.local_date))].sort();
    const sources = [...new Set(days.map((d) => d.source))];
    return {
      xAxis: { type: "category", data: dates.map(dayShort) },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: "{value} °C" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} °C`) },
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
      xAxis: { type: "time", axisLabel: { formatter: (v: number) => dayShort(new Date(v).toISOString()) } },
      yAxis: { type: "value", axisLabel: { formatter: "{value} m" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 2)} m`) },
      legend: { type: "scroll", top: 0, left: 0, right: 0 },
      series: points.map((point, i) => ({
        name: placeName(point), type: "line", symbol: "none", color: SERIES[i % SERIES.length],
        data: hours.filter((h) => h.point === point).map((h) => [h.ts, h.wave_height_m]),
      })),
    };
  }, [hours]);
  return <Chart option={option} label="Altura de ola en cada punto de la costa" height={300} />;
}

const TEMPERATURE_FIELDS = {
  temperature_mean: "Media",
  temperature_max: "Máxima",
  temperature_min: "Mínima",
} as const;

type TemperatureField = keyof typeof TEMPERATURE_FIELDS;

/**
 * The temperature of the AEMET stations spread over the island: each cell takes the inverse-distance mean of the
 * stations, so the colours show the warm south and the cool Tramuntana between the points that were measured.
 */
function TemperatureZones({ stations }: { stations: StationDay[] }) {
  const [field, setField] = useState<TemperatureField>("temperature_max");
  const { samples, areas, layers, min, max } = useMemo(() => {
    const samples = stations
      .filter((s) => s[field] !== null)
      .map((s) => ({ lon: s.lon, lat: s.lat, value: s[field] as number, entity: s.entity }));
    const values = samples.map((s) => s.value);
    const [min, max] = [Math.floor(Math.min(...values)), Math.ceil(Math.max(...values))];
    const areas: MapArea[] = surface(samples, 0.012).map((c) => ({ polygon: c.polygon, color: temperatureColor(c.value, min, max) }));
    const layers: MapLayer[] = [
      {
        id: "stations", label: "Estaciones", color: "#0a120d", radius: 4.5,
        points: samples.map((s) => ({
          lat: s.lat, lon: s.lon, color: temperatureColor(s.value, min, max),
          popup: [s.entity, `${TEMPERATURE_FIELDS[field]}: ${number(s.value, 1)} °C`],
        })),
      },
    ];
    return { samples, areas, layers, min, max };
  }, [stations, field]);

  if (samples.length === 0) return <p className="empty">Sin temperaturas para ese día.</p>;
  return (
    <>
      <div className="segmented" role="group" aria-label="Temperatura">
        {(Object.keys(TEMPERATURE_FIELDS) as TemperatureField[]).map((f) => (
          <button key={f} type="button" aria-pressed={f === field} onClick={() => setField(f)}>
            {TEMPERATURE_FIELDS[f]}
          </button>
        ))}
      </div>
      <PointMap layers={layers} areas={areas} height={480} />
      <div className="gradient-scale">
        <span>{number(min)} °C</span>
        <span className="gradient-bar" style={{ background: `linear-gradient(90deg, ${TEMPERATURE_STOPS.join(", ")})` }} />
        <span>{number(max)} °C</span>
      </div>
    </>
  );
}

function airLayers(air: AirQualityNow[]): MapLayer[] {
  const point = (a: AirQualityNow) => ({
    lat: a.lat as number, lon: a.lon as number, color: EAQI[a.eaqi_band - 1]?.color,
    popup: [placeName(a.entity), EAQI[a.eaqi_band - 1]?.label ?? "", `NO₂ ${a.no2 ?? "—"} · O₃ ${a.o3 ?? "—"} · PM10 ${a.pm10 ?? "—"} µg/m³`],
  });
  const located = air.filter((a) => a.lat !== null && a.lon !== null);
  return [
    { id: "stations", label: "Estaciones", color: "#15803d", radius: 8, points: located.filter((a) => a.source === "eea_air_quality").map(point) },
    { id: "model", label: "Modelo CAMS", color: "#d97706", radius: 5, points: located.filter((a) => a.source !== "eea_air_quality").map(point) },
  ];
}

/** An instant in Mallorca's local time: "5 nov 14:00". */
function when(iso: string): string {
  const local = new Date(iso).toLocaleString("sv-SE", { timeZone: "Europe/Madrid" }); // "2026-11-05 14:00:00"
  return `${dayShort(local)} ${local.slice(11, 16)}`;
}

const WARNING_PERIODS = {
  now: { label: "Ahora", hours: 1 },
  next: { label: "Próximas 72 h", hours: 72 },
} as const;

type WarningPeriod = keyof typeof WARNING_PERIODS;

/**
 * The AEMET warning zones of Mallorca coloured by their highest level in the period, with the warnings listed by
 * zone in the popup of each one.
 */
function WarningsMap({ zones, warnings }: { zones: WarningZone[]; warnings: WeatherWarning[] }) {
  const [period, setPeriod] = useState<WarningPeriod>("next");
  const { areas, layers, active } = useMemo(() => {
    const now = new Date();
    const active = overlapping(warnings, now, new Date(now.getTime() + WARNING_PERIODS[period].hours * 3_600_000));
    const levels = zoneLevels(active);
    // Coastal waters first, so the land zones are drawn over them.
    const ordered = [...zones].sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "coast" ? -1 : 1));
    const areas: MapArea[] = ordered.map((z) => ({ polygon: z.polygon, color: LEVELS[levels.get(z.zone) ?? 0]?.color ?? "#4ade80" }));
    const layers: MapLayer[] = [
      {
        id: "zones", label: "Zonas", color: "#0a120d", radius: 4,
        points: zones.filter((z) => z.kind === "land").map((z) => {
          // A land zone and its coastal waters (same code with a C) share the popup.
          const own = active.filter((w) => w.zone === z.zone || w.zone === `${z.zone}C`);
          const [lon, lat] = z.polygon.reduce(
            ([x, y], [px, py]) => [x + px / z.polygon.length, y + py / z.polygon.length],
            [0, 0],
          );
          const lines = own.map((w) => `${describe(w)}${w.zone_kind === "coast" ? " (costa)" : ""} · ${when(w.start_ts)}`);
          return {
            lat, lon, color: LEVELS[levels.get(z.zone) ?? 0]?.color,
            popup: [z.name, ...(lines.length ? lines : ["Sin avisos"])],
          };
        }),
      },
    ];
    return { areas, layers, active };
  }, [zones, warnings, period]);

  return (
    <>
      <div className="segmented" role="group" aria-label="Periodo">
        {(Object.keys(WARNING_PERIODS) as WarningPeriod[]).map((p) => (
          <button key={p} type="button" aria-pressed={p === period} onClick={() => setPeriod(p)}>
            {WARNING_PERIODS[p].label}
          </button>
        ))}
      </div>
      <PointMap layers={layers} areas={areas} height={420} />
      <div className="scale">
        {LEVELS.map((l) => (
          <span key={l.label}>
            <span className="dot" style={{ background: l.color }} /> {l.label}
          </span>
        ))}
        <span>{active.length === 0 ? "Ningún aviso en el periodo" : `${active.length} avisos en el periodo`}</span>
      </div>
    </>
  );
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
  const stations = useLoad(() => api.stations("aemet"));
  const warnings = useLoad(api.warnings);
  const zones = useLoad(api.warningZones);
  const stationDay = stations.status === "ready" && stations.data[0] ? ` (${dayName(stations.data[0].local_date)})` : "";

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
                  { label: "Desde", value: (w) => when(w.start_ts) },
                  { label: "Hasta", value: (w) => when(w.end_ts) },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title="Temperatura por zonas"
          subtitle={`Último día publicado por las ${stations.status === "ready" ? stations.data.length : 33} estaciones oficiales de AEMET${stationDay}, interpolado entre ellas.`}
          wide
        >
          <Async state={stations} height={480}>{(rows) => <TemperatureZones stations={rows} />}</Async>
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
                        {placeName(a.entity)}
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
        <Panel title="Modelo frente a estaciones" subtitle="Error del modelo en la temperatura media diaria de cada estación de AEMET y SOCIB.">
          <Async state={bias}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                columns={[
                  { label: "Estación", value: (b) => b.station },
                  { label: "Sesgo", value: (b) => (b.temperature_bias_c === null ? "—" : `${signed(Number(b.temperature_bias_c))} °C`), numeric: true },
                  { label: "Error", value: (b) => (b.temperature_mae_c === null ? "—" : `${number(Number(b.temperature_mae_c), 1)} °C`), numeric: true },
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
