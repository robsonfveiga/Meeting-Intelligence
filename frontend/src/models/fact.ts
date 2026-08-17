import type { components } from "../api/schema";

export type Fact = components["schemas"]["FactResponse"];
export type FactKind = components["schemas"]["FactKind"];

/** Display order, and the order the three hues were chosen in. */
export const FACT_KINDS: readonly FactKind[] = ["decision", "commitment", "open_thread"];

export const KIND_LABEL: Record<FactKind, string> = {
  decision: "Decisions",
  commitment: "Commitments",
  open_thread: "Open threads",
};

/** What each kind actually means, in the words a reader would use. */
export const KIND_BLURB: Record<FactKind, string> = {
  decision: "Questions the room settled",
  commitment: "Work someone took on",
  open_thread: "Raised, and still unanswered",
};
