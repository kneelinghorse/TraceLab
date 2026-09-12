import { useTheme } from "@/contexts/ThemeContext";
import type { ThemeChoice } from "@/lib/theme";

export function ThemeSelect() {
  const { choice, setChoice } = useTheme();
  return (
    <label className="flex items-center justify-between gap-3 text-sm text-muted">
      <span>Appearance</span>
      <select
        aria-label="Color theme"
        className="rounded-lg border border-line bg-surface px-2 py-1.5 text-foreground"
        value={choice}
        onChange={(event) => setChoice(event.target.value as ThemeChoice)}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
