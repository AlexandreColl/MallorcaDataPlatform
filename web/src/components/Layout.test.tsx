// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type Locale, MESSAGES, setLocale } from "../i18n";
import { Layout } from "./Layout";

const dashboards = (language: Locale) => {
  const { home, mobility } = MESSAGES[language].dashboards;
  return [
    { path: "/", icon: "home" as const, ...home },
    { path: "/movilidad", icon: "mobility" as const, ...mobility },
  ];
};

function show(language: Locale, address: string) {
  setLocale(language);
  window.history.replaceState(null, "", address);
  const all = dashboards(language);
  render(
    <Layout dashboards={all} current={all[1]!} version="0.18.0">
      <p>page</p>
    </Layout>,
  );
}

afterEach(() => {
  cleanup();
  setLocale("es");
  localStorage.clear();
  vi.restoreAllMocks();
});

describe.each(["es", "ca", "en"] as const)("the layout in %s", (language) => {
  const m = MESSAGES[language];

  it("names the menu, the page and the footer in that language, and links pages in it", () => {
    show(language, `/${language}/movilidad`);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(m.dashboards.mobility.title);
    expect(screen.getByRole("complementary", { name: m.layout.dashboards })).toBeTruthy();
    expect(screen.getByText(m.layout.footer)).toBeTruthy();
    const menu = screen.getAllByRole("navigation")[0]!;
    const link = within(menu).getByRole("link", { name: m.dashboards.mobility.label });
    expect(link.getAttribute("href")).toBe(`/${language}/movilidad`);
    expect(link.getAttribute("aria-current")).toBe("page");
  });

  it("offers the same page, with its filters, in each language, each named in itself", () => {
    show(language, `/${language}/movilidad?network=ctm`);
    const selector = screen.getByRole("navigation", { name: m.layout.language });
    const links = within(selector).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href"), a.getAttribute("lang")])).toEqual([
      ["Castellano", "/es/movilidad?network=ctm", "es"],
      ["Català", "/ca/movilidad?network=ctm", "ca"],
      ["English", "/en/movilidad?network=ctm", "en"],
    ]);
    expect(links.filter((a) => a.getAttribute("aria-current") === "true").map((a) => a.getAttribute("lang"))).toEqual([language]);
  });
});

it("remembers the language chosen and opens the page in it", () => {
  show("es", "/es/movilidad");
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign, search: "?network=emt_palma", hash: "" });
  fireEvent.click(screen.getByRole("link", { name: "Català" }));
  expect(localStorage.getItem("mdp-locale")).toBe("ca");
  expect(assign).toHaveBeenCalledWith("/ca/movilidad?network=emt_palma");
});
