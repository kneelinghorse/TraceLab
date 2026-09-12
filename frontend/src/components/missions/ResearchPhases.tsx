import { useState } from "react";

interface ResearchTask {
  name: string;
  status?: "pending" | "in_progress" | "completed";
  description?: string;
}

interface ResearchPhase {
  name: string;
  description?: string;
  tasks?: ResearchTask[];
}

interface ResearchPhasesProps {
  phases: Record<string, unknown>;
}

function ChevronIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      className={`w-5 h-5 transition-transform ${isOpen ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function TaskStatusIcon({ status }: { status?: string }) {
  if (status === "completed") {
    return (
      <span className="w-4 h-4 rounded-full bg-success-surface dark:bg-success-surface flex items-center justify-center">
        <svg className="w-2.5 h-2.5 text-success" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  }
  if (status === "in_progress") {
    return <span className="w-4 h-4 rounded-full bg-accent animate-pulse" />;
  }
  return <span className="w-4 h-4 rounded-full bg-surface-alt dark:bg-surface-alt" />;
}

function PhaseSection({ phase, index }: { phase: ResearchPhase; index: number }) {
  const [isOpen, setIsOpen] = useState(index === 0);
  const tasks = phase.tasks ?? [];

  return (
    <div className="border border-line dark:border-line rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 bg-background dark:bg-surface hover:bg-surface dark:hover:bg-surface-alt transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <span className="w-6 h-6 rounded-full bg-info-surface dark:bg-info-surface text-accent-text dark:text-accent-text flex items-center justify-center text-xs font-bold">
            {index + 1}
          </span>
          <span className="font-medium text-foreground dark:text-foreground">{phase.name}</span>
          {tasks.length > 0 && (
            <span className="text-xs text-muted dark:text-muted">
              ({tasks.length} task{tasks.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>
        <ChevronIcon isOpen={isOpen} />
      </button>

      {isOpen && (
        <div className="p-4 bg-surface dark:bg-background">
          {phase.description && (
            <p className="text-secondary dark:text-secondary text-sm mb-4">{phase.description}</p>
          )}

          {tasks.length > 0 ? (
            <ul className="space-y-2">
              {tasks.map((task, taskIndex) => (
                <li key={taskIndex} className="flex items-start gap-3">
                  <TaskStatusIcon status={task.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-foreground dark:text-foreground text-sm">{task.name}</p>
                    {task.description && (
                      <p className="text-muted dark:text-muted text-xs mt-0.5">{task.description}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted dark:text-muted text-sm">No tasks defined for this phase.</p>
          )}
        </div>
      )}
    </div>
  );
}

function parsePhases(phases: Record<string, unknown>): ResearchPhase[] {
  const result: ResearchPhase[] = [];

  for (const [key, value] of Object.entries(phases)) {
    if (typeof value === "object" && value !== null) {
      const phaseData = value as Record<string, unknown>;
      result.push({
        name: (phaseData.name as string) ?? key,
        description: phaseData.description as string | undefined,
        tasks: Array.isArray(phaseData.tasks)
          ? phaseData.tasks.map((t: unknown) => {
              if (typeof t === "string") {
                return { name: t };
              }
              if (typeof t === "object" && t !== null) {
                const taskObj = t as Record<string, unknown>;
                return {
                  name: (taskObj.name as string) ?? String(t),
                  status: taskObj.status as ResearchTask["status"],
                  description: taskObj.description as string | undefined,
                };
              }
              return { name: String(t) };
            })
          : undefined,
      });
    } else if (typeof value === "string") {
      result.push({ name: key, description: value });
    }
  }

  return result;
}

export function ResearchPhases({ phases }: ResearchPhasesProps) {
  const parsedPhases = parsePhases(phases);

  if (parsedPhases.length === 0) {
    return (
      <div className="text-muted dark:text-muted text-sm py-2">
        No research phases defined.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {parsedPhases.map((phase, index) => (
        <PhaseSection key={index} phase={phase} index={index} />
      ))}
    </div>
  );
}
