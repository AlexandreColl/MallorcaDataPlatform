// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { Mobility } from "./Mobility";

// ECharts and MapLibre need a canvas and WebGL: the charts and maps are stand-ins named after what they show.
vi.mock("../components/Chart", () => ({ Chart: ({ label }: { label: string }) => <figure aria-label={label} />, SERIES: ["#000"] }));
vi.mock("../components/PointMap", () => ({ PointMap: () => <div role="img" aria-label="mapa" /> }));

const square = (lon: number, lat: number) => [[[lon - 0.05, lat - 0.05], [lon + 0.05, lat - 0.05], [lon + 0.05, lat + 0.05], [lon - 0.05, lat + 0.05]]];

const answers = {
  mobilityDaily: [
    { network: "emt_palma", local_date: "2026-11-11", is_weekend: false, stops: 900, stops_with_service: 850, scheduled_stop_calls: 52_000 },
  ],
  stops: [
    { network: "emt_palma", stop: "stop_1", name: "Plaça d'Espanya", lat: 39.576, lon: 2.655, local_date: "2026-11-11", departures: 1400, lines: 18 },
    { network: "ctm", stop: "stop_9", name: "Inca (estació)", lat: 39.72, lon: 2.91, local_date: "2026-11-11", departures: 210, lines: 6 },
  ],
  population: [
    { municipality: "07040", year: 2016, population: 402_000, density_per_km2: 1910 },
    { municipality: "07040", year: 2026, population: 440_000, density_per_km2: 2090 },
    { municipality: "07027", year: 2016, population: 31_000, density_per_km2: 530 },
    { municipality: "07027", year: 2026, population: 34_100, density_per_km2: 583 },
  ],
  municipalities: [
    { municipality: "07040", name: "Palma", polygon: square(2.65, 39.57) },
    { municipality: "07027", name: "Inca", polygon: square(2.91, 39.72) },
  ],
  touristDwellings: [
    { municipality: "07040", reference_month: "2025-11-01", tourist_dwellings: 1100, dwellings_per_1000_inhabitants: 2.5 },
    { municipality: "07040", reference_month: "2026-05-01", tourist_dwellings: 1023, dwellings_per_1000_inhabitants: 2.3 },
  ],
  municipalUnemployment: [
    { municipality: "07040", month: "2026-09-01", is_suppressed: false, unemployed: 12900, unemployed_per_1000_inhabitants: 29.3 },
    { municipality: "07040", month: "2026-10-01", is_suppressed: false, unemployed: 13407, unemployed_per_1000_inhabitants: 30.8 },
    { municipality: "07027", month: "2026-10-01", is_suppressed: true, unemployed: null, unemployed_per_1000_inhabitants: null },
  ],
  humanPressure: [],
  bikeStations: [
    { station: "station_1", name: "01 PARC DE SES VELES", lat: 39.566, lon: 2.659, local_date: "2026-11-26", hours_observed: 24, bikes_available: 9.75, bikes_available_min: 4, bikes_available_max: 14, ebikes_available: 1.2, docks_available: 10.25, occupancy_pct: 48.8, working_docks: 20, hours_empty: 0, hours_full: 1, largest_hourly_swing: 5 },
    { station: "station_2", name: "45 JAUME III", lat: 39.572, lon: 2.643, local_date: "2026-11-26", hours_observed: 24, bikes_available: 0.4, bikes_available_min: 0, bikes_available_max: 2, ebikes_available: 0, docks_available: 17.6, occupancy_pct: 2.2, working_docks: 18, hours_empty: 15, hours_full: 0, largest_hourly_swing: 2 },
  ],
  bikesHourly: [
    { ts: "2026-11-26T16:00:00Z", local_date: "2026-11-26", local_hour: 17, stations: 106, bikes_available: 562, ebikes_available: 120, docks_available: 1100, occupancy_pct: 33.8, stations_empty: 9, stations_full: 2 },
  ],
  routes: [{ network: "ctm", route: "route_1", short_name: "T1", name: "T1 · Palma - Inca", kind: "train", color: null, local_date: "2026-11-11", trips: 64, geometry: { type: "MultiLineString", coordinates: [] } }],
};

