import { useEffect, useState } from "react";

export type Loaded<T> = { status: "loading" } | { status: "error"; error: string } | { status: "ready"; data: T };

/**
 * Runs `load` on mount and again whenever one of `deps` changes, and keeps its result: the page shows a skeleton,
 * the data or the error. A reload keeps showing the previous data until the new one arrives, and an answer that
 * arrives after a newer request was started is dropped.
 */
export function useLoad<T>(load: () => Promise<T>, deps: readonly unknown[] = []): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  useEffect(() => {
    let active = true;
    load()
      .then((data) => active && setState({ status: "ready", data }))
      .catch((error: unknown) => active && setState({ status: "error", error: String(error) }));
    return () => {
      active = false;
    };
  }, deps); // not `load`: it is a new closure on every render
  return state;
}

/** The data when it is ready, otherwise null (to build key figures from several requests). */
export function ready<T>(state: Loaded<T>): T | null {
  return state.status === "ready" ? state.data : null;
}
