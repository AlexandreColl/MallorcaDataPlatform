import { useEffect, useState } from "react";

export type Loaded<T> = { status: "loading" } | { status: "error"; error: string } | { status: "ready"; data: T };

/** Runs `load` once and keeps its result: the page shows a skeleton, the data or the error. */
export function useLoad<T>(load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  useEffect(() => {
    let active = true;
    load()
      .then((data) => active && setState({ status: "ready", data }))
      .catch((error: unknown) => active && setState({ status: "error", error: String(error) }));
    return () => {
      active = false;
    };
  }, []);
  return state;
}

/** True while the system (or the browser) is in dark mode; follows changes. */
export function useDarkMode(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setDark(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return dark;
}
