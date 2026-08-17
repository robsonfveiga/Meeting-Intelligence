import { useMemo } from "react";
import type { ScoredChunk } from "../models/answer";
import type { Fact } from "../models/fact";
import type { Meeting } from "../models/transcript";
import type { TimelineBand, TimelineTick } from "../models/timeline";

/** Guards against a zero-duration meeting turning every offset into NaN. */
function offsetOf(startMs: number, durationMs: number): number {
  if (durationMs <= 0) return 0;
  return Math.min(1, Math.max(0, startMs / durationMs));
}

/** "04 Mar" reads faster than "2026-03-04" when four of them are stacked. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "—";
  return when.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

export function formatClock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * Assembles the two layers the backend never joins.
 *
 * Resting layer: every extracted fact, at the second it was said. Overlay: the
 * excerpts the current answer was built from, keyed to their citation markers so
 * a tick and a `[2]` in the prose are visibly the same thing.
 */
export function useTimeline(
  meetings: Meeting[],
  facts: Fact[],
  excerpts: ScoredChunk[],
  citedChunkIds: Map<string, number>,
): TimelineBand[] {
  return useMemo(() => {
    // `id` is optional in the generated schema because the model defaults it,
    // even though the API always sends one. A meeting with no identifier cannot
    // be keyed or linked, so it is dropped here rather than cast away.
    const ordered = meetings
      .filter((meeting): meeting is Meeting & { id: string } => typeof meeting.id === "string")
      .sort((a, b) => (a.occurred_at ?? "").localeCompare(b.occurred_at ?? ""));
    const longest = Math.max(1, ...ordered.map((m) => m.duration_ms ?? 0));

    return ordered.map((meeting) => {
      const durationMs = meeting.duration_ms ?? 0;

      const factTicks: TimelineTick[] = facts
        .filter((fact) => fact.meeting_id === meeting.id)
        .map((fact) => ({
          id: fact.id,
          kind: fact.kind,
          offset: offsetOf(fact.time.start_ms, durationMs),
          label: fact.statement,
          detail: [fact.owner, fact.due].filter(Boolean).join(" · "),
        }));

      const evidenceTicks: TimelineTick[] = excerpts
        .filter((hit) => hit.meeting_id === meeting.id)
        .map((hit) => ({
          id: `evidence-${hit.chunk_id}`,
          kind: "evidence" as const,
          offset: offsetOf(hit.time.start_ms, durationMs),
          label: hit.text,
          detail: hit.speakers.join(", "),
          marker: citedChunkIds.get(hit.chunk_id),
        }));

      return {
        meetingId: meeting.id,
        title: meeting.title,
        date: formatDate(meeting.occurred_at),
        durationMs,
        // A floor of 25%, so a very short meeting is still a clickable band
        // rather than a sliver.
        widthShare: Math.max(0.25, durationMs / longest),
        ticks: [...factTicks, ...evidenceTicks],
      };
    });
  }, [meetings, facts, excerpts, citedChunkIds]);
}
