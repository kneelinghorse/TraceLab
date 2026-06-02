/**
 * Extract a human-readable message from an error thrown by the httpClient.
 *
 * apiRequest() (http.ts) throws `new Error(responseBodyText)`, so for a FastAPI
 * error the message is the raw JSON body — `{"detail":"Email already registered"}`
 * for an HTTPException, or `{"detail":[{...,"msg":"..."}]}` for a 422 validation
 * error. Surface the clean message instead of the raw JSON.
 */
export function apiErrorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (!(err instanceof Error) || !err.message) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    const detail = parsed?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      // FastAPI/Pydantic 422: a list of {loc, msg, type}.
      const messages = detail
        .map((d) => (d && typeof d === "object" ? (d as { msg?: string }).msg : undefined))
        .filter((m): m is string => Boolean(m));
      if (messages.length) {
        return messages.join("; ");
      }
    }
  } catch {
    // Not JSON — fall through to the raw message.
  }
  return err.message;
}
