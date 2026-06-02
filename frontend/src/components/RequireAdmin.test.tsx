import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Drive the guard directly off controllable auth/role state so each fail-closed
// branch is exercised deterministically (no async role fetch in these cases).
const mocks = vi.hoisted(() => ({
  auth: { isReady: true, isAuthenticated: true },
  role: { role: null as string | null, status: "loading" as string, refetch: vi.fn() },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mocks.auth,
}));

// Override only useRole; keep the REAL isAdminRole so the guard's admin
// allowlist is validated against production logic, not a test-local copy.
vi.mock("@/contexts/RoleContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/contexts/RoleContext")>();
  return {
    ...actual,
    useRole: () => mocks.role,
  };
});

import { RequireAdmin } from "@/components/RequireAdmin";

const ADMIN_CONTENT = "secret-admin-panel";

function renderGuard(opts: {
  isReady?: boolean;
  isAuthenticated?: boolean;
  status: string;
  role?: string | null;
}) {
  mocks.auth.isReady = opts.isReady ?? true;
  mocks.auth.isAuthenticated = opts.isAuthenticated ?? true;
  mocks.role.status = opts.status;
  mocks.role.role = opts.role ?? null;
  return render(
    <RequireAdmin>
      <div>{ADMIN_CONTENT}</div>
    </RequireAdmin>,
  );
}

beforeEach(() => {
  mocks.role.refetch = vi.fn();
});

describe("RequireAdmin — fail-closed denials", () => {
  it("renders nothing but a placeholder while auth is still hydrating", () => {
    renderGuard({ isReady: false, status: "idle" });
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
    expect(screen.getByText(/Checking permissions/i)).toBeTruthy();
  });

  it("does not flash admin content while the role is still loading", () => {
    renderGuard({ status: "loading" });
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
    expect(screen.getByText(/Checking permissions/i)).toBeTruthy();
  });

  it("denies when the role lookup is idle for an authenticated caller", () => {
    renderGuard({ status: "idle" });
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
  });

  it("denies when not authenticated", () => {
    renderGuard({ isAuthenticated: false, status: "idle" });
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
    expect(screen.getByText(/Admin access required/i)).toBeTruthy();
  });

  it("denies (fail-closed) but offers a Retry when the /auth/me lookup errored", () => {
    renderGuard({ status: "error" });
    // Still fail-closed — children never render on a resolution error...
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
    // ...but the user gets an in-app retry instead of a permanent lockout (#315b).
    expect(screen.getByText(/Permission check failed/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("invokes refetch() when the Retry control is clicked on an errored lookup", () => {
    renderGuard({ status: "error" });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(mocks.role.refetch).toHaveBeenCalledTimes(1);
  });

  it.each(["member", "viewer", "service"])(
    "denies a resolved non-admin role: %s",
    (role) => {
      renderGuard({ status: "ready", role });
      expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
      expect(screen.getByText(/Admin access required/i)).toBeTruthy();
    },
  );

  it("denies an unrecognized role (allowlist, not denylist)", () => {
    renderGuard({ status: "ready", role: "superuser" });
    expect(screen.queryByText(ADMIN_CONTENT)).toBeNull();
  });
});

describe("RequireAdmin — allows admin tier", () => {
  it.each(["admin", "owner"])("renders children for role: %s", (role) => {
    renderGuard({ status: "ready", role });
    expect(screen.getByText(ADMIN_CONTENT)).toBeTruthy();
  });
});
