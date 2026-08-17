import type { JobResponse } from "../models/ingestion";
import { request } from "./client";

export async function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${jobId}`);
}
