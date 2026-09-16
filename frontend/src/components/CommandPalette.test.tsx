import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { isAuthenticated: true, isReady: true, user: { user_id: "alice", display_name: "Alice", email: "alice@example.test" }, logout: vi.fn() },
  role: { isAdmin: false },
  router: { pathname: "/missions", push: vi.fn() },
  names: vi.fn(), history: vi.fn(), saved: vi.fn(),
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/contexts/RoleContext", () => ({ useRole: () => mocks.role }));
vi.mock("@/lib/api/navigation", () => ({ navigationApi: { search: mocks.names } }));
vi.mock("@/lib/api/search", () => ({ searchApi: { history: mocks.history } }));
vi.mock("@/lib/api/activity", async original => ({ ...await original<object>(), activityApi: { summary: async () => ({ generated_at: "2026-09-13T00:00:00", new_total: 0, by_type: {} }) } }));
vi.mock("@/lib/api/savedSearches", () => ({ savedSearchesApi: { list: mocks.saved } }));

import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { openCommandPalette } from "@/lib/command-palette";

const kinds = ["project", "document", "mission", "report", "collection", "evidence"] as const;
function response(query = "Needle") {
  return { query, groups: kinds.map(kind => ({ entity_type: kind, total: 1, page: 1, page_size: 5, items: [{ id: kind, title: `${query} ${kind}`, href: `/${kind === "evidence" ? kind : kind + "s"}/${kind}` }] })) };
}

beforeEach(() => {
  // The palette debounces queries for 200 ms. Drive that timer rather than waiting on it: a
  // default 1 s findBy poll spends its whole budget on one or two name lookups and then fails.
  // Only the timer functions are faked, so SWR's Date/performance use stays real.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  vi.clearAllMocks();
  mocks.auth.user.user_id = "alice";
  mocks.role.isAdmin = false;
  mocks.names.mockResolvedValue(response());
  mocks.history.mockResolvedValue({ entries: [] });
  mocks.saved.mockResolvedValue({ items: [] });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
});
afterEach(() => { vi.useRealTimers(); });

function shell() {
  return <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}><ThemeProvider><AppShell><h1>Existing route</h1></AppShell></ThemeProvider></SWRConfig>;
}
function open() { act(openCommandPalette); return screen.getByRole("textbox", { name: "Search research or find a section" }); }
/** Runs out the 200 ms query debounce and flushes the lookup promises it releases, so every
 *  assertion below reads a settled tree. Deterministic regardless of machine load. */
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(250); }); }

describe("scoped palette data and actions", () => {
  it("queries names only while open and exposes every server-returned entity link", async () => {
    render(shell());
    expect(mocks.names).not.toHaveBeenCalled();
    const input = open();
    expect(mocks.names).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: " Needle " } });
    await settle();
    for (const kind of kinds) expect(screen.getByRole("button", { name: `Needle ${kind}`, exact: true })).toBeTruthy();
    expect(mocks.names).toHaveBeenCalledWith("Needle");
    fireEvent.click(screen.getByRole("button", { name: "Needle evidence", exact: true }));
    expect(mocks.router.push).toHaveBeenCalledWith("/evidence/evidence");
  });

  it("pages a full scoped group and resets its page for a new name", async () => {
    mocks.names.mockImplementation(async (query, kind, page) => ({ query, groups: [{ entity_type: "document", total: 113, page: page ?? 1, page_size: 5, items: [{ id: "doc", title: `${query} page ${page ?? 1}`, href: "/documents/doc" }] }] }));
    render(shell());
    const input = open();
    fireEvent.change(input, { target: { value: "First" } });
    await settle();
    const group = screen.getByRole("region", { name: "Documents (113)" });
    fireEvent.click(within(group).getByRole("button", { name: "Next" }));
    await settle();
    expect(screen.getByRole("button", { name: "First page 2" })).toBeTruthy();
    expect(mocks.names).toHaveBeenCalledWith("First", "document", 2);
    fireEvent.change(input, { target: { value: "Second" } });
    expect(screen.queryByText("First page 2")).toBeNull();
    await settle();
    expect(screen.getByRole("button", { name: "Second page 1" })).toBeTruthy();
    expect(mocks.names).not.toHaveBeenCalledWith("Second", "document", 2);
  });

  it("distinguishes a failed lookup from no matches and allows retry", async () => {
    mocks.names.mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValue({ query: "Needle", groups: [] });
    render(shell());
    fireEvent.change(open(), { target: { value: "Needle" } });
    await settle();
    const error = screen.getByRole("alert");
    expect(within(error).getByText("Could not find objects")).toBeTruthy();
    expect(screen.queryByText("No matching objects")).toBeNull();
    fireEvent.click(within(error).getByRole("button", { name: "Retry" }));
    await settle();
    expect(screen.getByText("No matching objects")).toBeTruthy();
  });

  it("keeps a quickly reopened palette active when the previous native close event arrives late", async () => {
    HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
    render(shell());
    open();
    const dialog = screen.getByRole("dialog", { name: "Search and navigation" });
    fireEvent.click(screen.getByRole("button", { name: "Close search" }));
    const input = open();
    fireEvent(dialog, new Event("close"));
    fireEvent.change(input, { target: { value: "Needle" } });
    await settle();
    expect(screen.getByRole("button", { name: "Needle project", exact: true })).toBeTruthy();
  });

  it("keeps old lookup results out of a new query and a new account", async () => {
    let release!: (value: ReturnType<typeof response>) => void;
    mocks.names.mockImplementation(query => query === "Old" ? new Promise(resolve => { release = resolve; }) : Promise.resolve(response(query)));
    const view = render(shell());
    const input = open();
    fireEvent.change(input, { target: { value: "Old" } });
    await settle();
    expect(mocks.names).toHaveBeenCalledWith("Old");
    fireEvent.change(input, { target: { value: "New" } });
    await settle();
    expect(screen.getByRole("button", { name: "New project" })).toBeTruthy();
    await act(async () => { release(response("Old")); });
    await settle();
    expect(screen.queryByRole("button", { name: "Old project" })).toBeNull();
    mocks.auth.user.user_id = "bob";
    view.rerender(shell());
    expect(screen.queryByRole("button", { name: "New project" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Search and navigation" })).toBeNull();
  });

  it("routes saved and recent searches to their canonical execution flow and exposes useful actions", async () => {
    mocks.history.mockResolvedValue({ entries: [{ id: "history-id", query_text: "Recent research" }] });
    mocks.saved.mockResolvedValue({ items: [{ id: "saved-id", name: "Saved research" }] });
    render(shell());
    open();
    await settle();
    expect(screen.getByRole("button", { name: "Saved research", exact: true })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Saved research", exact: true }));
    expect(mocks.router.push).toHaveBeenCalledWith("/search?saved=saved-id");
    open();
    await settle();
    fireEvent.click(screen.getByRole("button", { name: "Recent research", exact: true }));
    expect(mocks.router.push).toHaveBeenCalledWith("/search?history=history-id");
    open();
    expect(screen.getByRole("button", { name: "New mission", exact: true })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload documents", exact: true })).toBeTruthy();
    expect(screen.getByText("Keyboard help")).toBeTruthy();
  });
});
