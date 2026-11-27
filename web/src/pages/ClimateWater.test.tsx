// @vitest-environment happy-dom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api";
import { MESSAGES, setLocale } from "../i18n";
import { ClimateWater } from "./ClimateWater";

// ECharts needs a canvas: the page is checked without it, with each chart as a figure named by its label.
vi.mock("../components/Chart", () => ({ Chart: ({ label }: { label: string }) => <figure aria-label={label} />, SERIES: ["#000"] }));

const answers: Record<string, unknown[]> = {
  water: [],
  climate: [],
  aquifers: [],
  seaTemperature: [
    { month: "2025-07-01", points: 8, days_reported: 31, sst_mean_c: 27.9, sst_climatology_c: 25.6, sst_anomaly_c: 2.3, heatwave_days: 24.5, days_with_heatwave: 31, has_preliminary_days: false },
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

  it.each(["ca", "en"] as const)("speaks %s", async (language) => {
    setLocale(language);
    const m = MESSAGES[language].climate;
    render(<ClimateWater />);

    expect(await within(await panel(m.seaTitle)).findByRole("figure", { name: m.seaChart })).toBeTruthy();
  });
});
