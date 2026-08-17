import type { components } from "../api/schema";

export type JobResponse = components["schemas"]["JobResponse"];
export type Stage = components["schemas"]["Stage"];
export type StageStats = components["schemas"]["StageStats"];
export type UploadAccepted = components["schemas"]["UploadAccepted"];

/**
 * The pipeline in the order the graph runs it, which is also the order the
 * interface fills them in. `received` and `done` are not shown as steps: one is
 * the moment before any work and the other is the absence of remaining work.
 */
export const PIPELINE: readonly { stage: string; label: string; blurb: string }[] = [
  { stage: "validate", label: "Validate", blurb: "Is this really WebVTT?" },
  { stage: "parse", label: "Parse", blurb: "Cues merged into speaker turns" },
  { stage: "chunk", label: "Chunk", blurb: "Turns grouped, never split" },
  { stage: "contextualise", label: "Contextualise", blurb: "Where each chunk sits" },
  { stage: "embed", label: "Embed", blurb: "Vectors, batched" },
  { stage: "extract_facts", label: "Extract", blurb: "Decisions, commitments, threads" },
  { stage: "finalise", label: "Finalise", blurb: "Close the job" },
];

export const TERMINAL_STAGES: readonly string[] = ["done", "failed"];
