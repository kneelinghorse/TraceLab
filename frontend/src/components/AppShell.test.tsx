import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { isAuthenticated: true, isReady: true, user: { user_id: "alice", display_name: "Alice", email: "alice@example.test" }, logout: vi.fn() },
  role: { isAdmin: false },
  router: { pathname: "/missions/[id]", push: vi.fn() },
  activity: { mission: 0, evidence: 0, report: 0 },
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/contexts/RoleContext", () => ({ useRole: () => mocks.role }));
vi.mock("@/lib/api/navigation", () => ({ navigationApi: { search: async () => ({ groups: [] }) } }));
vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { list: async () => ({ items: [] }) } }));
vi.mock("@/lib/api/activity", async original => ({ ...await original<object>(), activityApi: { summary: async () => ({ generated_at: "2026-09-13T00:00:00", new_total: mocks.activity.mission + mocks.activity.evidence + mocks.activity.report, by_type: { ...mocks.activity } }), markViewed: async () => ({ viewed: 0, new_total: 0 }) } }));
vi.mock("@/components/LoginPanel", () => ({ LoginPanel: () => <p>Sign in form</p> }));
vi.mock("@/components/RegisterPanel", () => ({ RegisterPanel: () => <p>Registration form</p> }));

import { SWRConfig } from "swr";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { openCommandPalette } from "@/lib/command-palette";
import migrations from "@/lib/route-migrations.json";

beforeEach(() => {
  localStorage.clear();
  mocks.auth.isAuthenticated = true;
  mocks.role.isAdmin = false;
  mocks.activity.mission = 0; mocks.activity.evidence = 0; mocks.activity.report = 0;
  mocks.router.push.mockReset();
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
});
const fresh = { provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false };
function shell() { return render(<SWRConfig value={fresh}><ThemeProvider><AppShell><h1>Queue work</h1></AppShell></ThemeProvider></SWRConfig>); }

describe("the shared shell", () => {
  it("opens focused search from the Home entry point", () => {
    shell();
    act(openCommandPalette);
    expect(screen.getByRole("dialog", { name: "Search and navigation" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Search research or find a section" }));
  });
  it("provides one main and banner, and marks only the deepest navigation route current", () => {
    shell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).queryByRole("link", { name: "Queue" })).toBeNull();
    expect(within(nav).getByRole("link", { name: "Missions", exact: true }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main-content");
    expect(screen.getByRole("link", { name: "Saved searches" })).toBeTruthy();
    expect(within(nav).getByRole("link", { name: "Relationships" }).getAttribute("href")).toBe("/graph");
    // A retired or redirecting alias (such as /search since QA-2) is never a navigation target.
    const aliases = migrations.filter((row) => row.kind !== "page").map((row) => row.source);
    expect(within(nav).getAllByRole("link").map((link) => link.getAttribute("href")).filter((href) => aliases.includes(href ?? ""))).toEqual([]);
  });

  it("shows new-item counts on the Missions, Evidence and Reports entries in the sidebar and the drawer, hidden at zero", async () => {
    mocks.activity.mission = 2; mocks.activity.evidence = 1;
    shell();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect((await within(nav).findByRole("link", { name: "Missions, 2 new" })).getAttribute("href")).toBe("/missions");
    expect(within(nav).getByRole("link", { name: "Evidence, 1 new" }).getAttribute("href")).toBe("/evidence");
    expect(within(nav).getByRole("link", { name: "Reports", exact: true })).toBeTruthy();
    expect(within(screen.getByRole("banner")).queryByRole("link", { name: /Inbox/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(within(screen.getByRole("dialog", { name: "Navigation" })).getByRole("link", { name: "Missions, 2 new" })).toBeTruthy();
    expect(screen.getAllByTestId("new-count").map((badge) => badge.textContent)).toEqual(["1", "2", "1", "2"]);
    expect(within(nav).queryByRole("link", { name: "Inbox", exact: true })).toBeNull();
  });

  it("keeps admin destinations out of both navigation and command search for non-admins", () => {
    const view = shell();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Search and navigation" });
    expect(within(dialog).queryByRole("button", { name: "Users" })).toBeNull();
    mocks.role.isAdmin = true;
    view.rerender(<SWRConfig value={fresh}><ThemeProvider><AppShell><h1>Queue work</h1></AppShell></ThemeProvider></SWRConfig>);
    expect(screen.getByRole("link", { name: "Users" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Users" })).toBeTruthy();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }])("opens focused keyboard search and submits an encoded research query (%j)", (modifier) => {
    shell();
    fireEvent.keyDown(window, { key: "k", ...modifier });
    const input = screen.getByRole("textbox", { name: "Search research or find a section" });
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "evidence & citations" } });
    fireEvent.submit(input.closest("form")!);
    expect(mocks.router.push).toHaveBeenCalledWith("/librarian?q=evidence%20%26%20citations");
    expect(screen.queryByRole("dialog", { name: "Search and navigation" })).toBeNull();
  });

  it("jumps to a section and restores drawer state on close", () => {
    shell();
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getByRole("button", { name: "Open navigation" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.getByRole("button", { name: "Open navigation" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Search and navigation" })).getByRole("button", { name: "Evidence" }));
    expect(mocks.router.push).toHaveBeenCalledWith("/evidence");
  });

  it("keeps login in the same themed landmark shell without exposing workspace controls", () => {
    mocks.auth.isAuthenticated = false;
    shell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getByText("Sign in form")).toBeTruthy();
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Color theme" })).toBeTruthy();
  });
});
