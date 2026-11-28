import { useCallback, useMemo, useState } from "react";

import { api, daysAgo, type PollenDustDay, type SeaHour, type WeatherSourceDay } from "../api";
import { Async, Table } from "../components/Async";
import { Chart, SERIES } from "../components/Chart";
import { KpiRow } from "../components/KpiCard";
import { Panel } from "../components/Layout";
import { PointMap } from "../components/PointMap";
import { TemperatureZones } from "../components/TemperatureZones";
import { WarningsMap } from "../components/WarningsMap";
import { ready, useLoad } from "../hooks";
import { messages } from "../i18n";
import {
  airLayers,
  DUST_EPISODE_UGM3,
  eaqiBand,
  eaqiBands,
  environmentKpis,
  episodeType,
  islandDays,
  localTime,
  POLLEN_MODERATE,
  temperatureSubtitle,
} from "../lib/environment";
import { dayShort, number, orDash, placeName, signed } from "../lib/format";
import { describe, levels } from "../lib/warnings";

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
  return <Chart option={option} label={messages().weather.dailyTemperatureChart} height={300} />;
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
  return <Chart option={option} label={messages().weather.wavesChart} height={300} />;
}

/** A dashed horizontal line at a threshold, labelled with its value. */
function threshold(value: number, color: string) {
  return {
    symbol: "none", silent: true, data: [{ yAxis: value }],
    // The label sits above the line inside the plot: at its end it would be cut by the edge of the panel.
    lineStyle: { type: "dashed", color }, label: { formatter: String(value), color, position: "insideEndTop" },
  };
}

function PollenSeason({ days }: { days: PollenDustDay[] }) {
  const option = useCallback(() => {
    const island = islandDays(days);
    const m = messages().weather;
    const [olive = "#000", grass = "#000"] = [SERIES[2], SERIES[0]];
    return {
      xAxis: { type: "category", data: island.map((d) => dayShort(d.date)) },
      yAxis: { type: "value" }, // grains/m³, as the subtitle says: the unit has a name in each language
      tooltip: { valueFormatter: orDash((v) => number(v, 1)) },
      series: [
        { name: m.olive, type: "line", symbol: "none", color: olive, data: island.map((d) => d.olive), markLine: threshold(POLLEN_MODERATE.olive, olive) },
        { name: m.grass, type: "line", symbol: "none", color: grass, data: island.map((d) => d.grass), markLine: threshold(POLLEN_MODERATE.grass, grass) },
      ],
    };
  }, [days]);
  return <Chart option={option} label={messages().weather.pollenChart} height={300} />;
}

function SaharanDust({ days }: { days: PollenDustDay[] }) {
  const option = useCallback(() => {
    const island = islandDays(days);
    const color = SERIES[2] ?? "#000";
    return {
      xAxis: { type: "category", data: island.map((d) => dayShort(d.date)) },
      yAxis: { type: "value", axisLabel: { formatter: "{value} µg/m³" } },
      tooltip: { valueFormatter: orDash((v) => `${number(v, 1)} µg/m³`) },
      series: [
        {
          name: messages().weather.dust, type: "bar", color, barCategoryGap: "10%",
          data: island.map((d) => d.dust), markLine: threshold(DUST_EPISODE_UGM3, "#dc2626"),
        },
      ],
    };
  }, [days]);
  return <Chart option={option} label={messages().weather.dustChart} height={300} />;
}

/** "2026-03-10" -> "10 mar 2026": dust episodes span several years. */
const dayAndYear = (isoDay: string) => `${dayShort(isoDay)} ${isoDay.slice(0, 4)}`;
/** A concentration in µg/m³ without decimals, or a dash. */
const ugm3 = orDash((value) => number(value, 0));

/** A wave height in metres with two decimals, or a dash. */
const metres = orDash((value) => number(value, 2));

