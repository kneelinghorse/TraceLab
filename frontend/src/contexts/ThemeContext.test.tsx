import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
const mocks = vi.hoisted(() => ({ user: { user_id: "alice" } as { user_id: string } | null }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: mocks.user }) }));
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ThemeSelect } from "@/components/ThemeSelect";
import { themeStorageKey } from "@/lib/theme";
let media: EventTarget & { matches: boolean };
beforeEach(() => {
  localStorage.clear();
  mocks.user = { user_id: "alice" };
  media = Object.assign(new EventTarget(), { matches: true });
  vi.stubGlobal("matchMedia", () => media);
});
const picker = () => <ThemeProvider><ThemeSelect /></ThemeProvider>;

describe("per-user appearance", () => {
  it("offers exactly the palettes shipped in the vendored Brand A tokens, plus System", () => {
    const css = readFileSync("node_modules/@oods/tokens/dist/css/tokens.css", "utf8");
    // `base` is an alias in the same selector block as light, not another palette.
    expect(css).toMatch(/\[data-brand='A'\]\[data-theme='base'\],\s*\[data-brand='A'\]\[data-theme='light'\] \{/);
    const themes = [...new Set([...css.matchAll(/\[data-brand='A'\]\[data-theme='([^']+)'\]/g)].map(match => match[1]))].filter(theme => theme !== "base");
    render(picker());
    const choices = screen.getAllByRole("option").map(option => (option as HTMLOptionElement).value);
    expect(choices.sort()).toEqual([...themes, "system"].sort());
  });
  it("keeps High contrast selected across OS changes and persisted for the user", () => {
    render(picker());
    fireEvent.change(screen.getByLabelText("Color theme"), { target: { value: "hc" } });
    expect(document.documentElement.dataset.theme).toBe("hc");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
    act(() => { media.matches = false; media.dispatchEvent(new Event("change")); });
    expect(document.documentElement.dataset.theme).toBe("hc");
    expect(localStorage.getItem(themeStorageKey("alice"))).toBe("hc");
  });
  it("follows OS changes only while System is selected", () => {
    render(picker());
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("option", { name: "System (Dark)" })).toBeTruthy();
    act(() => { media.matches = false; media.dispatchEvent(new Event("change")); });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(screen.getByRole("option", { name: "System (Light)" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Color theme"), { target: { value: "dark" } });
    act(() => { media.dispatchEvent(new Event("change")); });
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(themeStorageKey("alice"))).toBe("dark");
  });
  it("changes accounts without leaking one user's saved appearance to another", () => {
    localStorage.setItem(themeStorageKey("alice"), "light");
    localStorage.setItem(themeStorageKey("bob"), "dark");
    const view = render(picker());
    expect(document.documentElement.dataset.theme).toBe("light");
    mocks.user = { user_id: "bob" };
    view.rerender(picker());
    expect(document.documentElement.dataset.theme).toBe("dark");
    mocks.user = { user_id: "alice" };
    view.rerender(picker());
    expect(document.documentElement.dataset.theme).toBe("light");
  });
  it("observes changes from another tab", () => {
    render(picker());
    act(() => { localStorage.setItem(themeStorageKey("alice"), "light"); window.dispatchEvent(new StorageEvent("storage")); });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect((screen.getByLabelText("Color theme") as HTMLSelectElement).value).toBe("light");
  });
});
