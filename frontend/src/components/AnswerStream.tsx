import type { ReactNode } from "react";
import type { AnswerCitation } from "../models/answer";
import styles from "./AnswerStream.module.css";

interface Props {
  text: string;
  citations: AnswerCitation[];
  streaming: boolean;
  focused: string | null;
  onFocus: (id: string | null) => void;
}

/**
 * The answer, with its citation markers turned into the same objects the evidence
 * panel and the timeline show.
 *
 * Markers stay inert while tokens are still arriving: the citations they point at
 * only exist once the backend has verified them, and a chip that looked clickable
 * before its evidence was confirmed would claim more than the system knows. A
 * half-typed "[" at the end of the stream stays plain text until the bracket closes.
 *
 * FORMATTING: the model emits light markdown — bold for figures, blank lines
 * between paragraphs, the occasional bullet list — so that subset is rendered
 * rather than shown as literal asterisks. A markdown library is deliberately not
 * used: it would need to be taught not to mangle the citation markers, which is
 * more work than handling three constructs, and anything outside the subset falls
 * through as plain text rather than breaking.
 */

/** Emphasis or a citation marker, whichever comes first. */
const INLINE = /\*\*(.+?)\*\*|\[(\d+)\]/g;
const BULLET = /^\s*[-*]\s+/;

export function AnswerStream({ text, citations, streaming, focused, onFocus }: Props) {
  const byMarker = new Map(citations.map((citation) => [citation.marker, citation]));

  function chip(marker: number, key: string): ReactNode {
    const citation = byMarker.get(marker);
    const id = citation ? `evidence-${citation.chunk_id}` : null;

    return (
      <button
        key={key}
        type="button"
        className={`${styles.chip} ${id && focused === id ? styles.focused : ""}`}
        disabled={!citation}
        onMouseEnter={() => id && onFocus(id)}
        onMouseLeave={() => onFocus(null)}
        onFocus={() => id && onFocus(id)}
        onBlur={() => onFocus(null)}
        aria-label={
          citation
            ? `Evidence ${marker}: ${citation.meeting_title}, ${citation.speakers.join(", ")}`
            : `Evidence ${marker}, not yet verified`
        }
      >
        {marker}
      </button>
    );
  }

  function inline(source: string, keyPrefix: string): ReactNode[] {
    const pieces: ReactNode[] = [];
    let cursor = 0;

    for (const match of source.matchAll(INLINE)) {
      const at = match.index;
      if (at > cursor) pieces.push(source.slice(cursor, at));

      if (match[1] !== undefined) {
        pieces.push(<strong key={`${keyPrefix}-b${at}`}>{match[1]}</strong>);
      } else if (match[2] !== undefined) {
        pieces.push(chip(Number(match[2]), `${keyPrefix}-c${at}`));
      }
      cursor = at + match[0].length;
    }

    if (cursor < source.length) pieces.push(source.slice(cursor));
    return pieces;
  }

  const blocks = text.split(/\n{2,}/).filter((block) => block.trim().length > 0);

  return (
    <div className={styles.answer}>
      {blocks.map((block, index) => {
        const lines = block.split("\n").filter((line) => line.trim().length > 0);
        const isList = lines.length > 0 && lines.every((line) => BULLET.test(line));
        const last = index === blocks.length - 1;

        if (isList) {
          return (
            <ul key={index} className={styles.list}>
              {lines.map((line, item) => (
                <li key={item}>{inline(line.replace(BULLET, ""), `${index}-${item}`)}</li>
              ))}
            </ul>
          );
        }

        return (
          <p key={index}>
            {inline(block, String(index))}
            {streaming && last && <span className={styles.caret} aria-hidden="true" />}
          </p>
        );
      })}
    </div>
  );
}
