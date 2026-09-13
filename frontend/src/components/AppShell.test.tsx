import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { isAuthenticated: true, isReady: true, user: { user_id: "alice", display_name: "Alice", email: "alice@example.test" }, logout: vi.fn() },
  role: { isAdmin: false },
  router: { pathname: "/missions/queue", push: vi.fn() },
}));
vi.mock("next/router", () => ({ useRouter: () => mocks.router }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/contexts/RoleContext", () => ({ useRole: () => mocks.role }));
vi.mock("@/components/LoginPanel", () => ({ LoginPanel: () => <p>Sign in form</p> }));
vi.mock("@/components/RegisterPanel", () => ({ RegisterPanel: () => <p>Registration form</p> }));

import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { openCommandPalette } from "@/lib/command-palette";

beforeEach(() => {
  localStorage.clear();
  mocks.auth.isAuthenticated = true;
  mocks.role.isAdmin = false;
  mocks.router.push.mockReset();
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
});
function shell() { return render(<ThemeProvider><AppShell><h1>Queue work</h1></AppShell></ThemeProvider>); }

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
    expect(within(nav).getByRole("link", { name: "Queue" }).getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByRole("link", { name: "Missions", exact: true }).hasAttribute("aria-current")).toBe(false);
    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main-content");
    expect(screen.getByRole("link", { name: "Saved searches" })).toBeTruthy();
  });

  it("keeps admin destinations out of both navigation and command search for non-admins", () => {
    const view = shell();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Search and navigation" });
    expect(within(dialog).queryByRole("button", { name: "Users" })).toBeNull();
    mocks.role.isAdmin = true;
    view.rerender(<ThemeProvider><AppShell><h1>Queue work</h1></AppShell></ThemeProvider>);
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
    expect(mocks.router.push).toHaveBeenCalledWith("/search?q=evidence%20%26%20citations");
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
