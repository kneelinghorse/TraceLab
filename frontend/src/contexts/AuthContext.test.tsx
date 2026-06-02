import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// A stored session is present on mount; clearStoredAuth() empties it.
const store = vi.hoisted(() => ({
  value: { token: "t", user_id: "u1", email: "a@example.com", display_name: "A" } as
    | { token: string; user_id: string; email: string; display_name: string }
    | null,
}));

vi.mock("@/lib/auth/storage", () => ({
  getStoredAuth: () => store.value,
  clearStoredAuth: vi.fn(() => {
    store.value = null;
  }),
  setStoredAuth: vi.fn(),
}));

vi.mock("@/lib/api/auth", () => ({
  login: vi.fn(),
  register: vi.fn(),
  refresh: vi.fn(),
}));

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { AUTH_EXPIRED_EVENT } from "@/lib/api/http";

function Probe() {
  const { isAuthenticated } = useAuth();
  return <span data-testid="authed">{String(isAuthenticated)}</span>;
}

beforeEach(() => {
  store.value = { token: "t", user_id: "u1", email: "a@example.com", display_name: "A" };
});

describe("AuthProvider — 401 zombie-auth (#315a)", () => {
  it("drops the in-memory session when a 401 fires AUTH_EXPIRED_EVENT", () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    // Hydrated from the stored token → looks signed in.
    expect(screen.getByTestId("authed").textContent).toBe("true");

    // The http layer cleared storage on a 401 and fired the event; AuthContext must
    // also drop its in-memory token so the app shows login, not a broken shell.
    fireEvent(window, new Event(AUTH_EXPIRED_EVENT));

    expect(screen.getByTestId("authed").textContent).toBe("false");
  });
});
