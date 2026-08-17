import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { getJob } from "../api/jobs";
import { uploadTranscript } from "../api/meetings";
import type { JobResponse } from "../models/ingestion";
import { TERMINAL_STAGES } from "../models/ingestion";

const POLL_MS = 400;
/**
 * Upload returns as soon as the file is on disk, and the job only becomes
 * readable once the graph writes its first checkpoint — so a 404 in the first
 * moments is the backend being honest, not a failure. Tolerated for a few seconds,
 * after which it really is missing.
 */
const NOT_FOUND_GRACE = 15;
/**
 * A failed read is not a failed ingest. The pipeline runs in the background and
 * does not care whether a poll succeeded, so giving up on the first bad response
 * threw away a job that was still running — the reason this exists is a 500 in
 * the opening milliseconds that ended the poll for an ingest which then completed
 * normally. Retried a few times before the failure is believed, and the count
 * resets on every good read so a long ingest never exhausts it.
 */
const FAILURE_GRACE = 3;

/**
 * Upload a transcript, then follow the job until it settles.
 *
 * Polling rather than a push channel, because the backend exposes job state as a
 * plain read off the graph checkpoint and an ingest finishes in seconds. A socket
 * would be more machinery than the problem has.
 *
 * The poll lives in an effect keyed on the job identifier rather than in a
 * self-recursive callback. That way the loop has exactly one owner, and unmounting
 * mid-ingest cancels it instead of leaving a timer writing into a dead component.
 */
export function useIngestJob(onFinished?: () => void) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Held in a ref so a new callback identity does not restart the poll, and
  // written in an effect because refs must not be touched during render.
  const finished = useRef(onFinished);
  useEffect(() => {
    finished.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    let timer: number | undefined;
    let missing = 0;
    let failures = 0;

    const tick = async () => {
      try {
        const latest = await getJob(jobId);
        if (cancelled) return;

        missing = 0;
        failures = 0;
        setJob(latest);

        if (TERMINAL_STAGES.includes(latest.stage)) {
          finished.current?.();
          return;
        }
        timer = window.setTimeout(() => void tick(), POLL_MS);
      } catch (cause) {
        if (cancelled) return;

        // The job has not checkpointed yet. Keep waiting rather than reporting a
        // failure the user cannot act on.
        if (cause instanceof ApiError && cause.status === 404 && missing < NOT_FOUND_GRACE) {
          missing += 1;
          timer = window.setTimeout(() => void tick(), POLL_MS);
          return;
        }
        if (failures < FAILURE_GRACE) {
          failures += 1;
          timer = window.setTimeout(() => void tick(), POLL_MS);
          return;
        }
        setError("Lost track of the job. The API stopped responding.");
      }
    };

    void tick();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [jobId]);

  const ingest = useCallback(async (file: File) => {
    setError(null);
    setJob(null);
    setJobId(null);
    setUploading(true);

    try {
      const accepted = await uploadTranscript(file);
      setJobId(accepted.job_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }, []);

  return { job, uploading, error, ingest };
}
