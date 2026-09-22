/**
 * The three steps from a conversation to a running mission (LIB-2, decision #527).
 *
 * WALK-1 finding 6, Derek: "not sure if a user will know they need to submit
 * first to create the draft mission and then submit again to deepsearch to run
 * the research." The two steps are deliberate (a draft is an artifact that can
 * be run any time, decision #525), so the strip explains them rather than
 * removing one. Shown on /librarian and on a draft mission reached from it;
 * one remembered preference hides it everywhere.
 */

const STEPS = [
  { title: "Shape it", detail: "Talk it through with the Librarian." },
  { title: "Review the draft", detail: "Read the mission it proposes, then create it." },
  { title: "Run it", detail: "Submit the saved draft to DeepSearch when you are ready." },
] as const;

export function LibrarianSteps({ current, onDismiss }: { current: 1 | 2 | 3; onDismiss?: () => void }) {
  return (
    <nav aria-label="Where you are" className="rounded-xl border border-line bg-surface-alt px-4 py-3">
      <ol className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-6">
        {STEPS.map((step, index) => {
          const number = (index + 1) as 1 | 2 | 3;
          const active = number === current;
          return (
            <li
              key={step.title}
              aria-current={active ? "step" : undefined}
              className={`flex min-w-0 flex-1 gap-2 text-sm ${active ? "text-foreground" : "text-secondary"}`}
            >
              <span
                aria-hidden="true"
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-accent text-on-accent" : "border border-line-strong"}`}
              >
                {number}
              </span>
              <span className="min-w-0">
                <span className={`block ${active ? "font-semibold" : ""}`}>{step.title}</span>
                <span className="block text-xs text-secondary">{step.detail}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="mt-2 text-xs text-secondary underline hover:text-foreground">
          Don&apos;t show this again
        </button>
      )}
    </nav>
  );
}
