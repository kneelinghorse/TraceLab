/** Wrapping tabs share native button focus and the arrow/Home/End keyboard pattern. */
export function TabList<T extends string>({ id, label, tabs, value, onChange, disabled = false }: {
  id: string; label: string; tabs: readonly T[]; value: T; onChange: (value: T) => void; disabled?: boolean;
}) {
  return <div role="tablist" aria-label={label} className="flex flex-wrap gap-2 border-b border-line pb-3">
    {tabs.map((tab, index) => <button type="button" key={tab} id={`${id}-${tab}`} role="tab" aria-selected={value === tab} aria-controls={`${id}-panel`} disabled={disabled} tabIndex={value === tab ? 0 : -1}
      className={`rounded-lg px-3 py-2 text-sm ${value === tab ? "bg-accent text-on-accent" : "text-secondary hover:bg-surface-alt"}`} onClick={() => onChange(tab)}
      onKeyDown={event => {
        const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
        if (next !== null) { event.preventDefault(); onChange(tabs[next]); document.getElementById(`${id}-${tabs[next]}`)?.focus(); }
      }}>{tab}</button>)}
  </div>;
}
