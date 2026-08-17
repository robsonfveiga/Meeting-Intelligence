import type { AnswerCitation, ScoredChunk } from "../models/answer";
import { formatClock } from "../hooks/useTimeline";
import styles from "./EvidencePanel.module.css";

interface Props {
  excerpts: ScoredChunk[];
  citations: AnswerCitation[];
  focused: string | null;
  onFocus: (id: string | null) => void;
}

/**
 * What the answer was built from, in the order the retriever ranked it.
 *
 * Every excerpt shows the two things that make it checkable: where it came from,
 * and how it was found. `kw 1 · vec 3` is the rank each strategy gave it — a
 * chunk that keyword loved and vectors ignored tells a different story from one
 * both agreed on, and that difference is why the system runs two strategies.
 */
export function EvidencePanel({ excerpts, citations, focused, onFocus }: Props) {
  const markerOf = new Map(citations.map((citation) => [citation.chunk_id, citation.marker]));

  if (!excerpts.length) return null;

  return (
    <section className={styles.panel} aria-label="Evidence">
      <h2 className={styles.heading}>
        Evidence
        <span className={styles.count}>{excerpts.length} excerpts</span>
      </h2>

      <div className={styles.cards}>
        {excerpts.map((hit, position) => {
        const id = `evidence-${hit.chunk_id}`;
        const marker = markerOf.get(hit.chunk_id);

        return (
          <article
            key={hit.chunk_id}
            // `--i` matches the timeline mark's stagger, so a card and its mark
            // arrive together rather than in two separate waves.
            style={{ ["--i" as string]: (marker ?? position + 1) - 1 }}
            className={`${styles.card} ${focused === id ? styles.focused : ""} ${
              marker === undefined ? styles.uncited : ""
            }`}
            onMouseEnter={() => onFocus(id)}
            onMouseLeave={() => onFocus(null)}
          >
            <header className={styles.meta}>
              {marker !== undefined ? (
                <span className={styles.marker}>{marker}</span>
              ) : (
                <span className={styles.unused} title="Retrieved but not cited">
                  ·
                </span>
              )}
              <span className={styles.meeting}>{hit.meeting_title}</span>
              <span className={styles.clock}>{formatClock(hit.time.start_ms)}</span>
            </header>

            <p className={styles.quote}>{hit.text}</p>

            <footer className={styles.foot}>
              <span className={styles.speakers}>{hit.speakers.join(", ")}</span>
              <span className={styles.ranks}>
                {Object.entries(hit.ranks ?? {}).map(([strategy, rank]) => (
                  <span key={strategy}>
                    {strategy === "keyword" ? "kw" : "vec"} {rank}
                  </span>
                ))}
              </span>
            </footer>
            </article>
          );
        })}
      </div>
    </section>
  );
}
