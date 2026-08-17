import { useMemo, useState } from "react";
import type { Fact, FactKind } from "../models/fact";
import { FACT_KINDS, KIND_BLURB, KIND_LABEL } from "../models/fact";
import { formatClock } from "../hooks/useTimeline";
import styles from "./TheRecord.module.css";

interface Props {
  facts: Fact[];
  focused: string | null;
  onFocus: (id: string | null) => void;
}

/**
 * The record: what was settled, what someone owes, and what is still open.
 *
 * A list rather than a search, because "what did we commit to" is a question
 * about a series of meetings and answering it from stored facts is both cheaper
 * and more complete than answering it from retrieval.
 *
 * Every entry carries the turns it came from. That is the guarantee — a fact
 * cannot be stored unless it pointed at real transcript — so the turn range is
 * shown rather than tucked away.
 */
export function TheRecord({ facts, focused, onFocus }: Props) {
  const [owner, setOwner] = useState<string>("");

  const owners = useMemo(
    () => [...new Set(facts.map((fact) => fact.owner).filter((name): name is string => !!name))].sort(),
    [facts],
  );

  const visible = owner ? facts.filter((fact) => fact.owner === owner) : facts;
  const byKind = (kind: FactKind) => visible.filter((fact) => fact.kind === kind);

  if (!facts.length) {
    return (
      <section className={styles.record}>
        <p className={styles.empty}>
          <strong>Nothing extracted yet.</strong> Ingest a transcript with an API key configured,
          and the decisions, commitments and open threads in it appear here — each one pointing
          back at the turns it came from.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.record} aria-label="The record">
      <div className={styles.bar}>
        <h2 className={styles.title}>The record</h2>
        <div className={styles.filter}>
          <label htmlFor="owner">Owed by</label>
          <select
            id="owner"
            value={owner}
            onChange={(event) => setOwner(event.target.value)}
            className={styles.select}
          >
            <option value="">everyone</option>
            {owners.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={styles.columns}>
        {FACT_KINDS.map((kind) => {
          const entries = byKind(kind);
          return (
            <div key={kind} className={`${styles.column} ${styles[kind]}`}>
              <header className={styles.columnHead}>
                <h3>{KIND_LABEL[kind]}</h3>
                <span className={styles.tally}>{entries.length}</span>
                <p className={styles.blurb}>{KIND_BLURB[kind]}</p>
              </header>

              {entries.length === 0 && <p className={styles.none}>None recorded.</p>}

              {entries.map((fact) => (
                <article
                  key={fact.id}
                  className={`${styles.card} ${focused === fact.id ? styles.focused : ""}`}
                  onMouseEnter={() => onFocus(fact.id)}
                  onMouseLeave={() => onFocus(null)}
                >
                  <p className={styles.statement}>{fact.statement}</p>

                  <footer className={styles.provenance}>
                    <span className={styles.meeting}>{fact.meeting_title}</span>
                    <span className={styles.clock}>{formatClock(fact.time.start_ms)}</span>
                    <span className={styles.turns}>
                      turns {fact.start_turn_index}–{fact.end_turn_index}
                    </span>
                  </footer>

                  {(fact.owner || fact.due) && (
                    <p className={styles.owner}>
                      {fact.owner}
                      {fact.due && <span className={styles.due}>due {fact.due}</span>}
                    </p>
                  )}
                </article>
              ))}
            </div>
          );
        })}
      </div>
    </section>
  );
}
