import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { profileApi } from "@/lib/api/settings";
import type { Role } from "@/types/auth";

/**
 * The caller's role, resolved from a live GET /auth/me — the ONLY channel by
 * which the client learns its role (decision #313; role is never in the JWT,
 * TokenUser, or StoredAuth, so a server-side demote/disable takes effect on the
 * next request with no token staleness).
 *
 * One fetch, provider-level: T48.2/T48.3 consume this via useRole() rather than
 * each re-fetching /auth/me. Every state but "ready"-with-an-admin-role is a
 * DENY for RequireAdmin — the resolution is fail-closed by construction.
 */
export type RoleStatus = "idle" | "loading" | "ready" | "error";

type RoleContextValue = {
  /** Live role, or null until resolved / on any failure. */
  role: Role | null;
  status: RoleStatus;
  /** True ONLY when the role resolved cleanly to an admin-tier role. */
  isAdmin: boolean;
  /**
   * Re-run the live /auth/me role resolution. Surfaced so a transient failure
   * (status "error") can be retried in-app instead of locking a legitimate admin
   * out of the admin pages until a full reload (decision #315b). No-op without a
   * live session.
   */
  refetch: () => void;
};

/**
 * Admin gate: owner is cumulative over admin (owner ⊇ admin). "service",
 * "member", and "viewer" are NOT admins. Anything unrecognized is denied —
 * the gate is an allowlist, not a denylist.
 */
export function isAdminRole(role: Role | null | undefined): boolean {
  return role === "admin" || role === "owner";
}

const RoleContext = createContext<RoleContextValue | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const { isReady, isAuthenticated, user } = useAuth();

  // The identity the role belongs to: the user_id while signed in, else null.
  // We key the reset + re-fetch on THIS, not on the isAuthenticated boolean,
  // so an IN-PLACE session swap — login()/refresh() replacing the token without
  // it ever going falsy — still forces a reset and re-fetch. Keying on the
  // boolean alone would silently serve user A's role to user B (a fail-open
  // flash, decision #285). The id carries no role data, so this respects
  // "role never travels in the token" (decisions #226/#313).
  const sessionKey = isAuthenticated ? user?.user_id ?? "" : null;

  const [role, setRole] = useState<Role | null>(null);
  const [status, setStatus] = useState<RoleStatus>(sessionKey === null ? "idle" : "loading");
  // Bumped by refetch() to re-trigger the resolving effect after a transient error.
  const [retryNonce, setRetryNonce] = useState(0);

  // Reset DURING RENDER (React's sanctioned "reset state on input change"
  // pattern), not in an effect, so children never observe a stale privileged
  // role for even one commit across logout, login, OR a user switch. On a live
  // session we drop straight to "loading"; the effect below resolves it.
  const [prevSessionKey, setPrevSessionKey] = useState(sessionKey);
  if (prevSessionKey !== sessionKey) {
    setPrevSessionKey(sessionKey);
    setRole(null);
    setStatus(sessionKey === null ? "idle" : "loading");
  }

  // Re-run resolution after a transient error. setStatus here runs in an event
  // handler (not an effect body), so it does not trip react-hooks/set-state-in-effect.
  const refetch = useCallback(() => {
    if (sessionKey === null) {
      return;
    }
    setStatus("loading");
    setRetryNonce((nonce) => nonce + 1);
  }, [sessionKey]);

  useEffect(() => {
    // Resolve the role once auth has hydrated and a session is present. State
    // is set ONLY in the async continuations (never synchronously in the effect
    // body), and every failure path is fail-closed. retryNonce re-triggers this
    // on an in-app refetch().
    if (!isReady || sessionKey === null) {
      return;
    }
    let cancelled = false;
    profileApi
      .get()
      .then((profile) => {
        if (cancelled) {
          return;
        }
        setRole(profile.role ?? null);
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        // A 401/403/network error must never leave a stale or assumed-privileged
        // role behind.
        setRole(null);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [isReady, sessionKey, retryNonce]);

  const value = useMemo<RoleContextValue>(
    () => ({
      role,
      status,
      isAdmin: status === "ready" && isAdminRole(role),
      refetch,
    }),
    [role, status, refetch],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error("useRole must be used within a RoleProvider");
  }
  return context;
}
