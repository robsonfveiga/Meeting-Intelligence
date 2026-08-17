import { useState } from "react";
import { formatClock, formatDate } from "../hooks/useTimeline";
import type { Meeting } from "../models/transcript";
import styles from "./CorpusList.module.css";

interface Props {
  meetings: Meeting[];
  onRemove: (id: string) => Promise<void>;
}

/**
 * What is in the corpus, and how to take something out of it.
 *
 * It sits under the drop zone because adding and removing are the same job seen
 * from both ends — the reason anyone deletes here is that they just uploaded the
 * wrong file, and making them go looking for the undo in another view would be
 * unkind at exactly the wrong moment.
 *
 * **Confirmation is inline, not a dialog.** `window.confirm` blocks the whole
 * page, reads as a browser artefact rather than part of the product, and cannot
 * say what is actually about to be lost. Turning the row itself into the question
 * keeps the meeting being deleted visible while the question is being answered,
 * which is the one thing a modal cannot do.
 */
export function CorpusList({ meetings, onRemove }: Props) {
  /** The row currently asking, the row currently deleting, and the last failure. */
  const [asking, setAsking] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function confirm(meeting: Meeting & { id: string }) {
    setRemoving(meeting.id);
    setFailure(null);
    try {
      await onRemove(meeting.id);
      setAsking(null);
    } catch (error) {
      setFailure(
        error instanceof Error
          ? `${meeting.title} was not deleted: ${error.message}`
          : `${meeting.title} was not deleted.`,
      );
    } finally {
      setRemoving(null);
    }
  }

  // Same narrowing as the timeline: `id` is optional in the generated schema
  // because the model defaults it, and a meeting that cannot be keyed cannot be
  // deleted by identifier either.
  const listed = meetings.filter(
    (meeting): meeting is Meeting & { id: string } => typeof meeting.id === "string",
  );

  if (!listed.length) {
    return (
      <section className={styles.corpus} aria-label="The corpus">
        <h3 className={styles.heading}>Nothing ingested yet</h3>
        <p className={styles.empty}>
          Meetings appear here once they have been through the pipeline, with a control to remove
          any of them again.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.corpus} aria-label="The corpus">
      <header className={styles.head}>
        <h3 className={styles.heading}>In the corpus</h3>
        <span className={styles.tally}>
          {listed.length} {listed.length === 1 ? "meeting" : "meetings"}
        </span>
      </header>

      {failure && (
        <p className={styles.failure} role="alert">
          {failure}
        </p>
      )}

      <ul className={styles.rows}>
        {listed.map((meeting) => {
          const busy = removing === meeting.id;
          const confirming = asking === meeting.id;

          return (
            <li key={meeting.id} className={`${styles.row} ${confirming ? styles.confirming : ""}`}>
              <span className={styles.date}>{formatDate(meeting.occurred_at)}</span>

              <span className={styles.detail}>
                <b className={styles.title}>{meeting.title}</b>
                <span className={styles.meta}>
                  {/* Optional in the generated schema because the model defaults
                      it, and empty whenever attribution was disabled. */}
                  {meeting.participants?.length ? (
                    <span>{meeting.participants.join(", ")}</span>
                  ) : null}
                  {meeting.duration_ms ? <span>{formatClock(meeting.duration_ms)}</span> : null}
                  <span className={styles.filename}>{meeting.source_filename}</span>
                </span>
              </span>

              {confirming ? (
                <span className={styles.question}>
                  {/*
                   * The consequence is spelled out rather than implied. Deleting a
                   * meeting also removes its extracted facts and everything
                   * retrieval can reach in it, which is more than the word
                   * "delete" on its own conveys.
                   */}
                  <span className={styles.warning}>
                    Removes its transcript, excerpts and extracted facts. Not reversible.
                  </span>
                  <button
                    type="button"
                    className={styles.destroy}
                    disabled={busy}
                    onClick={() => void confirm(meeting)}
                  >
                    {busy ? "Deleting" : "Delete"}
                  </button>
                  <button
                    type="button"
                    className={styles.cancel}
                    disabled={busy}
                    onClick={() => setAsking(null)}
                  >
                    Keep
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className={styles.remove}
                  aria-label={`Remove ${meeting.title}`}
                  onClick={() => {
                    setFailure(null);
                    setAsking(meeting.id);
                  }}
                >
                  Remove
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
