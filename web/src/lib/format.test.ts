// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { setLocale } from "../i18n";
import { age, compact, dayName, dayShort, monthName, monthShort, number, orDash, placeName, signed } from "./format";

afterEach(() => setLocale("es"));

// The expected texts are what Node's ICU writes; a browser with another ICU version may differ in a dot or a space.
describe.each([
  {
    language: "es" as const,
    texts: ["1234,5", "12.345", "2,6 M", "62 mil", "−11,5", "agosto de 2026", "ago 26", "4 nov", "4 de noviembre de 2026",
      "hace 3 h", "hace 5 días", "hace 3 meses", "hace menos de 1 h"],
  },
  {
    language: "ca" as const,
    texts: ["1.234,5", "12.345", "2,6 M", "62 mil", "−11,5", "agost del 2026", "ag. 26", "4 de nov.", "4 de novembre del 2026",
      "fa 3 h", "fa 5 dies", "fa 3 mesos", "fa menys d’1 h"],
  },
  {
    language: "en" as const,
    texts: ["1,234.5", "12,345", "2.6 M", "62 k", "−11.5", "August 2026", "Aug 26", "4 Nov", "4 November 2026",
      "3 hr ago", "5 days ago", "3 months ago", "less than 1 h ago"],
  },
])("formats in $language", ({ language, texts }) => {
  it("numbers, months, days and ages", () => {
    setLocale(language);
    expect([
      number(1234.5, 1), number(12_345), compact(2_596_458), compact(61_950), signed(-11.5),
      monthName("2026-08-01"), monthShort("2026-08-01"), dayShort("2026-11-04"), dayName("2026-11-04T10:00:00Z"),
      age(3), age(5 * 24), age(90 * 24), age(0.5),
    ]).toEqual(texts);
  });
});

it("reads a day as a calendar day, whatever the time zone", () => {
  expect(dayShort("2026-01-01")).toBe("1 ene");
  expect(dayName("2026-12-31T23:30:00Z")).toBe("31 de diciembre de 2026");
});

describe("orDash", () => {
  const format = orDash((v) => `${number(v, 1)} %`);

  it("formats a number", () => {
    expect(format(36.25)).toBe("36,3 %");
    expect(format(0)).toBe("0,0 %");
  });

  it("shows a dash for a missing value instead of throwing (ECharts passes undefined for an empty month)", () => {
    for (const missing of [undefined, null, Number.NaN, "-"]) expect(format(missing)).toBe("—");
  });
});

describe("placeName", () => {
  it("prefers the name the source publishes and tidies identifiers that already read as one", () => {
    expect(placeName("B228", "Palma, Puerto")).toBe("Palma, Puerto");
    expect(placeName("cala_millor", null)).toBe("Cala millor");
    expect(placeName("palma")).toBe("Palma");
  });
});
