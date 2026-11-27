import { describe, expect, it } from "vitest";

import type { BikeStation, Municipality, PopulationYear, StopService, TouristDwellings, TransitRoute } from "../api";
import { bikeLayer, emptiestStations, mobilityKpis, municipalityRows, routesSubtitle, stopLayers, withSelected } from "./mobility";

// A square municipality around (lon, lat), 0.1° a side.
const place = (municipality: string, name: string, lon: number, lat: number) =>
  ({
    municipality, name,
    polygon: [[[lon - 0.05, lat - 0.05], [lon + 0.05, lat - 0.05], [lon + 0.05, lat + 0.05], [lon - 0.05, lat + 0.05]]],
  }) as Municipality;
const register = (municipality: string, year: number, population: number) =>
  ({ municipality, year, population, density_per_km2: population / 10 }) as PopulationYear;
const stop = (network: "emt_palma" | "ctm", lon: number, lat: number, departures: number) =>
  ({ network, stop: `stop_${lon}`, name: null, lon, lat, departures, lines: 2, local_date: "2026-11-11" }) as StopService;

describe("municipalityRows", () => {
  it("joins the register, the change in ten years and the service per inhabitant, the most populated first", () => {
    const places = [place("07001", "Alaró", 2.79, 39.7), place("07040", "Palma", 2.65, 39.57)];
    const population = [
      register("07001", 2016, 5000), register("07001", 2026, 5500),
      register("07040", 2016, 400_000), register("07040", 2026, 440_000),
    ];

    const rows = municipalityRows(places, population, [stop("emt_palma", 2.65, 39.57, 880)], 2026);

    expect(rows.map((r) => r.place.name)).toEqual(["Palma", "Alaró"]);
    expect(rows[0]?.growth).toBeCloseTo(0.1);
    expect(rows[0]).toMatchObject({ perThousand: 2, service: { stops: 1, departures: 880 } });
    expect(rows[1]).toMatchObject({ perThousand: 0, service: { stops: 0, departures: 0 } });
  });

  it("takes the tourist dwellings of the latest count only", () => {
    const places = [place("07042", "Pollença", 3.03, 39.89), place("07040", "Palma", 2.65, 39.57)];
    const count = (municipality: string, reference_month: string, tourist_dwellings: number) =>
      ({ municipality, reference_month, tourist_dwellings }) as TouristDwellings;
    const dwellings = [count("07042", "2025-11-01", 2385), count("07042", "2026-05-01", 2344), count("07040", "2025-11-01", 1100)];

    const rows = municipalityRows(places, [], [], 2026, dwellings);

    expect(rows.find((r) => r.place.name === "Pollença")?.dwellings?.tourist_dwellings).toBe(2344);
    expect(rows.find((r) => r.place.name === "Palma")?.dwellings).toBeUndefined(); // not in May 2026
  });

  it("keeps the selected municipality at the end of the top twelve", () => {
    const rows = Array.from({ length: 15 }, (_, i) => ({ place: place(`0700${i}`, `M${i}`, 2, 39) }));

    expect(withSelected(rows as never, "07003")).toHaveLength(12);
    expect(withSelected(rows as never, "070014").at(-1)?.place.name).toBe("M14");
  });
});

describe("stopLayers", () => {
  it("gives each network a layer, the busiest stop the largest point", () => {
    const [emt, ctm] = stopLayers([stop("emt_palma", 2.6, 39.5, 100), stop("emt_palma", 2.7, 39.6, 25), stop("ctm", 3, 39.8, 4)]);

    expect(emt?.points.map((p) => p.size)).toEqual([2.5, 1.5]); // area proportional to the departures
    expect(ctm?.points[0]?.popup).toEqual(["stop_3", "CTM", "4 pasos · 2 líneas"]);
  });
});

describe("mobilityKpis", () => {
  it("shows the stop calls of the latest day of each network", () => {
    const day = (network: string, local_date: string, calls: number | null) =>
      ({ network, local_date, scheduled_stop_calls: calls, is_weekend: false, stops: 10, stops_with_service: 8 }) as never;

    const kpis = mobilityKpis([day("emt_palma", "2026-11-10", 1000), day("emt_palma", "2026-11-11", 1200), day("ctm", "2026-11-11", null)]);

    expect(kpis).toHaveLength(1); // CTM has no day with service yet
    expect(kpis[0]).toMatchObject({ value: "1200", month: "11 de noviembre de 2026, laborable", deviation: "8 de 10 paradas con servicio" });
  });
});

describe("routesSubtitle", () => {
  it("names the day of the timetables", () => {
    expect(routesSubtitle(null)).toContain("salidas tiene el último día");
    expect(routesSubtitle([{ local_date: "2026-11-11" } as TransitRoute])).toContain("el 11 de noviembre de 2026");
  });
});

const station = (name: string, docks: number, empty: number, full: number) =>
  ({
    station: `station_${name}`, name, lat: 39.57, lon: 2.65, local_date: "2026-11-26", hours_observed: 24,
    bikes_available: 7.25, ebikes_available: 1.5, occupancy_pct: 36.4, working_docks: docks, hours_empty: empty,
    hours_full: full,
  }) as BikeStation;

describe("bikeLayer", () => {
  it("sizes each station by its working docks and gives it the card of its day", () => {
    const layer = bikeLayer([station("01 PARC DE SES VELES", 20, 2, 1), station("45 JAUME III", 5, 0, 0)]);

    expect(layer.label).toBe("BiciPalma");
    expect(layer.points.map((p) => Number(p.size?.toFixed(2)))).toEqual([2, 1.3]);
    expect(layer.points[0]?.popup).toEqual([
      "01 PARC DE SES VELES",
      "7,3 bicis libres de media (1,5 eléctricas)",
      "Ocupación media del 36 % · 20 anclajes en uso",
      "Sin bicis 2 h y llena 1 h, de 24 h",
    ]);
  });
});

describe("emptiestStations", () => {
  it("puts first the stations that ran out of bikes for the most hours, then the fullest", () => {
    const rows = emptiestStations([station("a", 10, 0, 3), station("b", 10, 5, 0), station("c", 10, 0, 0)]);

    expect(rows.map((s) => s.name)).toEqual(["b", "a", "c"]);
  });
});
