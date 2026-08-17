import { useCallback, useEffect, useState } from "react";
import { deleteMeeting, listMeetings } from "../api/meetings";
import type { Meeting } from "../models/transcript";

/**
 * Loads the corpus, and reloads on demand after an ingest.
 *
 * The reload is a counter rather than an exposed fetch function, so the request
 * only ever happens inside an effect that can cancel it. Without that, a refresh
 * racing an unmount resolves into a component that no longer exists.
 */
export function useMeetings() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const refresh = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const found = await listMeetings();
        if (cancelled) return;
        setMeetings(found);
        setError(null);
      } catch {
        if (!cancelled) setError("Could not reach the API. Is the stack running?");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [reloads]);

  /**
   * Deletes, then drops the row locally rather than refetching.
   *
   * The server has already confirmed what changed, and exactly one meeting
   * changed, so a second round trip would only reproduce a list we can compute.
   * It throws on failure and leaves the list alone — the caller decides how to
   * report it, because a delete that quietly does nothing is the worst outcome.
   */
  const remove = useCallback(async (id: string) => {
    await deleteMeeting(id);
    setMeetings((current) => current.filter((meeting) => meeting.id !== id));
  }, []);

  return { meetings, loading, error, refresh, remove };
}
