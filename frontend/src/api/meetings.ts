import type { UploadAccepted } from "../models/ingestion";
import type { Meeting } from "../models/transcript";
import { ApiError, BASE, remove, request } from "./client";

export async function listMeetings(): Promise<Meeting[]> {
  return request<Meeting[]>("/meetings");
}

/** Takes the meeting, its turns, its chunks and its extracted facts with it. */
export async function deleteMeeting(id: string): Promise<void> {
  return remove(`/meetings/${id}`);
}

/**
 * Multipart, so it bypasses the JSON helper: setting Content-Type by hand on a
 * FormData body omits the boundary and the request fails server-side.
 */
export async function uploadTranscript(file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${BASE}/meetings`, { method: "POST", body: form });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(body.detail ?? `Upload failed (${response.status})`, response.status);
  }
  return (await response.json()) as UploadAccepted;
}

export type { Meeting, UploadAccepted };
