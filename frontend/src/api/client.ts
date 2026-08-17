/**
 * The one place that talks to the backend.
 *
 * Named for the job rather than the transport, and deliberately thin: five
 * endpoints and a stream do not need a query library, a cache layer or an
 * interceptor chain. When one of those earns its place it goes here.
 */

/** Same-origin in dev via the Vite proxy; overridable for a deployed build. */
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * FastAPI reports problems as `{"detail": ...}`, where detail is either a string
 * or a list of validation errors. Both are unwrapped here so no caller has to
 * know the shape — an error a person can read is the whole point.
 */
async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  } catch {
    // Not JSON. The status line is all we have.
  }
  return `${response.status} ${response.statusText}`;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return (await response.json()) as T;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

/**
 * Separate from `request` because a 204 carries no body, and asking `json()` for
 * one throws on a response that was in fact a success.
 */
export async function remove(path: string): Promise<void> {
  const response = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
}

/** Opens a stream without consuming it, so the caller can parse it frame by frame. */
export async function openStream(path: string, body: unknown): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  if (!response.body) throw new ApiError("The response carried no stream", 500);
  return response;
}

export { BASE };
