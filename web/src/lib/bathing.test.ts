// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import type { BathingWaterSeason, BathingWaterYear } from "../api";
import { setLocale } from "../i18n";
import { bathingCard, bathingLayers, changeText, latestShare, qualityName, QUALITY_COLORS } from "./bathing";
import { number } from "./format";

const water = (overrides: Partial<BathingWaterSeason>): BathingWaterSeason => ({
  bathing_water: "1038",
  name: "Playa dels Tamarells (Port de Pollença)",
  municipality: "07042",
  municipality_name: "Pollença",
  sampling_points: 3,
  lat: 39.9,
  lon: 3.08,
  season: 2026,
  samples: 27,
  last_sample_date: "2026-09-22",
  worst_e_coli: 1291,
  worst_enterococci: 52,
  samples_not_fit: 2,
  restrictions: 2,
  bans: 0,
  restricted_days: 4,
  assessed_samples: 108,
  assessed_seasons: 4,
  p95_e_coli: 410.2,
  p95_enterococci: 80.1,
  p90_e_coli: 250.3,
  p90_enterococci: 50.2,
  quality_class: 3,
  quality: "good",
  previous_quality_class: 4,
  quality_class_change: -1,
  ...overrides,
});

const year = (season: number, classified: number, excellent_share: number | null): BathingWaterYear => ({
  season,
  bathing_waters: 87,
  classified,
  excellent: 0,
  good: 0,
  sufficient: 0,
  poor: 0,
  excellent_share,
  downgraded: 0,
  upgraded: 0,
  samples: 0,
  samples_not_fit: 0,
  samples_not_fit_share: null,
  restrictions: 0,
  bans: 0,
  restricted_days: 0,
  worst_e_coli: null,
  worst_enterococci: null,
});

afterEach(() => setLocale("es"));

describe("bathing water quality", () => {
  it("names the classes and the waters without one", () => {
    expect(qualityName(4)).toBe("Excelente");
    expect(qualityName(1)).toBe("Insuficiente");
    expect(qualityName(null)).toBe("Sin clasificar");
  });

  it("says how the class moved against the previous season", () => {
    expect(changeText(water({}))).toBe("Baja desde excelente");
    expect(changeText(water({ quality_class: 4, previous_quality_class: 3 }))).toBe("Sube desde buena");
    expect(changeText(water({ quality_class: 4, previous_quality_class: 4 }))).toBe("Igual que la temporada anterior");
    expect(changeText(water({ previous_quality_class: null }))).toBeNull();
  });

  it("writes the card of a beach with its samples, worst results and restrictions", () => {
    const card = bathingCard(water({}));

    expect(card[0]).toBe("Playa dels Tamarells (Port de Pollença)");
    expect(card).toContain("Clase en 2026: Buena");
    expect(card.some((l) => l.includes(number(1291)) && l.includes("52"))).toBe(true);
    expect(card.some((l) => l.includes("2 restricciones"))).toBe(true);
    expect(bathingCard(water({ quality_class: null, assessed_samples: 9 }))).toContain(
      "Solo 9 muestras en cuatro temporadas (hacen falta 16)",
    );
  });

  it("draws one layer per class, best first, and skips the empty ones", () => {
    const layers = bathingLayers([water({ quality_class: 4 }), water({ quality_class: 4 }), water({ quality_class: null })]);

    expect(layers.map((l) => l.id)).toEqual(["bathing-4", "bathing-none"]);
    expect(layers[0]?.color).toBe(QUALITY_COLORS[4]);
    expect(layers[0]?.points).toHaveLength(2);
  });

  it("takes the share of the latest season with classified waters", () => {
    expect(latestShare([year(2024, 80, 0.9), year(2025, 85, 0.93), year(2026, 0, null)])?.season).toBe(2025);
    expect(latestShare([year(2023, 0, null)])).toBeNull();
  });

  it("speaks Catalan and English", () => {
    setLocale("ca");
    expect(qualityName(2)).toBe("Suficient");
    setLocale("en");
    expect(qualityName(3)).toBe("Good");
  });
});
