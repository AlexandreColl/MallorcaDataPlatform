// @vitest-environment happy-dom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { MESSAGES, setLocale } from "../i18n";
import { ClimateWater } from "./ClimateWater";

// ECharts needs a canvas: the page is checked without it, with each chart as a figure named by its label.
vi.mock("../components/Chart", () => ({ Chart: ({ label }: { label: string }) => <figure aria-label={label} />, SERIES: ["#000"] }));
// maplibre needs WebGL: the map is a list of its layers, each with the cards of its points.
vi.mock("../components/PointMap", () => ({
  PointMap: ({ layers }: { layers: { id: string; label: string; points: { popup: string[] }[] }[] }) => (
    <ul aria-label="mapa">
      {layers.map((l) => (
        <li key={l.id}>
          {l.label}: {l.points.map((p) => p.popup[0]).join(", ")}
        </li>
      ))}
    </ul>
  ),
}));

const answers: Record<string, unknown[]> = {
  water: [],
  climate: [],
  aquifers: [],
  seaTemperature: [
    { month: "2025-07-01", points: 8, days_reported: 31, sst_mean_c: 27.9, sst_climatology_c: 25.6, sst_anomaly_c: 2.3, heatwave_days: 24.5, days_with_heatwave: 31, has_preliminary_days: false },
  ],
  bathingWaters: [
    { bathing_water: "1034", name: "Playa Formentor", municipality: "07042", municipality_name: "Pollença", sampling_points: 1, lat: 39.96, lon: 3.13, season: 2026, samples: 9, last_sample_date: "2026-09-22", worst_e_coli: 31, worst_enterococci: 10, samples_not_fit: 0, restrictions: 0, bans: 0, restricted_days: 0, assessed_samples: 36, assessed_seasons: 4, p95_e_coli: 40.1, p95_enterococci: 12.0, p90_e_coli: 30.2, p90_enterococci: 11.0, quality_class: 4, quality: "excellent", previous_quality_class: 4, quality_class_change: 0 },
  ],
  bathingWaterYears: [
    { season: 2026, bathing_waters: 87, classified: 87, excellent: 80, good: 5, sufficient: 1, poor: 1, excellent_share: 0.92, downgraded: 2, upgraded: 1, samples: 1065, samples_not_fit: 30, samples_not_fit_share: 0.0282, restrictions: 20, bans: 5, restricted_days: 60, worst_e_coli: 17329, worst_enterococci: 5172 },
  ],
};

beforeEach(() => {
  const spied = api as unknown as Record<string, () => Promise<unknown>>;
  for (const [name, rows] of Object.entries(answers)) vi.spyOn(spied, name).mockResolvedValue(rows);
});
afterEach(() => {
  cleanup();
  setLocale("es");
  vi.restoreAllMocks();
});

const panel = async (title: string) => (await screen.findByRole("heading", { name: title })).closest("section") as HTMLElement;

describe("ClimateWater", () => {
  it("shows the sea anomaly and its heatwave days next to the air temperature", async () => {
    render(<ClimateWater />);

    const sea = await panel("El mar frente a lo normal");
    expect(await within(sea).findByRole("figure", { name: MESSAGES.es.climate.seaChart })).toBeTruthy();
    expect(await panel("Temperatura frente a lo normal")).toBeTruthy();
    expect(api.seaTemperature).toHaveBeenCalledWith("2016-01-01");
  });

  it("maps the beaches by their class and charts the share of excellent waters", async () => {
    render(<ClimateWater />);

    const map = await panel("Calidad de las aguas de baño");
    expect((await within(map).findByRole("list", { name: "mapa" })).textContent).toContain("Excelente: Playa Formentor");
    expect(within(map).getByText(/en 2026/)).toBeTruthy();
    const trend = await panel("Aguas de baño excelentes");
    expect(await within(trend).findByRole("figure", { name: MESSAGES.es.bathing.trendChart })).toBeTruthy();
  });

  it.each(["ca", "en"] as const)("speaks %s", async (language) => {
    setLocale(language);
    const m = MESSAGES[language].climate;
    render(<ClimateWater />);

    expect(await within(await panel(m.seaTitle)).findByRole("figure", { name: m.seaChart })).toBeTruthy();
    const b = MESSAGES[language].bathing;
    expect(await within(await panel(b.trendTitle)).findByRole("figure", { name: b.trendChart })).toBeTruthy();
  });
});
