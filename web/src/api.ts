// Calls of the REST API. The front end reads only the API, never the warehouse. Its types are generated from the
// OpenAPI schema (api.gen.ts, `make web-types`), so a change in api/schemas.py shows up in the type check.

import type {
  AirQualityNow,
  AnomaliesDay,
  BathingWaterSeason,
  BathingWaterYear,
  BikesHour,
  BikeStation,
  Aquifer,
  ClimateMonth,
  Correction,
  DetectorBenchmark,
  DustEpisode,
  DustPm10Station,
  Earthquake,
  Health,
  HumanPressureDay,
  Location,
  MobilityDay,
  ModelBias,
  Municipality,
  PollenDustDay,
  PopulationYear,
  QualityRule,
  ResourcesMonth,
  SeaHour,
  SeaTemperatureMonth,
  Series,
  SeriesDay,
  Source,
  StationDay,
  StopService,
  TourismMonth,
  TouristDwellings,
  MunicipalUnemployment,
  UnemploymentSeasonality,
  TransitRoute,
  WarningZone,
  WaterReservesMonth,
  WaveModelBias,
  WeatherEpisode,
  WeatherSourceDay,
  WeatherWarning,
} from "./api.gen";
import { locale } from "./i18n";

export type * from "./api.gen";

interface Page<T> {
  items: T[];
}

const BASE = "/api/v1";

/** Every request says the language of the page: the API answers the catalogue's labels and licences in it. */
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { headers: { "Accept-Language": locale() } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

const answers = new Map<string, Promise<unknown>>();

/**
 * The answer to `path`, asked for once per page load: a past day does not change, so playing the days again or
 * going back to one is instant. A failed request is forgotten, so the next attempt asks again.
 */
function remembered<T>(path: string, load: (path: string) => Promise<T>): Promise<T> {
  let answer = answers.get(path) as Promise<T> | undefined;
  if (!answer) {
    answer = load(path);
    answers.set(path, answer);
    answer.catch(() => answers.delete(path));
  }
  return answer;
}

/** An ISO day `days` before today, for the `from` and `start` parameters. */
export function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export const api = {
  health: () => get<Health>("/health"),
  sources: () => get<Source[]>("/sources"),
  locations: () => get<Location[]>("/locations"),
  resources: (from: string) => get<ResourcesMonth[]>(`/resources/monthly?from=${from}`),
  tourism: (from: string) => get<TourismMonth[]>(`/tourism/monthly?from=${from}`),
  climate: (from: string) => get<ClimateMonth[]>(`/climate/monthly?from=${from}`),
  seaTemperature: (from: string) => get<SeaTemperatureMonth[]>(`/sea/temperature/monthly?from=${from}`),
  water: (from: string) => get<WaterReservesMonth[]>(`/water/reserves?from=${from}`),
  aquifers: () => get<Aquifer[]>("/water/aquifers"),
  bathingWaters: () => get<BathingWaterSeason[]>("/water/bathing"),
  bathingWaterYears: () => get<BathingWaterYear[]>("/water/bathing/island"),
  mobilityDaily: (from: string) => get<MobilityDay[]>(`/mobility/daily?from=${from}`),
  stops: () => get<StopService[]>("/mobility/stops"),
  routes: () => get<TransitRoute[]>("/mobility/routes"),
  bikeStations: () => get<BikeStation[]>("/mobility/bike-stations"),
  bikesHourly: (from: string) => get<BikesHour[]>(`/mobility/bikes/hourly?from=${from}`),
  series: (source: string) => get<Series[]>(`/series?source=${encodeURIComponent(source)}`),
  seriesDaily: (series: Pick<Series, "source" | "entity" | "metric">, from: string) =>
    get<SeriesDay[]>(
      `/series/daily?${new URLSearchParams({ source: series.source, entity: series.entity, metric: series.metric, from })}`,
    ),
  weatherDaily: (from: string) => get<WeatherSourceDay[]>(`/weather/daily?from=${from}`),
  stations: (source: "aemet" | "socib" | "open_meteo", day?: string | null) =>
    remembered(`/weather/stations?source=${source}${day ? `&date=${day}` : ""}`, get<StationDay[]>),
  warnings: () => get<WeatherWarning[]>("/warnings"),
  warningZones: () => get<WarningZone[]>("/warnings/zones"),
  population: (from: number) => get<PopulationYear[]>(`/population?from=${from}`),
  touristDwellings: () => get<TouristDwellings[]>("/tourism/dwellings"),
  municipalUnemployment: () => get<MunicipalUnemployment[]>("/unemployment/municipalities"),
  unemploymentSeasonality: () => get<UnemploymentSeasonality[]>("/unemployment/seasonality?area=mallorca"),
  humanPressure: (from: string) => get<HumanPressureDay[]>(`/population/pressure?from=${from}`),
  municipalities: () => get<Municipality[]>("/municipalities"),
  episodes: (from: string) => get<WeatherEpisode[]>(`/weather/episodes?from=${from}`),
  modelBias: () => get<ModelBias[]>("/weather/model-bias"),
  airQuality: () => get<AirQualityNow[]>("/air-quality/latest"),
  pollenDust: (from: string) => get<PollenDustDay[]>(`/air-quality/pollen-dust?from=${from}`),
  dustEpisodes: (from: string) => get<DustEpisode[]>(`/air-quality/dust-episodes?from=${from}`),
  dustPm10: () => get<DustPm10Station[]>("/air-quality/dust-pm10"),
  sea: (start: string) => get<SeaHour[]>(`/sea/hourly?start=${start}T00:00:00Z`),
  seaModelBias: () => get<WaveModelBias[]>("/sea/model-bias"),
  earthquakes: () => get<Earthquake[]>("/earthquakes"),
  qualityRules: () => get<QualityRule[]>("/quality/rules"),
  anomaliesDaily: (start: string) => get<AnomaliesDay[]>(`/anomalies/daily?start=${start}T00:00:00Z`),
  detectorBenchmark: () => get<DetectorBenchmark[]>("/anomalies/benchmark"),
  corrections: (start: string) =>
    get<Page<Correction>>(`/corrections?start=${start}T00:00:00Z&limit=8`).then((page) => page.items),
};
