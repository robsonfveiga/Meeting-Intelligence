import type { FactKind } from "./fact";

/**
 * View models the API has no opinion about.
 *
 * The timeline is assembled in the browser from two sources that the backend
 * never joins: the extracted facts (the resting layer — what was settled, owed
 * or left open, at the moment it was said) and the excerpts an answer was built
 * from (the overlay — what this particular answer rests on).
 *
 * Two layers with different meanings, rather than one merged list, because
 * "this is where a decision was made" and "this is where the answer came from"
 * are different claims and should not look alike.
 */
export type TickKind = FactKind | "evidence";

export interface TimelineTick {
  id: string;
  kind: TickKind;
  /** 0–1, position within the meeting. `start_ms / duration_ms`. */
  offset: number;
  label: string;
  detail: string;
  /** Citation marker, when this tick is evidence behind a numbered claim. */
  marker?: number;
}

export interface TimelineBand {
  meetingId: string;
  title: string;
  date: string;
  durationMs: number;
  /** Share of the widest meeting, so band widths stay proportional to real time. */
  widthShare: number;
  ticks: TimelineTick[];
}
