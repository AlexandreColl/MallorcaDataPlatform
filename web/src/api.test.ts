// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";
import { setLocale } from "./i18n";

afterEach(() => {
  setLocale("es");
  vi.unstubAllGlobals();
});

it("asks the API in the language of the page, for the catalogue's labels and licences", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  setLocale("ca");

  await api.sources();

  expect(fetch).toHaveBeenCalledWith("/api/v1/sources", { headers: { "Accept-Language": "ca" } });
});
