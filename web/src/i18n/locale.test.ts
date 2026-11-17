// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import { locale, localizedPath, preferredLocale, setLocale, splitPath, startLocale } from "./locale";

afterEach(() => {
  setLocale("es");
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("splitPath and localizedPath", () => {
  it("takes the language off the path", () => {
    expect(splitPath("/ca/movilidad")).toEqual({ locale: "ca", path: "/movilidad" });
    expect(splitPath("/en/")).toEqual({ locale: "en", path: "/" });
    expect(splitPath("/en")).toEqual({ locale: "en", path: "/" });
    expect(splitPath("/es/clima-y-agua")).toEqual({ locale: "es", path: "/clima-y-agua" });
  });

  it("leaves paths without a language alone, including ones that start like one", () => {
    expect(splitPath("/movilidad")).toEqual({ locale: null, path: "/movilidad" });
    expect(splitPath("/")).toEqual({ locale: null, path: "/" });
    expect(splitPath("/fr/movilidad")).toEqual({ locale: null, path: "/fr/movilidad" });
    expect(splitPath("/english")).toEqual({ locale: null, path: "/english" });
  });

  it("puts it back", () => {
    expect(localizedPath("ca", "/movilidad")).toBe("/ca/movilidad");
    expect(localizedPath("en", "/")).toBe("/en/");
    for (const path of ["/", "/operacion"]) expect(splitPath(localizedPath("ca", path)).path).toBe(path);
  });
});

describe("preferredLocale", () => {
  it("prefers the language chosen before with the selector", () => {
    expect(preferredLocale("ca", ["en-US"])).toBe("ca");
  });

  it("else takes the first of the browser's languages that the web speaks", () => {
    expect(preferredLocale(null, ["fr-FR", "ca-ES-valencia", "es"])).toBe("ca");
    expect(preferredLocale(null, ["en-US"])).toBe("en");
    expect(preferredLocale("de", ["ES"])).toBe("es");
  });

  it("else speaks Spanish", () => {
    expect(preferredLocale(null, ["fr-FR", "de"])).toBe("es");
    expect(preferredLocale(null, [])).toBe("es");
  });
});

describe("startLocale", () => {
  it("rewrites an address without language so that a copied link keeps it, with its query", () => {
    window.history.replaceState(null, "", "/explorador?source=aemet#chart");
    localStorage.setItem("mdp-locale", "ca");
    expect(startLocale()).toBe("ca");
    expect(window.location.pathname).toBe("/ca/explorador");
    expect(window.location.search).toBe("?source=aemet");
    expect(window.location.hash).toBe("#chart");
    expect(locale()).toBe("ca");
    expect(document.documentElement.lang).toBe("ca");
  });

  it("follows the address over the remembered choice: a shared link opens in its language", () => {
    window.history.replaceState(null, "", "/en/movilidad");
    localStorage.setItem("mdp-locale", "ca");
    expect(startLocale()).toBe("en");
    expect(window.location.pathname).toBe("/en/movilidad");
    expect(localStorage.getItem("mdp-locale")).toBe("ca");
  });

  it("uses the browser's language for a first visit", () => {
    vi.stubGlobal("navigator", { ...navigator, languages: ["en-GB", "es"] });
    window.history.replaceState(null, "", "/");
    expect(startLocale()).toBe("en");
    expect(window.location.pathname).toBe("/en/");
  });
});
