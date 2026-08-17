import type { TimelineBand, TimelineTick } from "../models/timeline";
import { formatClock } from "../hooks/useTimeline";
import { MarkTooltip } from "./MarkTooltip";
import styles from "./CorpusTimeline.module.css";

/**
 * The corpus, as time.
 *
 * One band per meeting, laid out in the order they happened and sized in
 * proportion to how long each actually ran — so a seventy-second stand-up and a
 * three-minute retro do not pretend to be the same thing.
 *
 * Two layers sit on each band. Underneath, every extracted decision, commitment
 * and open thread at the second it was said. On top, the excerpts the current
 * answer was built from. Ask "was the pricing decision revisited?" and three
 * marks light up across three different weeks — which is the claim this whole
 * system makes, shown rather than described.
 */

interface Props {
  bands: TimelineBand[];
  /** Tick currently under the cursor or keyboard focus, shared with the answer. */
  focused: string | null;
  onFocus: (id: string | null) => void;
  /** Dimmed while an answer is being assembled, so the marks that light up read. */
  dimmed: boolean;
  loading: boolean;
}

const KIND_NAME: Record<string, string> = {
  decision: "Decision",
  commitment: "Commitment",
  open_thread: "Open thread",
  evidence: "Evidence",
};

const TONE: Record<string, string> = {
  decision: "var(--decision)",
  commitment: "var(--commitment)",
  open_thread: "var(--open)",
  evidence: "var(--ink)",
};

function Mark({
  band,
  tick,
  index,
  focused,
  onFocus,
}: {
  band: TimelineBand;
  tick: TimelineTick;
  index: number;
  focused: boolean;
  onFocus: (id: string | null) => void;
}) {
  const clock = formatClock(tick.offset * band.durationMs);
  const kind = KIND_NAME[tick.kind] ?? tick.kind;
  const meta = [
    band.title,
    clock,
    tick.kind === "evidence" ? tick.detail : kind,
  ]
    .filter(Boolean)
    .join(" · ");

  const className = [
    styles.tick,
    styles[tick.kind],
    focused ? styles.focused : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <MarkTooltip
      label={tick.label}
      detail={tick.kind === "evidence" ? undefined : tick.detail}
      meta={
        tick.marker !== undefined ? `Evidence ${tick.marker} · ${meta}` : meta
      }
      tone={TONE[tick.kind] ?? "var(--veil-strong)"}
    >
      {(reference) => (
        <button
          {...reference}
          type="button"
          className={className}
          // Position from real time; `--i` drives the stagger when marks land.
          style={{ left: `${tick.offset * 100}%`, ["--i" as string]: index }}
          onMouseEnter={() => onFocus(tick.id)}
          onMouseLeave={() => onFocus(null)}
          onFocus={() => onFocus(tick.id)}
          onBlur={() => onFocus(null)}
          aria-label={`${band.title}, ${clock}, ${kind}: ${tick.label}`}
        >
          {tick.marker !== undefined && (
            <span className={styles.marker}>{tick.marker}</span>
          )}
        </button>
      )}
    </MarkTooltip>
  );
}

export function CorpusTimeline({
  bands,
  focused,
  onFocus,
  dimmed,
  loading,
}: Props) {
  if (loading) {
    return <div className={styles.empty}>Reading the corpus…</div>;
  }

  if (!bands.length) {
    return (
      <div className={styles.empty}>
        <strong>No meetings yet.</strong> Ingest a transcript and this becomes
        the spine of everything — every decision and commitment at the second it
        was said.
      </div>
    );
  }

  return (
    <div className={`${styles.timeline} ${dimmed ? styles.dimmed : ""}`}>
      <div className={styles.rule}>
        <span>the corpus</span>
        <span className={styles.legend}>
          <i className={`${styles.key} ${styles.decision}`} /> decided
          <i className={`${styles.key} ${styles.commitment}`} /> owed
          <i className={`${styles.key} ${styles.open_thread}`} /> open
        </span>
      </div>

      {bands.map((band) => (
        <div key={band.meetingId} className={styles.band}>
          <span className={styles.date}>{band.date}</span>
          <span className={styles.title}>{band.title}</span>

          <div className={styles.trackWrap}>
            <div
              className={styles.track}
              style={{ width: `${band.widthShare * 100}%` }}
            >
              <span className={styles.spine} aria-hidden="true" />
              {band.ticks.map((tick) => (
                <Mark
                  key={tick.id}
                  band={band}
                  tick={tick}
                  index={(tick.marker ?? 1) - 1}
                  focused={focused === tick.id}
                  onFocus={onFocus}
                />
              ))}
            </div>
            <span className={styles.duration}>
              {formatClock(band.durationMs)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
