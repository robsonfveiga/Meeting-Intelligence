import type { AnswerTrace } from "../models/answer";
import styles from "./BuildTrace.module.css";

interface Props {
  trace: AnswerTrace;
}

function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

/**
 * How this answer was built, from the trace the response already carries.
 *
 * Not a debug panel behind a toggle. If a system asks to be trusted about what a
 * room decided, the cost of that claim — which query actually ran, whether the
 * first attempt failed, how many excerpts were weighed, what it spent — belongs
 * next to the claim.
 *
 * `dropped` is the one to read. It counts markers the model emitted pointing at
 * excerpts that were never supplied, so anything but zero is a grounding failure.
 * It is shown in magenta and named plainly rather than hidden.
 */
export function BuildTrace({ trace }: Props) {
  const dropped = trace.dropped_markers?.length ?? 0;
  const timings = Object.entries(trace.timings_ms ?? {});

  return (
    <section className={styles.trace} aria-label="How this answer was built">
      <h2 className={styles.heading}>How this was built</h2>

      <dl className={styles.grid}>
        <div className={styles.cell}>
          <dt>Query run</dt>
          <dd className={styles.query}>“{trace.search_query}”</dd>
        </div>

        <div className={styles.cell}>
          <dt>Rewritten</dt>
          <dd>{trace.rewritten ? `yes, after ${trace.attempts} attempts` : "no"}</dd>
        </div>

        <div className={styles.cell}>
          <dt>Excerpts weighed</dt>
          <dd>{trace.hits_considered}</dd>
        </div>

        <div className={`${styles.cell} ${dropped ? styles.alarm : ""}`}>
          <dt>Ungrounded markers</dt>
          <dd>{dropped === 0 ? "none" : `${dropped} dropped`}</dd>
        </div>

        <div className={styles.cell}>
          <dt>Tokens</dt>
          <dd>{trace.tokens.toLocaleString()}</dd>
        </div>

        <div className={styles.cell}>
          <dt>Evidence judged</dt>
          <dd>{trace.sufficient ? "sufficient" : "thin, and said so"}</dd>
        </div>
      </dl>

      {timings.length > 0 && (
        <ul className={styles.timings}>
          {timings.map(([stage, value]) => (
            <li key={stage}>
              <span>{stage}</span>
              <b>{ms(value)}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
