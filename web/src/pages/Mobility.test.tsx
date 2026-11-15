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
  humanPressure: [],
  routes: [{ network: "ctm", route: "route_1", short_name: "T1", name: "T1 · Palma - Inca", kind: "train", color: null, local_date: "2026-11-11", trips: 64, geometry: { type: "MultiLineString", coordinates: [] } }],
};

beforeEach(() => {
  for (const [name, rows] of Object.entries(answers)) vi.spyOn(api, name as keyof typeof api).mockResolvedValue(rows as never);
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

  it("follows the municipality chosen in the table in the population chart", async () => {
    render(<Mobility />);
    const table = await panel("Municipios más poblados");

    fireEvent.click(within(table).getByText("Inca"));

    expect(await screen.findByRole("figure", { name: /^Población de Inca a 1 de enero/ })).toBeTruthy();
    expect((screen.getByRole("combobox", { name: "Municipio" }) as HTMLSelectElement).value).toBe("07027");
  });
});
