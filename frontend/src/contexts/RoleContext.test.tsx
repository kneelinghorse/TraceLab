import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: {
    isReady: true,
    isAuthenticated: true,
    user: { user_id: "u1", email: "a@example.com", display_name: "A" } as
      | { user_id: string; email: string; display_name: string }
      | null,
  },
  getProfile: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => mocks.auth,
}));

vi.mock("@/lib/api/settings", () => ({
  profileApi: { get: mocks.getProfile },
}));

import { RoleProvider, useRole } from "@/contexts/RoleContext";

function Probe() {
  const { role, status, isAdmin } = useRole();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{role ?? "none"}</span>
      <span data-testid="isAdmin">{String(isAdmin)}</span>
    </div>
  );
}

function renderProbe() {
  return render(
    <RoleProvider>
      <Probe />
    </RoleProvider>,
  );
}

beforeEach(() => {
  mocks.auth.isReady = true;
  mocks.auth.isAuthenticated = true;
  mocks.auth.user = { user_id: "u1", email: "a@example.com", display_name: "A" };
  mocks.getProfile.mockReset();
});

describe("RoleProvider", () => {
  it("resolves an admin role from /auth/me", async () => {
    mocks.getProfile.mockResolvedValue({
      user_id: "u1",
      email: "a@example.com",
      display_name: "A",
      role: "admin",
    });
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("ready"));
    expect(screen.getByTestId("role").textContent).toBe("admin");
    expect(screen.getByTestId("isAdmin").textContent).toBe("true");
  });

  it("treats a member as a non-admin", async () => {
    mocks.getProfile.mockResolvedValue({
      user_id: "u2",
      email: "m@example.com",
      display_name: "M",
      role: "member",
    });
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("ready"));
    expect(screen.getByTestId("role").textContent).toBe("member");
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
  });

  it("fails closed when /auth/me rejects (e.g. 403)", async () => {
    mocks.getProfile.mockRejectedValue(new Error("403 Forbidden"));
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("role").textContent).toBe("none");
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
  });

  it("stays idle and does not call /auth/me when unauthenticated", async () => {
    mocks.auth.isAuthenticated = false;
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("idle"));
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
    expect(mocks.getProfile).not.toHaveBeenCalled();
  });

  it("clears a resolved admin role on logout (no stale privileged flash)", async () => {
    mocks.getProfile.mockResolvedValue({
      user_id: "u3",
      email: "a@example.com",
      display_name: "A",
      role: "admin",
    });
    const { rerender } = renderProbe();
    await waitFor(() => expect(screen.getByTestId("isAdmin").textContent).toBe("true"));

    // Session ends.
    mocks.auth.isAuthenticated = false;
    rerender(
      <RoleProvider>
        <Probe />
      </RoleProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("idle"));
    expect(screen.getByTestId("role").textContent).toBe("none");
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
  });

  it("re-resolves on an in-place user switch — never serves A's admin role to B", async () => {
    // user A resolves as admin
    mocks.getProfile.mockResolvedValueOnce({
      user_id: "u1",
      email: "a@example.com",
      display_name: "A",
      role: "admin",
    });
    const { rerender } = renderProbe();
    await waitFor(() => expect(screen.getByTestId("isAdmin").textContent).toBe("true"));

    // The token is replaced in place (a different user) WITHOUT logging out —
    // isAuthenticated never goes false. Keying only on the auth boolean would
    // keep showing A's admin role; keying on user_id forces a re-fetch.
    mocks.auth.user = { user_id: "u2", email: "m@example.com", display_name: "M" };
    mocks.getProfile.mockResolvedValueOnce({
      user_id: "u2",
      email: "m@example.com",
      display_name: "M",
      role: "member",
    });
    rerender(
      <RoleProvider>
        <Probe />
      </RoleProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("member"));
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
    expect(mocks.getProfile).toHaveBeenCalledTimes(2);
  });

  it("drops a prior admin role when the next session's /auth/me errors (fail-closed)", async () => {
    mocks.getProfile.mockResolvedValueOnce({
      user_id: "u1",
      email: "a@example.com",
      display_name: "A",
      role: "admin",
    });
    const { rerender } = renderProbe();
    await waitFor(() => expect(screen.getByTestId("isAdmin").textContent).toBe("true"));

    // A different session whose role lookup fails must NOT inherit A's role.
    mocks.auth.user = { user_id: "u2", email: "m@example.com", display_name: "M" };
    mocks.getProfile.mockRejectedValueOnce(new Error("503 Service Unavailable"));
    rerender(
      <RoleProvider>
        <Probe />
      </RoleProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("role").textContent).toBe("none");
    expect(screen.getByTestId("isAdmin").textContent).toBe("false");
  });
});
