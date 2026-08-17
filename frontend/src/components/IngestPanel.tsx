import { useRef, useState } from "react";
import { useIngestJob } from "../hooks/useIngestJob";
import { PIPELINE } from "../models/ingestion";
import styles from "./IngestPanel.module.css";

interface Props {
  onIngested: () => void;
}

function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

/**
 * Ingest, with the pipeline visible while it runs.
 *
 * Seven stages, filling in with the durations, token counts and costs the job
 * endpoint actually reports — not a progress bar standing in for work nobody can
 * see. The stages are a real sequence, so numbering them is information rather
 * than ornament.
 */
export function IngestPanel({ onIngested }: Props) {
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const { job, uploading, error, ingest } = useIngestJob(onIngested);

  const stats = job?.stats ?? {};
  // Optional in the schema because the field has a default, so it is narrowed once here.
  const notes = job?.errors ?? [];
  const failed = job?.stage === "failed";
  const finished = job?.stage === "done";

  function take(files: FileList | null) {
    const file = files?.[0];
    if (file) void ingest(file);
  }

  return (
    <section className={styles.ingest} aria-label="Ingest a transcript">
      <div
        className={`${styles.drop} ${dragging ? styles.dragging : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          take(event.dataTransfer.files);
        }}
      >
        <h2 className={styles.title}>Add a meeting</h2>
        <p className={styles.blurb}>
          Drop a WebVTT transcript here. In Teams that is <b>Download → .vtt</b> on the meeting
          transcript; Zoom and most transcription tools export it too.
        </p>
        <button type="button" className={styles.choose} onClick={() => picker.current?.click()}>
          {uploading ? "Uploading" : "Choose a file"}
        </button>
        <input
          ref={picker}
          type="file"
          accept=".vtt,text/vtt"
          className={styles.hidden}
          onChange={(event) => take(event.target.files)}
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {job && (
        <div className={styles.pipeline}>
          <header className={styles.pipelineHead}>
            <span className={styles.file}>{job.filename}</span>
            <span className={`${styles.stage} ${failed ? styles.failedTag : ""}`}>
              {job.stage}
            </span>
            {finished && (
              <span className={styles.summary}>
                {job.turn_count} turns · {job.chunk_count} chunks · {job.fact_count} facts ·{" "}
                {ms(job.total_duration_ms)}
              </span>
            )}
          </header>

          <ol className={styles.stages}>
            {PIPELINE.map((step, index) => {
              const measured = stats[step.stage];
              const state = measured ? styles.doneStep : styles.pendingStep;

              return (
                <li key={step.stage} className={`${styles.step} ${state}`}>
                  <span className={styles.index}>{String(index + 1).padStart(2, "0")}</span>
                  <span className={styles.label}>{step.label}</span>
                  <span className={styles.stepBlurb}>{step.blurb}</span>
                  <span className={styles.numbers}>
                    {measured ? (
                      <>
                        <b>{ms(measured.duration_ms)}</b>
                        {measured.items_out > 0 && <span>{measured.items_out} out</span>}
                        {measured.tokens > 0 && <span>{measured.tokens} tok</span>}
                      </>
                    ) : (
                      <span className={styles.waiting}>waiting</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>

          {notes.length > 0 && (
            <ul className={styles.notes}>
              {notes.map((note, index) => (
                <li key={index} className={note.recoverable ? styles.warn : styles.fail}>
                  <b>{note.stage}</b> {note.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
