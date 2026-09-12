import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
  it("follows OS changes only while System is selected", () => {
    render(picker());
    expect(document.documentElement.dataset.theme).toBe("dark");
    act(() => { media.matches = false; media.dispatchEvent(new Event("change")); });
    expect(document.documentElement.dataset.theme).toBe("light");
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
