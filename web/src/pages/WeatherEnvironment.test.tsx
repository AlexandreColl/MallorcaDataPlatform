// @vitest-environment happy-dom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { WeatherEnvironment } from "./WeatherEnvironment";

// ECharts and MapLibre need a canvas and WebGL: the page is checked without them, and the temperature map (canvas
// pixels) is covered by the tests of lib/interpolate and lib/contours.
vi.mock("../components/Chart", () => ({ Chart: ({ label }: { label: string }) => <figure aria-label={label} />, SERIES: ["#000"] }));
vi.mock("../components/PointMap", () => ({ PointMap: () => <div role="img" aria-label="mapa" /> }));
vi.mock("../components/TemperatureZones", () => ({ TemperatureZones: () => <div role="img" aria-label="temperatura por zonas" /> }));

const answers = {
  weatherDaily: [{ source: "open_meteo", source_label: "Open-Meteo", local_date: "2026-11-11", temperature_mean: 18.4, temperature_max: 22 }],
  airQuality: [
    { source: "eea_air_quality", entity: "bellver", name: "Bellver", lat: 39.56, lon: 2.62, eaqi_band: 2, no2: 11, o3: 60, pm10: 14 },
    { source: "eea_air_quality", entity: "foners", name: "Foners", lat: 39.57, lon: 2.66, eaqi_band: 4, no2: 48, o3: 20, pm10: 35 },
  ],
  sea: [],
  episodes: [],
  earthquakes: [{ ts: new Date().toISOString(), magnitude: 2.1, depth_km: 8, distance_to_palma_km: 40 }],
  modelBias: [{ station: "B228", station_name: "Palma, Puerto", elevation_diff_m: -12, temperature_bias_c: 0.8, temperature_bias_adjusted_c: 0.7, temperature_mae_adjusted_c: 1.1, days_compared: 30 }],
  stations: [],
  municipalities: [],
  warnings: [],
  warningZones: [],
};

beforeEach(() => {
  for (const [name, rows] of Object.entries(answers)) vi.spyOn(api, name as keyof typeof api).mockResolvedValue(rows as never);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const panel = async (title: string) => (await screen.findByRole("heading", { name: title })).closest("section") as HTMLElement;

describe("WeatherEnvironment", () => {
  it("shows the key figures of the model, the air and the earthquakes", async () => {
    render(<WeatherEnvironment />);

    expect(await screen.findByText("18,4")).toBeTruthy();
    expect(screen.getByText("1 de 2 estaciones buenas o razonables")).toBeTruthy();
    expect(screen.getByText("Último año, IGN")).toBeTruthy();
  });

  it("lists the air stations from the worst to the best", async () => {
    render(<WeatherEnvironment />);

    const rows = within(await panel("Estaciones de calidad del aire")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual(["Foners", "Bellver"]);
  });

  it("says when there is nothing to list", async () => {
    render(<WeatherEnvironment />);

    expect(within(await panel("Avisos en vigor y anunciados")).getByText("Ningún aviso en los próximos 3 días")).toBeTruthy();
    expect(within(await panel("Episodios del último año")).getByText("Ningún episodio en el último año")).toBeTruthy();
  });

  it("shows an error in the panel whose request failed, and the rest of the page", async () => {
    vi.spyOn(api, "modelBias").mockRejectedValue(new Error("503 Service Unavailable"));
    render(<WeatherEnvironment />);

    expect(within(await panel("Modelo frente a estaciones")).getByText(/No se pudieron cargar los datos/)).toBeTruthy();
    expect(await screen.findByText("Foners")).toBeTruthy();
  });
});
