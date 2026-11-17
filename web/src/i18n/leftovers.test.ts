// Every text the page shows lives in the dictionaries. This finds the Spanish ones written straight into the code,
// which tsc cannot see: a string or a JSX text with a Spanish letter or one of its most common words.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { expect, it } from "vitest";

const SRC = join(__dirname, "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "i18n" ? [] : files(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && name !== "api.gen.ts" ? [path] : [];
  });
}

/** Spanish letters, or two words in a row where one is a frequent Spanish word ("de la", "sin datos"). */
const SPANISH = /[áéíóúñ¿¡]|\b(?:de|del|el|la|las|los|en|por|con|sin|para|una?|y|que|cada)\s+\p{L}/iu;

/** Strings and JSX texts of a file, without comments. */
function texts(source: string): string[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
  const strings = [...code.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)].map((m) => m[1] ?? m[2] ?? m[3] ?? "");
  const jsx = [...code.matchAll(/>([^<>{}=;()]*[\p{L}][^<>{}=;()]*)</gu)].map((m) => m[1] ?? "");
  return [...strings, ...jsx];
}

it("leaves no Spanish text outside the dictionaries", () => {
  const found = files(SRC).flatMap((path) =>
    texts(readFileSync(path, "utf8"))
      .filter((text) => SPANISH.test(text))
      .map((text) => `${relative(SRC, path)}: ${text.trim().slice(0, 80)}`),
  );
  expect(found).toEqual([]);
});
