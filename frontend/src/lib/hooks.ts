"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "./api";

/**
 * Minimal data-fetching hook. `reload()` refetches in the background, keeping the current data
 * on screen (so polling does not flash skeletons). Pass null to skip.
 */
export function useApi<T>(path: string | null) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ key: string; data: T | null; error: string | null }>({
    key: "",
    data: null,
    error: null,
  });
  const key = `${path}#${version}`;

  useEffect(() => {
    if (!path) return;
    let live = true;
    api<T>(path)
      .then((data) => live && setResult({ key, data, error: null }))
      .catch((e) => live && setResult((r) => ({ key, data: r.data, error: e instanceof Error ? e.message : String(e) })));
    return () => {
      live = false;
    };
  }, [path, key]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const setData = useCallback(
    (update: T | null | ((prev: T | null) => T | null)) =>
      setResult((r) => ({ ...r, data: typeof update === "function" ? (update as (p: T | null) => T | null)(r.data) : update })),
    [],
  );

  return { data: result.data, error: result.error, loading: !!path && result.key !== key, reload, setData };
}

export function formatDuration(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec.toString().padStart(2, "0")}s`;
  return `${sec}s`;
}

export function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
