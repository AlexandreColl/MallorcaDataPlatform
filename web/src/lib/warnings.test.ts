import { describe as group, expect, it } from "vitest";

import type { WeatherWarning } from "../api";
import { describe, overlapping, zoneLevels } from "./warnings";

function warning(zone: string, level: number, start: string, end: string, phenomenon = "rain"): WeatherWarning {
  return {
    warning_id: `${zone}-${start}`, zone, zone_name: null, zone_kind: "land", phenomenon, level,
    start_ts: start, end_ts: end,
  };
}

const W = [
  warning("645401", 1, "2026-11-05T03:00:00Z", "2026-11-05T19:00:00Z"),
  warning("645401", 2, "2026-11-05T19:00:00Z", "2026-11-06T06:00:00Z", "wind"),
  warning("645404", 1, "2026-11-07T00:00:00Z", "2026-11-07T12:00:00Z"),
];

group("warnings", () => {
  it("keeps the warnings that overlap the period, ends excluded", () => {
    const now = new Date("2026-11-05T10:00:00Z");
    expect(overlapping(W, now, new Date("2026-11-05T11:00:00Z"))).toHaveLength(1);
    expect(overlapping(W, new Date("2026-11-05T19:00:00Z"), new Date("2026-11-05T20:00:00Z"))).toHaveLength(1);
    expect(overlapping(W, now, new Date("2026-11-08T00:00:00Z"))).toHaveLength(3);
  });

  it("colours each zone with its highest level", () => {
    const levels = zoneLevels(W);
    expect(levels.get("645401")).toBe(2);
    expect(levels.get("645404")).toBe(1);
    expect(levels.has("645403")).toBe(false);
  });

  it("puts a warning in words", () => {
    expect(describe(W[0] as WeatherWarning)).toBe("Amarillo por lluvias");
    expect(describe(W[1] as WeatherWarning)).toBe("Naranja por viento");
  });
});
