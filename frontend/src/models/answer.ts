import type { components } from "../api/schema";

/**
 * Narrow aliases over the schema generated from the backend's own OpenAPI
 * document. The backend stays the single source of truth, so these cannot drift:
 * regenerate `schema.d.ts` and a changed field becomes a type error here rather
 * than a runtime surprise.
 */
export type Answer = components["schemas"]["Answer"];
export type AnswerCitation = components["schemas"]["AnswerCitation"];
export type AnswerTrace = components["schemas"]["AnswerTrace"];
export type ScoredChunk = components["schemas"]["ScoredChunk"];
