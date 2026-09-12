export type ThemeChoice = "system" | "light" | "dark";

export const THEME_EVENT = "tracelab:theme-change";
export const themeStorageKey = (userId?: string | null) => `tracelab.theme.v1:${userId || "guest"}`;

const transientChoices = new Map<string, ThemeChoice>();

export function readThemeChoice(userId?: string | null): ThemeChoice {
  const key = themeStorageKey(userId);
  let value: string | null | undefined;
  try {
    value = window.localStorage.getItem(key);
  } catch {
    value = transientChoices.get(key);
  }
  return value === "light" || value === "dark" ? value : "system";
}

export function writeThemeChoice(choice: ThemeChoice, userId?: string | null) {
  const key = themeStorageKey(userId);
  transientChoices.set(key, choice);
  try {
    window.localStorage.setItem(key, choice);
  } catch {
    // A storage-disabled browser can still change the theme for this session.
  }
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function themeSnapshot(userId?: string | null) {
  const choice = readThemeChoice(userId);
  const prefersDark = typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = choice === "system" ? (prefersDark ? "dark" : "light") : choice;
  return `${choice}:${resolved}`;
}

// Runs in <head> before the first body paint. No credentials enter the script;
// the stored user ID is used only to select that user's saved theme preference.
export const themeBootstrapScript = `(() => {
  let choice = "system";
  try {
    let auth = null;
    try { auth = JSON.parse(localStorage.getItem("tracelab.auth.v2") || "null"); } catch {}
    choice = localStorage.getItem("tracelab.theme.v1:" + (auth?.user_id || "guest")) || "system";
  } catch {}
  const dark = choice === "dark" || (choice !== "light" && typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  root.dataset.brand = "A";
  root.dataset.theme = dark ? "dark" : "light";
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
})();`;
