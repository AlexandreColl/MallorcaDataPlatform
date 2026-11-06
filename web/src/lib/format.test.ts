import { describe, expect, it } from "vitest";

import { number, orDash } from "./format";

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
