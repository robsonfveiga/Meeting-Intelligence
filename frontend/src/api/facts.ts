import type { Fact, FactKind } from "../models/fact";
import { request } from "./client";

export interface FactQuery {
  kind?: FactKind;
  owner?: string;
  meetingId?: string;
}

export async function listFacts(query: FactQuery = {}): Promise<Fact[]> {
  const params = new URLSearchParams();
  if (query.kind) params.set("kind", query.kind);
  if (query.owner) params.set("owner", query.owner);
  if (query.meetingId) params.set("meeting_id", query.meetingId);

  const suffix = params.size ? `?${params}` : "";
  return request<Fact[]>(`/facts${suffix}`);
}
