import { beforeEach, describe, expect, it, vi } from "vitest";

import { readThemeChoice, themeBootstrapScript, themeSnapshot, themeStorageKey, writeThemeChoice } from "./theme";

function systemTheme(prefersDark: boolean) {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: prefersDark })));
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.dataset.theme = "light";
  systemTheme(false);
});

describe("theme preference contract", () => {
  it("follows the system until the current user makes an explicit choice", () => {
    systemTheme(true);
    expect(themeSnapshot("alice")).toBe("system:dark");
    writeThemeChoice("light", "alice");
    expect(themeSnapshot("alice")).toBe("light:light");
    expect(themeSnapshot("bob")).toBe("system:dark");
    expect(localStorage.getItem(themeStorageKey("alice"))).toBe("light");
  });

  it("returns to system behavior and ignores malformed stored choices", () => {
    writeThemeChoice("dark", "alice");
    writeThemeChoice("system", "alice");
    expect(themeSnapshot("alice")).toBe("system:light");
    localStorage.setItem(themeStorageKey("alice"), "invalid");
    expect(readThemeChoice("alice")).toBe("system");
  });

  it("applies the signed-in user's dark choice before the body paints", () => {
    localStorage.setItem("tracelab.auth.v2", JSON.stringify({ user_id: "alice" }));
    localStorage.setItem(themeStorageKey("alice"), "dark");
    window.eval(themeBootstrapScript);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.brand).toBe("A");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("uses system preference for an anonymous first visit", () => {
    systemTheme(true);
    window.eval(themeBootstrapScript);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it.each([false, true])("falls back from deferred high contrast to the OS scheme before first paint (dark=%s)", (dark) => {
    systemTheme(dark);
    localStorage.setItem("tracelab.auth.v2", JSON.stringify({ user_id: "alice" }));
    localStorage.setItem(themeStorageKey("alice"), "hc");
    const resolved = dark ? "dark" : "light";
    expect(readThemeChoice("alice")).toBe("system");
    expect(themeSnapshot("alice")).toBe(`system:${resolved}`);
    window.eval(themeBootstrapScript);
    expect(document.documentElement.dataset.theme).toBe(resolved);
    expect(document.documentElement.classList.contains("dark")).toBe(dark);
    expect(document.documentElement.style.colorScheme).toBe(resolved);
  });

  it("keeps first paint and user controls usable when storage is disabled", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Disabled"); });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Disabled"); });
    systemTheme(true);
    window.eval(themeBootstrapScript);
    expect(document.documentElement.dataset.theme).toBe("dark");
    writeThemeChoice("light", "storage-disabled-user");
    expect(themeSnapshot("storage-disabled-user")).toBe("light:light");
    get.mockRestore();
    set.mockRestore();
  });
});
