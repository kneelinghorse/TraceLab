import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { isAdminRole, useRole } from "@/contexts/RoleContext";

type RequireAdminProps = {
  children: ReactNode;
  /** Optional custom denial UI; defaults to an inline "access denied" panel. */
  fallback?: ReactNode;
};

/**
 * Authorization guard for admin-only surfaces (the T48.2/T48.3 admin pages).
 *
 * FAIL-CLOSED, mirroring the backend's deny-by-default: children render ONLY
 * when the caller's role has resolved cleanly to admin/owner. Every other
 * state — auth still hydrating, role still loading, not signed in, the
 * /auth/me lookup errored, or a non-admin role (member/viewer/service) —
 * denies, so the admin UI never flashes before the role is known
 * (a half-gated UI is a vuln, decision #285).
 *
 * This is UX only. The server's require_admin/authorize() dependency is the
 * real boundary (admin APIs still 403 server-side); this just avoids rendering
 * controls the caller cannot use.
 */
export function RequireAdmin({ children, fallback }: RequireAdminProps) {
  const { isReady, isAuthenticated } = useAuth();
  const { status, role, refetch } = useRole();

  // Still resolving: auth not hydrated, or an authenticated caller's role is
  // mid-fetch. Render a neutral placeholder — never the children.
  if (!isReady || (isAuthenticated && (status === "idle" || status === "loading"))) {
    return (
      <main className="min-h-screen grid place-items-center bg-[hsl(var(--background))] text-slate-300">
        Checking permissions…
      </main>
    );
  }

  // Transient resolution failure for an authenticated caller: still fail-closed
  // (children never render), but offer an in-app retry so a flaky /auth/me does
  // not lock a legitimate admin out for the whole session (decision #315b).
  if (isAuthenticated && status === "error") {
    if (fallback !== undefined) {
      return <>{fallback}</>;
    }
    return (
      <main className="min-h-screen grid place-items-center bg-[hsl(var(--background))] px-4">
        <div className="max-w-md text-center">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Couldn’t verify access</p>
          <h1 className="mt-2 text-lg font-semibold text-white">Permission check failed</h1>
          <p className="mt-2 text-sm text-slate-400">
            A network or server error stopped us from confirming your access. Your session is
            still active — try again.
          </p>
          <button
            type="button"
            onClick={refetch}
            className="mt-4 rounded-md border border-slate-600 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  // Definitive deny: not signed in, or the role resolved to a non-admin tier.
  if (!isAuthenticated || !isAdminRole(role)) {
    if (fallback !== undefined) {
      return <>{fallback}</>;
    }
    return (
      <main className="min-h-screen grid place-items-center bg-[hsl(var(--background))] px-4">
        <div className="max-w-md text-center">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">403 — Forbidden</p>
          <h1 className="mt-2 text-lg font-semibold text-white">Admin access required</h1>
          <p className="mt-2 text-sm text-slate-400">
            Your account does not have permission to view this page.
          </p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