beforeEach(() => {
  // Spied as plain functions: the union of every method of `api` is too large for TypeScript (TS2590).
  const calls = api as unknown as Record<string, () => Promise<unknown>>;
  for (const [name, rows] of Object.entries(answers)) vi.spyOn(calls, name).mockResolvedValue(rows);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const panel = async (title: string) => (await screen.findByRole("heading", { name: title })).closest("section") as HTMLElement;
const firstCells = (section: HTMLElement) =>
  within(section).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]?.textContent);

describe("Mobility", () => {
  it("shows the population of the island and the service per inhabitant", async () => {
    render(<Mobility />);

    expect(await screen.findByText("474.100")).toBeTruthy(); // Palma and Inca on 1 January 2026
    expect(screen.getByText("Pasos por 1.000 habitantes")).toBeTruthy();
    expect(screen.getByText("850 de 900 paradas con servicio")).toBeTruthy();
  });

  it("lists the municipalities, the stops and the lines", async () => {
    render(<Mobility />);

    expect(firstCells(await panel("Municipios más poblados"))).toEqual(["Palma", "Inca"]);
    expect(firstCells(await panel("Paradas con más servicio"))).toEqual(["Plaça d'Espanya", "Inca (estació)"]);
    expect(within(await panel("Líneas con más salidas")).getByText("CTM · tren")).toBeTruthy();
  });

  it("gives each municipality its tourist dwellings per 1,000 inhabitants of the latest count", async () => {
    render(<Mobility />);
    const table = await panel("Municipios más poblados");

    expect(within(table).getByText("Viv. turísticas por 1.000")).toBeTruthy();
    expect(await within(table).findByText("2,3")).toBeTruthy(); // Palma in May 2026, not November 2025
    expect(within(table).getAllByText("—").length).toBeGreaterThan(0); // Inca was not counted in the answer
  });

  it("gives each municipality its unemployment per 1,000 inhabitants of the latest month", async () => {
    render(<Mobility />);
    const table = await panel("Municipios más poblados");

    expect(within(table).getByText("Paro por 1.000")).toBeTruthy();
    expect(await within(table).findByText("30,8")).toBeTruthy(); // Palma in October, not September
  });

  it("still draws the municipalities when the unemployment fails", async () => {
    vi.spyOn(api, "municipalUnemployment").mockRejectedValue(new Error("503"));
    render(<Mobility />);

    expect(firstCells(await panel("Municipios más poblados"))).toEqual(["Palma", "Inca"]);
  });

  it("still draws the municipalities when the tourist dwellings fail", async () => {
    vi.spyOn(api, "touristDwellings").mockRejectedValue(new Error("503"));
    render(<Mobility />);

    expect(firstCells(await panel("Municipios más poblados"))).toEqual(["Palma", "Inca"]);
  });

  it("follows the municipality chosen in the table in the population chart", async () => {
    render(<Mobility />);
    const table = await panel("Municipios más poblados");

    fireEvent.click(within(table).getByText("Inca"));

    expect(await screen.findByRole("figure", { name: /^Población de Inca a 1 de enero/ })).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "Municipio" }) as HTMLSelectElement).value).toBe("07027");
  });
});

describe("Mobility BiciPalma", () => {
  it("lists the stations that ran out of bikes for the most hours, and charts the network hour by hour", async () => {
    render(<Mobility />);

    expect(firstCells(await panel("Estaciones que más se vacían"))).toEqual(["45 JAUME III", "01 PARC DE SES VELES"]);
    expect(screen.getByRole("figure", { name: "Bicis libres, eléctricas y estaciones vacías de BiciPalma cada hora" })).toBeTruthy();
    expect(screen.getByText(/Datos hasta el 26 de noviembre de 2026/)).toBeTruthy();
  });
});
