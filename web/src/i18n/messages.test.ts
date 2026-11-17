import { describe, expect, it } from "vitest";

import { LOCALES, MESSAGES } from ".";

/** Every text of a dictionary as "path -> value": a string, or a function as its number of parameters. */
function leaves(node: object, prefix = ""): Map<string, unknown> {
  const found = new Map<string, unknown>();
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "object" && value !== null) {
      for (const [k, v] of leaves(value, path)) found.set(k, v);
    } else {
      found.set(path, value);
    }
  }
  return found;
}

const spanish = leaves(MESSAGES.es);

describe.each(LOCALES)("the %s texts", (language) => {
  const texts = leaves(MESSAGES[language]);

  // tsc already fails on a missing text; this also catches one added with a cast, or with a different parameter list.
  it("have the same texts as Spanish, with the same parameters", () => {
    expect([...texts.keys()].sort()).toEqual([...spanish.keys()].sort());
    for (const [path, value] of texts) {
      const reference = spanish.get(path);
      expect(typeof value, path).toBe(typeof reference);
      if (typeof value === "function" && typeof reference === "function") expect(value.length, path).toBe(reference.length);
    }
  });

  it("leave none empty", () => {
    for (const [path, value] of texts) {
      const text = typeof value === "function" ? value(...Array.from({ length: value.length }, () => "x")) : value;
      expect(String(text).trim(), path).not.toBe("");
    }
  });
});

