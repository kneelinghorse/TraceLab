import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { THEME_EVENT, themeSnapshot, writeThemeChoice } from "@/lib/theme";
import type { ThemeChoice, ThemeName } from "@/lib/theme";

type ThemeContextValue = {
  choice: ThemeChoice;
  resolved: ThemeName;
  setChoice: (choice: ThemeChoice) => void;
};

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);
const serverSnapshot = () => "system:light";

function subscribe(callback: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener("storage", callback);
  window.addEventListener(THEME_EVENT, callback);
  media.addEventListener("change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(THEME_EVENT, callback);
    media.removeEventListener("change", callback);
  };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.user_id;
  const getSnapshot = useCallback(() => themeSnapshot(userId), [userId]);
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, serverSnapshot);
  const [choice, resolved] = snapshot.split(":") as [ThemeChoice, ThemeName];
  const setChoice = useCallback((next: ThemeChoice) => writeThemeChoice(next, userId), [userId]);

  useLayoutEffect(() => {
    // Hydration begins with the server snapshot. Read the real client choice
    // here so it cannot overwrite the head bootstrap with a light frame.
    const currentResolved = themeSnapshot(userId).split(":")[1];
    const root = document.documentElement;
    root.dataset.brand = "A";
    root.dataset.theme = currentResolved;
    root.classList.toggle("dark", currentResolved === "dark");
    // hc uses the shipped system colors on a light native canvas; it never
    // inherits the dark compatibility class or an OS-dependent native palette.
    root.style.colorScheme = currentResolved === "dark" ? "dark" : "light";
  }, [resolved, userId]);

  const value = useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const theme = useContext(ThemeContext);
  if (!theme) throw new Error("useTheme must be used within ThemeProvider");
  return theme;
}
