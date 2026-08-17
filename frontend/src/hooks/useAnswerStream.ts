import { useCallback, useRef, useState } from "react";
import { streamAnswer } from "../api/chat";
import { ApiError } from "../api/client";
import type { AnswerCitation, AnswerTrace, ScoredChunk } from "../models/answer";

/**
 * `retrieving` is a real state, not a loading spinner in disguise. The backend
 * sends excerpts before the first token exists, so there is a genuine moment
 * where the evidence is known and the answer is not — and that moment is worth
 * showing, because it is the difference between a system that retrieves and one
 * that just talks.
 */
export type AskStatus = "idle" | "retrieving" | "streaming" | "done" | "error";

export interface AnswerState {
  status: AskStatus;
  question: string;
  text: string;
  excerpts: ScoredChunk[];
  citations: AnswerCitation[];
  trace: AnswerTrace | null;
  /** Retrieval found nothing usable, so no model was called at all. Not an error. */
  refused: boolean;
  error: string | null;
}

const EMPTY: AnswerState = {
  status: "idle",
  question: "",
  text: "",
  excerpts: [],
  citations: [],
  trace: null,
  refused: false,
  error: null,
};

export function useAnswerStream() {
  const [state, setState] = useState<AnswerState>(EMPTY);
  const abort = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abort.current?.abort();
    setState(EMPTY);
  }, []);

  const ask = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) return;

    // A second question abandons the first rather than interleaving with it.
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;

    setState({ ...EMPTY, status: "retrieving", question: trimmed });

    try {
      for await (const event of streamAnswer({ question: trimmed }, controller.signal)) {
        if (controller.signal.aborted) return;

        switch (event.type) {
          case "excerpts":
            setState((s) => ({ ...s, excerpts: event.excerpts }));
            break;
          case "token":
            setState((s) => ({ ...s, status: "streaming", text: s.text + event.text }));
            break;
          case "done":
            setState((s) => ({
              ...s,
              status: "done",
              citations: event.citations,
              trace: event.trace,
              refused: event.refused,
            }));
            break;
          case "error":
            setState((s) => ({ ...s, status: "error", error: event.message }));
            break;
        }
      }
    } catch (cause) {
      if (controller.signal.aborted) return;
      // A 503 here means no API key is configured. The message the backend sends
      // says so and says what still works, so it is shown verbatim.
      const message =
        cause instanceof ApiError
          ? cause.message
          : "The answer stream stopped unexpectedly. Check that the API is running.";
      setState((s) => ({ ...s, status: "error", error: message }));
    }
  }, []);

  return { ...state, ask, reset };
}
