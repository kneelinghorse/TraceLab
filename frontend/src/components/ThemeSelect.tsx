import { useTheme } from "@/contexts/ThemeContext";
import type { ThemeChoice } from "@/lib/theme";
import { THEME_LABELS } from "@/lib/theme";

export function ThemeSelect() {
  const { choice, resolved, setChoice } = useTheme();
  return (
    <label className="flex items-center justify-between gap-3 text-sm text-muted">
      <span>Theme</span>
      <select
        aria-label="Color theme"
        className="rounded-lg border border-line bg-surface px-2 py-1.5 text-foreground"
        value={choice}
        onChange={(event) => setChoice(event.target.value as ThemeChoice)}
      >
        <option value="system">{choice === "system" ? `System (${THEME_LABELS[resolved]})` : "System"}</option>
        {Object.entries(THEME_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  );
}
