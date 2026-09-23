import type { ChunkRef, DraftResponse, EvidenceRef, ReplySegment } from "@/lib/api/librarian";

/**
 * What the Librarian page keeps in this browser (LIB-2, decision #527).
 *
 * The server stays stateless (decision #519); the conversation is a per-viewer
 * convenience kept in localStorage so leaving the page and coming back does not
 * discard it. WALK-1 finding 1: four paid turns and a draft vanished on one
 * route change. Keyed per user so a shared browser never shows another
 * account's conversation. Every read and write is wrapped: a blocked store
 * degrades to the pre-LIB-2 behaviour instead of breaking the page.
 */

export type Turn =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      segments: ReplySegment[];
      evidence: EvidenceRef[];
      suggested: boolean;
      /** An answer turn's cited chunks and refusal flag (QA-1); absent on turns stored before it. */
      chunks?: ChunkRef[];
      noEvidence?: boolean;
    };

export interface StoredLibrarianState {
  projectId: string;
  turns: Turn[];
  draft: DraftResponse | null;
}

export const librarianStateKey = (userId?: string | null) => `tracelab.librarian.v1:${userId || "guest"}`;
export const orientationKey = (userId?: string | null) => `tracelab.librarian.orientation.v1:${userId || "guest"}`;

function isTurn(value: unknown): value is Turn {
  if (!value || typeof value !== "object") return false;
  const turn = value as { role?: unknown; text?: unknown; segments?: unknown };
  if (turn.role === "user") return typeof turn.text === "string";
  if (turn.role === "assistant") return Array.isArray(turn.segments);
  return false;
}

export function readLibrarianState(userId?: string | null): StoredLibrarianState | null {
  try {
    const raw = window.localStorage.getItem(librarianStateKey(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredLibrarianState>;
    if (!Array.isArray(parsed.turns) || !parsed.turns.every(isTurn)) return null;
    return {
      projectId: typeof parsed.projectId === "string" ? parsed.projectId : "",
      turns: parsed.turns,
      draft: parsed.draft && typeof parsed.draft === "object" && "draft" in parsed.draft ? parsed.draft : null,
    };
  } catch {
    return null;
  }
}

export function writeLibrarianState(userId: string | null | undefined, state: StoredLibrarianState) {
  try {
    if (state.turns.length === 0 && !state.draft) {
      window.localStorage.removeItem(librarianStateKey(userId));
    } else {
      window.localStorage.setItem(librarianStateKey(userId), JSON.stringify(state));
    }
  } catch {
    // Storage disabled: the conversation lives for this page view only, as before.
  }
}

export function clearLibrarianState(userId?: string | null) {
  try {
    window.localStorage.removeItem(librarianStateKey(userId));
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}

/** Derek's "dont show me this anymore": one preference hides the step strip and the mission-page notice. */
export function readOrientationDismissed(userId?: string | null): boolean {
  try {
    return window.localStorage.getItem(orientationKey(userId)) === "dismissed";
  } catch {
    return false;
  }
}

export function writeOrientationDismissed(userId?: string | null) {
  try {
    window.localStorage.setItem(orientationKey(userId), "dismissed");
  } catch {
    // Without storage the dismissal lasts for this page view only.
  }
}
