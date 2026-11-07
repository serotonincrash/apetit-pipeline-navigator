import { ApiError } from "@/api/fetcher";

/** The plain message from a failed request, when the server sent one. */
export function messageOf(error: unknown): string | undefined {
  return error instanceof ApiError ? error.message : undefined;
}

/** A run or step error as people read it. An unexpected error's details stay in the worker log. */
export function runErrorText(error: string): string {
  return error.startsWith("Unexpected ")
    ? "An unexpected error stopped the run. Copy the run id for the data specialist, who finds the details in the worker log."
    : error;
}
