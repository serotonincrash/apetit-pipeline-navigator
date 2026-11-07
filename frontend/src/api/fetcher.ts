import { personaHeader } from "./persona";

/** An API failure with the plain message the server sent. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function messageOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // The body was not JSON; fall through to the status text.
  }
  return response.statusText || `The server answered with status ${response.status}.`;
}

/** The mutator the generated client calls for every request. */
export const fetcher = async <T>(url: string, init: RequestInit): Promise<T> => {
  const headers = new Headers(init.headers);
  for (const [name, value] of Object.entries(personaHeader())) headers.set(name, value);
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) throw new ApiError(response.status, await messageOf(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
};
