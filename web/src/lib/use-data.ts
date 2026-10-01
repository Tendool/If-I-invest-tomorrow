"use client";
/* Data fetching on mount/dependency change legitimately sets state inside effects. */
/* eslint-disable react-hooks/refs, react-hooks/set-state-in-effect */

import * as React from "react";

export interface DataState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Tiny fetch hook: re-runs when `deps` change; ignores stale responses. Pass `enabled=false` to skip. */
export function useData<T>(fetcher: () => Promise<T>, deps: React.DependencyList, enabled = true): DataState<T> {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(enabled);
  const [error, setError] = React.useState<string | null>(null);
  const [tick, setTick] = React.useState(0);
  const fetchRef = React.useRef(fetcher);
  fetchRef.current = fetcher;

  React.useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let live = true;
    setLoading(true);
    setError(null);
    fetchRef
      .current()
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
