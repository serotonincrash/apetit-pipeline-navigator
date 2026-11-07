import { ApiError } from "@/api/fetcher";

/** The plain message from a failed request, when the server sent one. */
export function messageOf(error: unknown): string | undefined {
  return error instanceof ApiError ? error.message : undefined;
}
