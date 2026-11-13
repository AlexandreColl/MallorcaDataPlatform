import { describe, expect, it } from "vitest";

import type { AirQualityNow, SeaHour, StationDay, WeatherSourceDay } from "../api";
import { airLayers, environmentKpis, episodeType, localTime, temperatureSubtitle } from "./environment";

const day = (fields: Partial<WeatherSourceDay>) => ({ source: "open_meteo", temperature_max: null, ...fields }) as WeatherSourceDay;
const air = (fields: Partial<AirQualityNow>) =>
  ({ source: "eea_air_quality", entity: "bellver", name: null, lat: 39.56, lon: 2.62, no2: 10, o3: 50, pm10: 12, ...fields }) as AirQualityNow;

describe("environmentKpis", () => {
  it("takes the latest model day, the worst air station and the earthquakes of the year", () => {
    const weather = [
      day({ local_date: "2026-11-10", temperature_mean: 17.2 }),
      day({ local_date: "2026-11-11", temperature_mean: 18.46, temperature_max: 22.1 }),
      day({ source: "aemet", local_date: "2026-11-11", temperature_mean: 30 }), // stations are not the island's figure
    ];
    const stations = [air({ eaqi_band: 1 }), air({ eaqi_band: 3 }), air({ source: "open_meteo", eaqi_band: 6 })];

    const [temperature, quality, quakes] = environmentKpis(weather, stations, [], 4);

    expect(temperature).toMatchObject({ value: "18,5", month: "11 de noviembre de 2026 · modelo", deviation: "Máxima 22,1 °C" });
    expect(temperature?.history).toHaveLength(2);
    expect(quality).toMatchObject({ value: "Regular", deviation: "1 de 2 estaciones buenas o razonables", tone: "neutral" });
    expect(quakes).toMatchObject({ id: "quakes", value: "4" });
  });

  it("shows the highest wave of the last 24 hours only", () => {
    const hour = (hoursAgo: number, wave: number, point: string) =>
      ({ ts: new Date(Date.now() - hoursAgo * 3_600_000).toISOString(), wave_height_m: wave, point }) as SeaHour;
    const sea = [hour(30, 4.2, "dragonera"), hour(2, 1.4, "cala_millor"), hour(1, 0.8, "palma")];

    const waves = environmentKpis([], [], sea, 0).find((k) => k.id === "waves");

    expect(waves).toMatchObject({ value: "1,4", deviation: "En Cala millor" });
  });
});

describe("airLayers", () => {
  it("splits the stations from the model points and leaves out the unlocated ones", () => {
    const [stations, model] = airLayers([air({ eaqi_band: 4 }), air({ lat: null }), air({ source: "open_meteo", eaqi_band: 2 })]);

    expect(stations?.points).toHaveLength(1);
    expect(stations?.points[0]).toMatchObject({ color: "#ff5050", popup: ["Bellver", "Mala", "NO₂ 10 · O₃ 50 · PM10 12 µg/m³"] });
    expect(model?.points).toHaveLength(1);
  });
});

describe("texts", () => {
  it("writes an instant in Mallorca's time", () => {
    expect(localTime("2026-11-05T13:00:00Z")).toBe("5 nov 14:00"); // UTC+1 in winter
    expect(localTime("2026-07-05T13:00:00Z")).toBe("5 jul 15:00"); // UTC+2 in summer
  });

  it("names the kinds of an episode", () => {
    expect(episodeType("rain + wind")).toBe("lluvia + viento");
    expect(episodeType("heat")).toBe("heat");
  });

  it("says which day the temperature map shows", () => {
    const stations = [{ local_date: "2026-11-03" }, { local_date: "2026-11-03" }] as StationDay[];

    expect(temperatureSubtitle(null, null)).toMatch(/^Las 33 estaciones oficiales de AEMET, interpoladas/);
    expect(temperatureSubtitle(stations, null)).toMatch(/^Las 2 estaciones .* el 3 de noviembre de 2026 \(último día publicado\)/);
    expect(temperatureSubtitle(stations, "2026-11-03")).not.toMatch(/último día publicado/);
  });
});