export function WeatherEnvironment() {
  const weather = useLoad(() => api.weatherDaily(daysAgo(30)));
  const air = useLoad(api.airQuality);
  const sea = useLoad(() => api.sea(daysAgo(7)));
  const episodes = useLoad(() => api.episodes(daysAgo(365)));
  const quakes = useLoad(api.earthquakes);
  const pollenDust = useLoad(() => api.pollenDust(daysAgo(365)));
  const dustEpisodes = useLoad(() => api.dustEpisodes(daysAgo(3 * 365)));
  const dustStations = useLoad(api.dustPm10);
  const bias = useLoad(api.modelBias);
  const waveBias = useLoad(api.seaModelBias);

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
  const m = messages().weather;
  const coast = ` (${messages().warnings.coast})`;

  return (
    <>
      <KpiRow kpis={kpis} colors={["#dc2626", "#0891b2", "#2563eb", "#7c3aed"]} />
      <div className="grid">
        <Panel title={m.warningsTitle} subtitle={m.warningsSubtitle} wide>
          <Async state={zones} height={420}>
            {(z) => <Async state={warnings} height={420}>{(w) => <WarningsMap zones={z} warnings={w} />}</Async>}
          </Async>
        </Panel>
        <Panel title={m.warningsListTitle} subtitle={m.warningsListSubtitle}>
          <Async state={warnings}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 12)}
                empty={m.noWarnings}
                columns={[
                  {
                    label: m.warning,
                    value: (w) => (
                      <span className="source-cell">
                        <span className="dot" style={{ background: levels()[w.level]?.color }} />
                        <span className="stacked">
                          {describe(w)}
                          <small>{w.zone_name ?? w.zone}{w.zone_kind === "coast" ? coast : ""}</small>
                        </span>
                      </span>
                    ),
                  },
                  { label: m.from, value: (w) => localTime(w.start_ts) },
                  { label: m.to, value: (w) => localTime(w.end_ts) },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title={m.zonesTitle}
          subtitle={temperatureSubtitle(ready(stations), day)}
          wide
        >
          <Async state={stations} height={480}>
            {(rows) => <Async state={places} height={480}>{(p) => <TemperatureZones stations={rows} places={p} days={aemetDays} onDay={setDay} />}</Async>}
          </Async>
        </Panel>
        <Panel title={m.last30Title} subtitle={m.last30Subtitle}>
          <Async state={weather} height={300}>{(rows) => <DailyTemperature days={rows} />}</Async>
        </Panel>
        <Panel title={m.airTitle} subtitle={m.airSubtitle} wide>
          <Async state={air} height={480}>
            {() => (
              <>
                <PointMap layers={layers} height={480} />
                <div className="scale">
                  {eaqiBands().slice(0, 4).map((b) => (
                    <span key={b.label}>
                      <span className="dot" style={{ background: b.color }} /> {b.label}
                    </span>
                  ))}
                </div>
              </>
            )}
          </Async>
        </Panel>
        <Panel title={m.airStationsTitle} subtitle={m.airStationsSubtitle}>
          <Async state={air}>
            {(rows) => (
              <Table
                rows={rows.filter((a) => a.source === "eea_air_quality").sort((a, b) => b.eaqi_band - a.eaqi_band)}
                columns={[
                  {
                    label: m.station,
                    value: (a) => (
                      <span className="source-cell">
                        <span className="dot" style={{ background: eaqiBand(a.eaqi_band)?.color }} />
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
        <Panel title={m.pollenTitle} subtitle={m.pollenSubtitle} wide>
          <Async state={pollenDust} height={300}>{(rows) => <PollenSeason days={rows} />}</Async>
        </Panel>
        <Panel title={m.dustEpisodesTitle} subtitle={m.dustEpisodesSubtitle}>
          <Async state={dustEpisodes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                empty={m.noDustEpisodes}
                columns={[
                  { label: m.start, value: (e) => dayAndYear(e.start_date) },
                  { label: m.days, value: (e) => number(e.days), numeric: true },
                  { label: m.dust, value: (e) => ugm3(e.peak_dust_ugm3), numeric: true },
                  { label: m.pm10Excess, value: (e) => (e.pm10_excess_ugm3 === null ? "—" : signed(e.pm10_excess_ugm3, 0)), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.dustTitle} subtitle={m.dustSubtitle} wide>
          <Async state={pollenDust} height={300}>{(rows) => <SaharanDust days={rows} />}</Async>
        </Panel>
        <Panel title={m.dustStationsTitle} subtitle={m.dustStationsSubtitle}>
          <Async state={dustStations}>
            {(rows) => (
              <Table
                rows={rows}
                columns={[
                  { label: m.station, value: (d) => placeName(d.station, d.name) },
                  { label: m.withWithout, value: (d) => `${ugm3(d.pm10_dust_days_ugm3)} / ${ugm3(d.pm10_other_days_ugm3)}`, numeric: true },
                  { label: m.camsBias, value: (d) => (d.model_bias_dust_days_ugm3 === null ? "—" : signed(d.model_bias_dust_days_ugm3, 0)), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.wavesTitle} subtitle={m.wavesSubtitle} wide>
          <Async state={sea} height={300}>{(rows) => <Waves hours={rows} />}</Async>
        </Panel>
        <Panel title={m.episodesTitle} subtitle={m.episodesSubtitle}>
          <Async state={episodes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                empty={m.noEpisodes}
                columns={[
                  { label: m.start, value: (e) => dayShort(e.start_date) },
                  { label: m.type, value: (e) => episodeType(e.episode_type) },
                  { label: m.rain, value: (e) => (e.peak_rain_mm === null ? "—" : `${number(e.peak_rain_mm, 0)} mm`), numeric: true },
                  { label: m.gust, value: (e) => (e.peak_gust_kmh === null ? "—" : `${number(e.peak_gust_kmh, 0)} km/h`), numeric: true },
                  { label: m.wave, value: (e) => (e.peak_wave_m === null ? "—" : `${number(e.peak_wave_m, 1)} m`), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel title={m.quakesTitle} subtitle={m.quakesSubtitle}>
          <Async state={quakes}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                empty={m.noQuakes}
                columns={[
                  { label: m.date, value: (e) => dayShort(e.ts) },
                  { label: m.magnitude, value: (e) => (e.magnitude === null ? "—" : number(e.magnitude, 1)), numeric: true },
                  { label: m.depth, value: (e) => (e.depth_km === null ? "—" : `${number(e.depth_km, 0)} km`), numeric: true },
                  { label: m.toPalma, value: (e) => (e.distance_to_palma_km === null ? "—" : `${number(e.distance_to_palma_km, 0)} km`), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title={m.modelTitle}
          subtitle={m.modelSubtitle}
        >
          <Async state={bias}>
            {(rows) => (
              <Table
                rows={rows.slice(0, 8)}
                columns={[
                  { label: m.station, value: (b) => b.station_name ?? b.station },
                  { label: m.heightDifference, value: (b) => (b.elevation_diff_m === null ? "—" : `${signed(Number(b.elevation_diff_m), 0)} m`), numeric: true },
                  { label: m.bias, value: (b) => (b.temperature_bias_adjusted_c === null ? "—" : `${signed(Number(b.temperature_bias_adjusted_c))} °C`), numeric: true },
                  { label: m.error, value: (b) => (b.temperature_mae_adjusted_c === null ? "—" : `${number(Number(b.temperature_mae_adjusted_c), 1)} °C`), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
        <Panel
          title={m.buoysTitle}
          subtitle={m.buoysSubtitle}
        >
          <Async state={waveBias}>
            {(rows) => (
              <Table
                rows={rows}
                empty={m.noBuoyHours}
                columns={[
                  { label: m.buoy, value: (b) => placeName(b.buoy, b.buoy_name) },
                  {
                    label: m.buoyModelMean,
                    value: (b) => `${metres(b.wave_height_buoy_mean_m)} / ${metres(b.wave_height_model_mean_m)}`,
                    numeric: true,
                  },
                  { label: m.bias, value: (b) => (b.wave_height_bias_m === null ? "—" : signed(Number(b.wave_height_bias_m), 2)), numeric: true },
                  { label: "r", value: (b) => (b.wave_height_correlation === null ? "—" : number(Number(b.wave_height_correlation), 2)), numeric: true },
                ]}
              />
            )}
          </Async>
        </Panel>
      </div>
    </>
  );
}
