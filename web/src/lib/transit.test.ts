import { describe, expect, it } from "vitest";

import type { TransitRoute } from "../api";
import { routePopup, routeWidth } from "./transit";

const M1: TransitRoute = {
  network: "ctm",
  route: "route_216",
  short_name: "M1",
  name: "M1 · Palma - UIB - ParcBit",
  kind: "metro",
  color: "#ffdd00",
  local_date: "2026-11-06",
  trips: 98,
  geometry: { type: "MultiLineString", coordinates: [] },
};

describe("routeWidth", () => {
  it("grows with the square root of the departures, from 1 px to 5 px for the busiest line", () => {
    expect(routeWidth(200, 200)).toBe(5);
    expect(routeWidth(50, 200)).toBe(3);
    expect(routeWidth(0, 200)).toBe(1);
  });

  it("draws a line without timetable, or a network without service, at the thinnest width", () => {
    expect(routeWidth(null, 200)).toBe(1);
    expect(routeWidth(0, 0)).toBe(1);
  });
});

describe("routePopup", () => {
  it("names the line, its network and kind, and its departures that day", () => {
    expect(routePopup(M1, "CTM")).toEqual(["M1 · Palma - UIB - ParcBit", "CTM · metro", "98 salidas el 6 de noviembre de 2026"]);
  });

  it("says when the line has no timetable on the latest day", () => {
    expect(routePopup({ ...M1, trips: null, local_date: null }, "CTM")[2]).toBe("Sin horario el último día");
  });
});
