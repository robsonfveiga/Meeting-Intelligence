import { useCallback, useEffect, useState } from "react";
import { listFacts } from "../api/facts";
import type { Fact } from "../models/fact";

export function useFacts() {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloads, setReloads] = useState(0);

  const refresh = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const found = await listFacts();
        if (!cancelled) setFacts(found);
      } catch {
        // The record is a secondary surface. Failing to load it should not take
        // the page down, so it degrades to empty and the empty state explains why.
        if (!cancelled) setFacts([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [reloads]);

  return { facts, loading, refresh };
}
