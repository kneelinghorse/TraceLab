import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { getStoredAuth, setStoredAuth } from "@/lib/auth/storage";
import { apiRequest, AUTH_EXPIRED_EVENT } from "./http";
import { documentsApi } from "./documents";
import { reportsApi } from "./reports";
import { collectionsApi } from "./collections";

const session = { token: "test-current-session", user_id: "member", email: "member@example.test", display_name: "Member" };
beforeEach(() => { localStorage.clear(); setStoredAuth(session); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("rejected sessions", () => {
  it.each([
    [401, '{"detail":"Expired"}', false, true],
    [401, '<html>Unauthorized</html>', false, true],
    [403, '{"detail":"Account is disabled"}', false, true],
    [403, '{"detail":"Project access denied"}', false, false],
    [403, 'Account is disabled', false, false],
    [403, '{broken json', false, false],
    [403, '{"detail":{"message":"Account is disabled"}}', false, false],
    [500, '{"detail":"Account is disabled"}', false, false],
    [403, '{"detail":"Account is disabled"}', true, false],
    [401, '', true, false],
  ])("status %s body %s skipAuth=%s expires=%s", async (status, body, skipAuth, expires) => {
    const response = new Response(body, { status });
    const read = vi.spyOn(response, "text");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const event = vi.fn(); window.addEventListener(AUTH_EXPIRED_EVENT, event);
    try {
      await expect(apiRequest("/fixture", { skipAuth })).rejects.toMatchObject({ status });
      expect(read).toHaveBeenCalledOnce();
      expect(getStoredAuth()).toEqual(expires ? null : session);
      expect(event).toHaveBeenCalledTimes(expires ? 1 : 0);
    } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, event); }
  });

  it("preserves a session after network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Network unavailable")));
    await expect(apiRequest("/fixture")).rejects.toThrow("Network unavailable");
    expect(getStoredAuth()).toEqual(session);
  });

  it("does not expire a new account for an older request's rejection", async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(resolve => { finish = resolve; })));
    const pending = apiRequest("/fixture");
    const current = { ...session, token: "test-new-session", user_id: "new-member" };
    setStoredAuth(current);
    finish(new Response('{"detail":"Account is disabled"}', { status: 403 }));
    await expect(pending).rejects.toMatchObject({ status: 403 });
    expect(getStoredAuth()).toEqual(current);
  });

  it("clears persistent and in-memory identity, removing signed-in user content", async () => {
    function Probe() {
      const { user, token, isAuthenticated } = useAuth();
      return <p>{isAuthenticated ? `Private workspace for ${user?.email}: ${token}` : "Signed out"}</p>;
    }
    render(<AuthProvider><Probe /></AuthProvider>);
    expect(screen.getByText(/Private workspace/)).toBeTruthy();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"detail":"Account is disabled"}', { status: 403 })));
    await act(async () => { await expect(apiRequest("/fixture")).rejects.toMatchObject({ status: 403 }); });
    expect(screen.getByText("Signed out")).toBeTruthy();
    expect(screen.queryByText(/Private workspace/)).toBeNull();
    expect(getStoredAuth()).toBeNull();
  });

  it.each([
    ["document", () => documentsApi.downloadDocument("document")],
    ["report", () => reportsApi.exportReport("report")],
    ["collection", () => collectionsApi.exportMarkdown("collection")],
  ])("uses the same disabled-session boundary for %s downloads", async (_name, download) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response('{"detail":"Project access denied"}', { status: 403 })).mockResolvedValueOnce(new Response('{"detail":"Account is disabled"}', { status: 403 })));
    await expect(download()).rejects.toThrow();
    expect(getStoredAuth()).toEqual(session);
    await expect(download()).rejects.toThrow();
    expect(getStoredAuth()).toBeNull();
  });
});
