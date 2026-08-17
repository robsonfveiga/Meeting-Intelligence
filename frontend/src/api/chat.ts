import type { AnswerCitation, AnswerTrace, ScoredChunk } from "../models/answer";
import { openStream } from "./client";

/**
 * Server-Sent Events over POST, parsed by hand.
 *
 * `EventSource` cannot be used here. It only issues GET requests, and the
 * question travels in a POST body — so the browser's built-in parser is off the
 * table and the frames have to be read off a `ReadableStream`.
 *
 * The hazard that makes this worth writing carefully: **frames do not arrive
 * whole.** A network chunk can split anywhere, including halfway through a JSON
 * payload or between the `event:` and `data:` lines of one frame. Everything is
 * therefore buffered until a complete `\n\n` terminator is seen, and the
 * remainder is carried into the next read. Parsing each chunk as it arrives
 * looks like it works right up until a long answer straddles a packet boundary.
 */

export type StreamEvent =
  | { type: "excerpts"; excerpts: ScoredChunk[] }
  | { type: "token"; text: string }
  | { type: "done"; citations: AnswerCitation[]; trace: AnswerTrace; refused: boolean }
  | { type: "error"; message: string };

export interface AskRequest {
  question: string;
  meeting_ids?: string[];
  speaker?: string | null;
}

const FRAME_END = /\r?\n\r?\n/;

/** Turns one raw SSE frame into an event, or null if it is not one we handle. */
function parseFrame(frame: string): StreamEvent | null {
  let name = "message";
  const dataLines: string[] = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    // Comment lines (":" keep-alives) and unknown fields are ignored by design.
  }

  if (!dataLines.length) return null;

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return { type: "error", message: "The server sent a frame that could not be read." };
  }

  switch (name) {
    case "excerpts":
      return { type: "excerpts", excerpts: payload as ScoredChunk[] };
    case "token":
      return { type: "token", text: (payload as { text: string }).text };
    case "done": {
      const done = payload as { citations: AnswerCitation[]; trace: AnswerTrace; refused: boolean };
      return { type: "done", ...done };
    }
    case "error":
      return { type: "error", message: (payload as { message: string }).message };
    default:
      return null;
  }
}

/**
 * Yields events in the order the backend produces them: excerpts first — before
 * a single token exists — then the answer token by token, then the verified
 * citations and the trace. That ordering is the product's argument made visible,
 * so the interface should never buffer it into one delivery.
 */
export async function* streamAnswer(
  request: AskRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await openStream("/chat/stream", request);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) return;

      const { done, value } = await reader.read();
      if (done) break;

      // `stream: true` matters: a multi-byte character can also be split across
      // reads, and decoding without it would corrupt the token.
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.search(FRAME_END);
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary).replace(FRAME_END, "");

        const event = parseFrame(frame);
        if (event) yield event;

        boundary = buffer.search(FRAME_END);
      }
    }

    // A final frame with no trailing blank line still counts.
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    reader.cancel().catch(() => {
      // Already closed. Nothing to recover.
    });
  }
}
